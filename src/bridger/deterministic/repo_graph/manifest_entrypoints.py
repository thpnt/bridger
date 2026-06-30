import posixpath
from pathlib import PurePosixPath

from pydantic import JsonValue

from bridger.deterministic.repo_graph.imports import SafeFileIndex
from bridger.models.repo_context import ManifestFile, ManifestKind, RepoContextArtifact
from bridger.models.repo_graph import GraphEdge, GraphEdgeKind, GraphNode, GraphNodeKind

SCRIPT_EXTENSIONS = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")


def build_manifest_entrypoint_graph(
    repo_context: RepoContextArtifact, safe_files: SafeFileIndex
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for manifest in repo_context.manifests:
        if not safe_files.contains(manifest.path):
            continue
        for key, value, target in _manifest_entries(manifest, safe_files):
            node_id = f"manifest:{manifest.path}:{key}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    kind=GraphNodeKind.MANIFEST_ENTRY,
                    path=manifest.path,
                    key=key,
                )
            )
            if target is not None:
                edges.append(
                    GraphEdge(
                        from_id=node_id,
                        to_id=f"file:{target}",
                        kind=GraphEdgeKind.DECLARES_ENTRYPOINT,
                    )
                )
    return nodes, edges


def _manifest_entries(
    manifest: ManifestFile, safe_files: SafeFileIndex
) -> list[tuple[str, str, str | None]]:
    if manifest.kind is ManifestKind.PYTHON_PYPROJECT:
        return _python_script_entries(manifest, safe_files)
    if manifest.kind is ManifestKind.NODE_PACKAGE_JSON:
        return _package_entries(manifest, safe_files)
    return []


def _python_script_entries(
    manifest: ManifestFile, safe_files: SafeFileIndex
) -> list[tuple[str, str, str | None]]:
    scripts = manifest.parsed.get("scripts")
    if not isinstance(scripts, dict):
        return []
    entries: list[tuple[str, str, str | None]] = []
    for name, value in sorted(scripts.items()):
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        module = value.partition(":")[0]
        entries.append(
            (
                f"project.scripts.{name}",
                value,
                _resolve_python_module(module, safe_files),
            )
        )
    return entries


def _package_entries(
    manifest: ManifestFile, safe_files: SafeFileIndex
) -> list[tuple[str, str, str | None]]:
    entries: list[tuple[str, str, str | None]] = []
    bin_value = manifest.parsed.get("bin")
    if isinstance(bin_value, str):
        entries.append(
            (
                "bin",
                bin_value,
                _resolve_script_path(manifest.path, bin_value, safe_files),
            )
        )
    elif isinstance(bin_value, dict):
        entries.extend(_package_bin_entries(manifest.path, bin_value, safe_files))
    for key in ("main", "module"):
        value = manifest.parsed.get(key)
        if isinstance(value, str):
            entries.append(
                (key, value, _resolve_script_path(manifest.path, value, safe_files))
            )
    return entries


def _package_bin_entries(
    manifest_path: str,
    values: dict[str, JsonValue],
    safe_files: SafeFileIndex,
) -> list[tuple[str, str, str | None]]:
    entries: list[tuple[str, str, str | None]] = []
    for name, value in sorted(values.items()):
        if isinstance(name, str) and isinstance(value, str):
            entries.append(
                (
                    f"bin.{name}",
                    value,
                    _resolve_script_path(manifest_path, value, safe_files),
                )
            )
    return entries


def _resolve_python_module(module: str, safe_files: SafeFileIndex) -> str | None:
    if not module or any(not part.isidentifier() for part in module.split(".")):
        return None
    path = module.replace(".", "/")
    candidates = (
        f"src/{path}.py",
        f"src/{path}/__init__.py",
        f"{path}.py",
        f"{path}/__init__.py",
    )
    matches = safe_files.existing_candidates(candidates)
    return matches[0] if len(matches) == 1 else None


def _resolve_script_path(
    manifest_path: str, value: str, safe_files: SafeFileIndex
) -> str | None:
    if "\\" in value:
        return None
    manifest_directory = PurePosixPath(manifest_path).parent.as_posix()
    normalized = posixpath.normpath(posixpath.join(manifest_directory, value))
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        return None
    suffix = PurePosixPath(normalized).suffix
    candidates = (
        (normalized,)
        if suffix
        else (normalized,)
        + tuple(f"{normalized}{extension}" for extension in SCRIPT_EXTENSIONS)
    )
    matches = safe_files.existing_candidates(candidates)
    return matches[0] if len(matches) == 1 else None
