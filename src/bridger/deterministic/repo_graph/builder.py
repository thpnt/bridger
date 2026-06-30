from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from bridger.deterministic.repo_graph.imports import (
    ImportResolver,
    JavaScriptImportResolver,
    PythonImportResolver,
    SafeFileIndex,
)
from bridger.deterministic.repo_graph.manifest_entrypoints import (
    build_manifest_entrypoint_graph,
)
from bridger.deterministic.repo_graph.nodes import (
    build_file_and_directory_graph,
    build_symbol_graph,
)
from bridger.deterministic.repo_graph.path_patterns import build_path_pattern_graph
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.repo_graph import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    RepoGraphArtifact,
    RepoGraphUnresolvedImport,
)
from bridger.models.symbol_index import SymbolIndexArtifact


def build_repo_graph_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> RepoGraphArtifact:
    root = repo_root.resolve()
    artifacts_directory = root / ".bridger" / "artifacts"
    file_index = FileIndexArtifact.model_validate_json(
        (artifacts_directory / "file-index.json").read_bytes()
    )
    repo_context = RepoContextArtifact.model_validate_json(
        (artifacts_directory / "repo-context.json").read_bytes()
    )
    symbol_index = SymbolIndexArtifact.model_validate_json(
        (artifacts_directory / "symbol-index.json").read_bytes()
    )
    safe_files = SafeFileIndex(file_index)

    nodes, edges = build_file_and_directory_graph(file_index)
    symbol_nodes, symbol_edges = build_symbol_graph(symbol_index, safe_files.safe_paths)
    nodes.extend(symbol_nodes)
    edges.extend(symbol_edges)

    import_edges, unresolved_imports = _build_import_graph(root, file_index, safe_files)
    edges.extend(import_edges)

    manifest_nodes, manifest_edges = build_manifest_entrypoint_graph(
        repo_context, safe_files
    )
    nodes.extend(manifest_nodes)
    edges.extend(manifest_edges)

    pattern_nodes, pattern_edges = build_path_pattern_graph(safe_files.safe_paths)
    nodes.extend(pattern_nodes)
    edges.extend(pattern_edges)

    return RepoGraphArtifact(
        generated_at=generated_at or datetime.now(UTC),
        nodes=_deduplicate_nodes(nodes),
        edges=_deduplicate_edges(edges),
        unresolved_imports=_deduplicate_unresolved(unresolved_imports),
    )


def _build_import_graph(
    repo_root: Path,
    file_index: FileIndexArtifact,
    safe_files: SafeFileIndex,
) -> tuple[list[GraphEdge], list[RepoGraphUnresolvedImport]]:
    resolvers: tuple[ImportResolver, ...] = (
        PythonImportResolver(),
        JavaScriptImportResolver(),
    )
    resolver_by_extension = {
        extension: resolver
        for resolver in resolvers
        for extension in resolver.supported_extensions
    }
    edges: list[GraphEdge] = []
    unresolved: list[RepoGraphUnresolvedImport] = []
    for indexed_file in sorted(file_index.files, key=lambda item: item.path):
        extension = PurePosixPath(indexed_file.path).suffix.lower()
        resolver = resolver_by_extension.get(extension)
        if resolver is None:
            continue
        try:
            content = _read_indexed_file(repo_root, indexed_file.path).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        extraction = resolver.extract_imports(indexed_file.path, content)
        resolution = resolver.resolve_imports(
            indexed_file.path, extraction.imports, safe_files
        )
        edges.extend(
            GraphEdge(
                from_id=f"file:{item.source_path}",
                to_id=f"file:{item.target_path}",
                kind=GraphEdgeKind.IMPORTS,
                import_text=item.import_text,
            )
            for item in resolution.resolved
        )
        unresolved.extend(
            RepoGraphUnresolvedImport(
                from_path=item.source_path,
                import_text=item.import_text,
                reason=item.reason.value,
            )
            for item in resolution.unresolved
        )
    return edges, unresolved


def _read_indexed_file(repo_root: Path, relative_path: str) -> bytes:
    current_path = repo_root
    for part in Path(relative_path).parts:
        current_path /= part
        if current_path.is_symlink():
            raise OSError("indexed path is no longer a safe repository file")
    resolved_path = current_path.resolve(strict=True)
    if not resolved_path.is_relative_to(repo_root):
        raise OSError("indexed path is no longer a safe repository file")
    return resolved_path.read_bytes()


def _deduplicate_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    unique: dict[str, GraphNode] = {}
    for node in nodes:
        unique.setdefault(node.id, node)
    return list(unique.values())


def _deduplicate_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    unique: dict[tuple[str, str, GraphEdgeKind, str | None], GraphEdge] = {}
    for edge in edges:
        key = (edge.from_id, edge.to_id, edge.kind, edge.import_text)
        unique.setdefault(key, edge)
    return list(unique.values())


def _deduplicate_unresolved(
    imports: list[RepoGraphUnresolvedImport],
) -> list[RepoGraphUnresolvedImport]:
    unique: dict[tuple[str, str, str], RepoGraphUnresolvedImport] = {}
    for item in imports:
        key = (item.from_path, item.import_text, item.reason)
        unique.setdefault(key, item)
    return list(unique.values())
