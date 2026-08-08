"""Immutable Layer 4 graph snapshot publication and loading."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import networkx as nx  # type: ignore[import-untyped]
from networkx.readwrite import json_graph  # type: ignore[import-untyped]

from extraction.graphify import adapt_file_index_to_graphify, run_graphify_extraction
from graph.errors import FullRebuildRequired, InvalidGraphSnapshot
from graph.intelligence import (
    _build_observations,
    analyze_graph_structure,
    compute_community_structure,
)
from graph.validation import validate_graph_intelligence
from graphify.build import build_merge
from graphify.cluster import community_member_sigs
from graphify.export import to_json
from graphify.report import generate as generate_report
from models.files import FileChangeSet, FileIndex
from models.graph import (
    ArtifactReference,
    GraphBuildResult,
    GraphConstructionConfig,
    GraphDiagnostics,
    GraphSnapshotManifest,
    RepositoryGraph,
)
from models.repository import RepositoryContext

SNAPSHOT_SCHEMA_VERSION = "1"
GRAPH_CONTRACT_VERSION = "bridger.graph.v1"
GRAPHIFY_ENGINE_VERSION = "0.9.32"
EXTRACTOR_FINGERPRINT = "graphify-ast-extract-v1"
INVENTORY_POLICY_VERSION = "bridger-intake-v1"

_PAYLOAD_ARTIFACTS = (
    "graph.json",
    "structural.json",
    "diagnostics.json",
    "graphify-manifest.json",
    "GRAPH_REPORT.md",
)
_REQUIRED_ARTIFACTS = _PAYLOAD_ARTIFACTS + ("snapshot-manifest.json",)


def create_graph_snapshot(
    context: RepositoryContext,
    file_index: FileIndex,
    graph: RepositoryGraph,
    diagnostics: GraphDiagnostics,
    graphify_derived_state: dict[str, Any],
    config: GraphConstructionConfig,
    output_root: Path,
    *,
    graphify_manifest: dict[str, Any] | None = None,
    build_mode: Literal["full", "incremental"] = "full",
    parent_snapshot_id: str | None = None,
) -> GraphBuildResult:
    """Validate, publish, and select one immutable deterministic graph snapshot."""
    if diagnostics.publication_blocking:
        raise InvalidGraphSnapshot("publication-blocking graph diagnostics")
    _validate_context_and_index(context, file_index)
    if type(graph) is not nx.DiGraph:
        raise InvalidGraphSnapshot("graph is not a networkx.DiGraph")

    storage_root = Path(output_root)
    snapshot_id = _snapshot_id(context.revision)
    with _writer_lock(storage_root):
        staging_root = storage_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{snapshot_id}-", dir=staging_root))
        try:
            _write_snapshot_payload(
                staging,
                context,
                file_index,
                graph,
                diagnostics,
                graphify_derived_state,
                graphify_manifest or _graphify_manifest(file_index),
            )
            manifest = _create_manifest(
                snapshot_id,
                context,
                file_index,
                config,
                diagnostics,
                staging,
                build_mode=build_mode,
                parent_snapshot_id=parent_snapshot_id,
            )
            _write_json(
                staging / "snapshot-manifest.json",
                manifest.model_dump(mode="json"),
            )
            _read_validated_snapshot(
                staging,
                expected_context=context,
                expected_file_index=file_index,
                expected_config=config,
            )
            snapshot_root = storage_root / "snapshots" / snapshot_id
            snapshot_root.parent.mkdir(parents=True, exist_ok=True)
            if snapshot_root.exists():
                raise InvalidGraphSnapshot(f"snapshot already exists: {snapshot_id}")
            staging.replace(snapshot_root)
            _write_current_pointer(storage_root, snapshot_id)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return GraphBuildResult(
        operation_mode=build_mode,
        graph=graph,
        manifest=manifest,
        diagnostics=diagnostics,
        snapshot_root=snapshot_root,
    )


def load_graph_snapshot(
    output_root: Path,
    snapshot_id: str | None = None,
) -> GraphBuildResult:
    """Strictly load an explicit immutable snapshot or the selected current one."""
    storage_root = Path(output_root)
    selected_id = snapshot_id or _read_current_pointer(storage_root)
    if not selected_id or Path(selected_id).name != selected_id:
        raise InvalidGraphSnapshot("invalid graph snapshot id")
    snapshot_root = storage_root / "snapshots" / selected_id
    graph, manifest, diagnostics, _structural = _read_validated_snapshot(snapshot_root)
    return GraphBuildResult(
        operation_mode="loaded",
        graph=graph,
        manifest=manifest,
        diagnostics=diagnostics,
        snapshot_root=snapshot_root,
    )


def validate_graph_snapshot(
    snapshot_root: Path,
    *,
    expected_context: RepositoryContext | None = None,
    expected_file_index: FileIndex | None = None,
    expected_config: GraphConstructionConfig | None = None,
) -> None:
    """Reject a staged or persisted snapshot that violates Layer 4 invariants."""
    _read_validated_snapshot(
        Path(snapshot_root),
        expected_context=expected_context,
        expected_file_index=expected_file_index,
        expected_config=expected_config,
    )


def update_graph_snapshot(
    previous_manifest: GraphSnapshotManifest,
    target_context: RepositoryContext,
    target_file_index: FileIndex,
    changes: FileChangeSet,
    config: GraphConstructionConfig,
    output_root: Path,
    *,
    cache_root: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None,
) -> GraphBuildResult:
    """Publish a complete incremental snapshot using Layer 1 and Graphify merge."""
    _require_incremental_compatibility(
        previous_manifest,
        target_context,
        target_file_index,
        changes,
        config,
    )
    previous = load_graph_snapshot(output_root, previous_manifest.snapshot_id)
    if previous.manifest != previous_manifest:
        raise FullRebuildRequired("previous manifest does not match persisted snapshot")

    eligible_paths = set(
        adapt_file_index_to_graphify(target_context, target_file_index)
    )
    changed_paths = set(changes.added_paths) | set(changes.modified_paths)
    paths_to_extract = [
        path
        for path in sorted(eligible_paths)
        if path.relative_to(target_context.root_path.resolve()).as_posix()
        in changed_paths
    ]
    graphify_extraction = run_graphify_extraction(
        paths_to_extract,
        target_context.root_path,
        cache_root=cache_root,
        parallel=parallel,
        max_workers=max_workers,
    )
    prune_sources = sorted(set(changes.deleted_paths) | set(changes.modified_paths))
    merged_graph = build_merge(
        [graphify_extraction],
        graph_path=previous.snapshot_root / "graph.json",
        prune_sources=prune_sources,
        directed=True,
        root=target_context.root_path,
    )
    if type(merged_graph) is not nx.DiGraph:
        raise FullRebuildRequired(
            "Graphify incremental merge did not produce a DiGraph"
        )
    merged_graph.graph["repository_id"] = target_context.repository_id
    merged_graph.graph["revision"] = target_context.revision
    merged_graph.graph["scope_path"] = target_context.scope_path

    community_structure = compute_community_structure(merged_graph, config)
    derived_state = {
        **community_structure,
        **analyze_graph_structure(merged_graph, community_structure, config),
    }
    merged_extraction = _graph_to_extraction(merged_graph)
    build_observations = _build_observations(merged_extraction)
    build_observations["output_node_count"] = merged_graph.number_of_nodes()
    build_observations["output_edge_count"] = merged_graph.number_of_edges()
    build_observations["output_hyperedge_count"] = len(
        merged_graph.graph.get("hyperedges", [])
    )
    diagnostics = validate_graph_intelligence(
        target_context,
        target_file_index,
        merged_graph,
        merged_extraction,
        derived_state,
        build_observations,
    )
    if diagnostics.publication_blocking:
        raise FullRebuildRequired("incremental graph diagnostics block publication")
    return create_graph_snapshot(
        target_context,
        target_file_index,
        merged_graph,
        diagnostics,
        derived_state,
        config,
        output_root,
        graphify_manifest=_graphify_manifest(target_file_index),
        build_mode="incremental",
        parent_snapshot_id=previous_manifest.snapshot_id,
    )


def _write_snapshot_payload(
    staging: Path,
    context: RepositoryContext,
    file_index: FileIndex,
    graph: RepositoryGraph,
    diagnostics: GraphDiagnostics,
    derived_state: dict[str, Any],
    graphify_manifest: dict[str, Any],
) -> None:
    communities = derived_state.get("communities")
    labels = derived_state.get("community_labels")
    if not isinstance(communities, dict) or not isinstance(labels, dict):
        raise InvalidGraphSnapshot("derived state is missing communities or labels")
    if not to_json(
        graph,
        communities,
        str(staging / "graph.json"),
        force=True,
        built_at_commit=context.revision,
        community_labels=labels,
    ):
        raise InvalidGraphSnapshot("Graphify refused graph serialization")
    _write_json(staging / "structural.json", derived_state)
    _write_json(staging / "diagnostics.json", diagnostics.model_dump(mode="json"))
    _write_json(staging / "graphify-manifest.json", graphify_manifest)
    report = generate_report(
        graph,
        communities,
        derived_state.get("cohesion", {}),
        labels,
        derived_state.get("god_nodes", []),
        derived_state.get("surprising_connections", []),
        {
            "warning": (
                "Bridger FileIndex supplies the authoritative file count "
                f"({len(file_index.files)}); it does not collect word counts."
            )
        },
        {"input": 0, "output": 0},
        str(context.root_path),
        suggested_questions=derived_state.get("suggested_questions", []),
        built_at_commit=context.revision,
    )
    _write_text(staging / "GRAPH_REPORT.md", report + "\n")


def _create_manifest(
    snapshot_id: str,
    context: RepositoryContext,
    file_index: FileIndex,
    config: GraphConstructionConfig,
    diagnostics: GraphDiagnostics,
    staging: Path,
    *,
    build_mode: Literal["full", "incremental"],
    parent_snapshot_id: str | None,
) -> GraphSnapshotManifest:
    artifacts = {
        name: _artifact_reference(staging / name, name) for name in _PAYLOAD_ARTIFACTS
    }
    return GraphSnapshotManifest(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        file_index_digest=_canonical_sha256(file_index.model_dump(mode="json")),
        graph_contract_version=GRAPH_CONTRACT_VERSION,
        graphify_engine_version=GRAPHIFY_ENGINE_VERSION,
        extractor_fingerprint=EXTRACTOR_FINGERPRINT,
        inventory_policy_version=INVENTORY_POLICY_VERSION,
        build_configuration_fingerprint=_canonical_sha256(
            config.model_dump(mode="json")
        ),
        build_mode=build_mode,
        parent_snapshot_id=parent_snapshot_id,
        artifacts=artifacts,
        created_at=datetime.now(UTC),
        validation_status="validated",
        diagnostics_summary=_diagnostics_summary(diagnostics),
    )


def _read_validated_snapshot(
    snapshot_root: Path,
    *,
    expected_context: RepositoryContext | None = None,
    expected_file_index: FileIndex | None = None,
    expected_config: GraphConstructionConfig | None = None,
) -> tuple[RepositoryGraph, GraphSnapshotManifest, GraphDiagnostics, dict[str, Any]]:
    if not snapshot_root.is_dir():
        raise InvalidGraphSnapshot(f"snapshot directory is missing: {snapshot_root}")
    manifest = _read_manifest(snapshot_root / "snapshot-manifest.json")
    _validate_manifest(
        manifest,
        snapshot_root,
        expected_context,
        expected_file_index,
        expected_config,
    )
    graph = _read_graph(snapshot_root / "graph.json")
    structural = _read_json_object(snapshot_root / "structural.json")
    diagnostics = _read_diagnostics(snapshot_root / "diagnostics.json")
    _validate_graph_identity(graph, manifest)
    _validate_structural_state(graph, structural)
    _validate_diagnostics(manifest, diagnostics)
    if diagnostics.publication_blocking:
        raise InvalidGraphSnapshot("snapshot diagnostics block publication")
    return graph, manifest, diagnostics, structural


def _validate_manifest(
    manifest: GraphSnapshotManifest,
    snapshot_root: Path,
    expected_context: RepositoryContext | None,
    expected_file_index: FileIndex | None,
    expected_config: GraphConstructionConfig | None,
) -> None:
    if manifest.schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise InvalidGraphSnapshot("unsupported snapshot manifest schema")
    if manifest.validation_status != "validated":
        raise InvalidGraphSnapshot("snapshot manifest is not validated")
    if manifest.graph_contract_version != GRAPH_CONTRACT_VERSION:
        raise InvalidGraphSnapshot("incompatible graph contract version")
    if manifest.graphify_engine_version != GRAPHIFY_ENGINE_VERSION:
        raise InvalidGraphSnapshot("incompatible Graphify engine version")
    if manifest.extractor_fingerprint != EXTRACTOR_FINGERPRINT:
        raise InvalidGraphSnapshot("incompatible extractor fingerprint")
    if manifest.inventory_policy_version != INVENTORY_POLICY_VERSION:
        raise InvalidGraphSnapshot("incompatible inventory policy version")
    for name in _REQUIRED_ARTIFACTS:
        if not (snapshot_root / name).is_file():
            raise InvalidGraphSnapshot(f"required snapshot artifact is missing: {name}")
    if set(manifest.artifacts) != set(_PAYLOAD_ARTIFACTS):
        raise InvalidGraphSnapshot("snapshot manifest has an invalid artifact set")
    for name, reference in manifest.artifacts.items():
        if reference.path != name:
            raise InvalidGraphSnapshot(f"artifact path does not match its name: {name}")
        actual = _artifact_reference(snapshot_root / name, name)
        if actual != reference:
            raise InvalidGraphSnapshot(f"artifact integrity check failed: {name}")
    if expected_context is not None:
        _validate_context_identity(manifest, expected_context)
    if expected_file_index is not None:
        _validate_context_and_index(
            expected_context or _context_from_manifest(manifest),
            expected_file_index,
        )
        if manifest.file_index_digest != _canonical_sha256(
            expected_file_index.model_dump(mode="json")
        ):
            raise InvalidGraphSnapshot("FileIndex digest does not match snapshot")
    if expected_config is not None:
        expected_fingerprint = _canonical_sha256(
            expected_config.model_dump(mode="json")
        )
        if manifest.build_configuration_fingerprint != expected_fingerprint:
            raise InvalidGraphSnapshot(
                "graph configuration fingerprint does not match snapshot"
            )


def _validate_structural_state(
    graph: RepositoryGraph,
    structural: dict[str, Any],
) -> None:
    required = {
        "communities",
        "cohesion",
        "community_member_signatures",
        "community_labels",
        "god_nodes",
        "surprising_connections",
        "suggested_questions",
    }
    if not required.issubset(structural):
        raise InvalidGraphSnapshot("structural state is incomplete")
    communities = structural["communities"]
    if not isinstance(communities, dict):
        raise InvalidGraphSnapshot("structural communities are not a dictionary")
    members: list[str] = []
    normalized_communities: dict[int, list[str]] = {}
    for key, value in communities.items():
        try:
            community_id = int(key)
        except (TypeError, ValueError) as error:
            raise InvalidGraphSnapshot("structural community id is invalid") from error
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise InvalidGraphSnapshot("structural community members are invalid")
        normalized_communities[community_id] = value
        members.extend(value)
    if set(members) != set(graph.nodes) or len(members) != len(set(members)):
        raise InvalidGraphSnapshot("structural communities do not cover graph nodes")
    signatures = structural["community_member_signatures"]
    if not isinstance(signatures, dict):
        raise InvalidGraphSnapshot("community member signatures are invalid")
    expected_signatures = community_member_sigs(normalized_communities)
    normalized_signatures = {int(key): value for key, value in signatures.items()}
    if normalized_signatures != expected_signatures:
        raise InvalidGraphSnapshot("community member signatures do not match members")
    labels = structural["community_labels"]
    cohesion = structural["cohesion"]
    if not isinstance(labels, dict) or not isinstance(cohesion, dict):
        raise InvalidGraphSnapshot("community labels or cohesion are invalid")
    community_keys = {str(key) for key in normalized_communities}
    if {str(key) for key in labels} != community_keys or {
        str(key) for key in cohesion
    } != community_keys:
        raise InvalidGraphSnapshot(
            "community labels or cohesion do not match communities"
        )
    if not all(isinstance(value, str) for value in labels.values()):
        raise InvalidGraphSnapshot("community labels are invalid")
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in cohesion.values()
    ):
        raise InvalidGraphSnapshot("community cohesion values are invalid")
    structural_analysis_keys = (
        "god_nodes",
        "surprising_connections",
        "suggested_questions",
    )
    if not all(isinstance(structural[key], list) for key in structural_analysis_keys):
        raise InvalidGraphSnapshot("structural analysis outputs are invalid")
    for node in structural["god_nodes"]:
        if not isinstance(node, dict) or node.get("id") not in graph:
            raise InvalidGraphSnapshot("god node references an unknown graph node")


def _validate_diagnostics(
    manifest: GraphSnapshotManifest,
    diagnostics: GraphDiagnostics,
) -> None:
    if manifest.diagnostics_summary != _diagnostics_summary(diagnostics):
        raise InvalidGraphSnapshot(
            "manifest diagnostics summary does not match diagnostics"
        )


def _read_graph(path: Path) -> RepositoryGraph:
    data = _read_json_object(path)
    if data.get("directed") is not True:
        raise InvalidGraphSnapshot("persisted graph is not directed")
    try:
        graph = json_graph.node_link_graph(data, edges="links")
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidGraphSnapshot("persisted graph cannot be reconstructed") from error
    if type(graph) is not nx.DiGraph:
        raise InvalidGraphSnapshot("persisted graph did not reconstruct as nx.DiGraph")
    if "hyperedges" not in graph.graph and isinstance(data.get("hyperedges"), list):
        graph.graph["hyperedges"] = data["hyperedges"]
    return graph


def _validate_graph_identity(
    graph: RepositoryGraph,
    manifest: GraphSnapshotManifest,
) -> None:
    for key, value in (
        ("repository_id", manifest.repository_id),
        ("revision", manifest.revision),
        ("scope_path", manifest.scope_path),
    ):
        if graph.graph.get(key) != value:
            raise InvalidGraphSnapshot(f"graph {key} does not match its manifest")
    hyperedges = graph.graph.get("hyperedges", [])
    if not isinstance(hyperedges, list):
        raise InvalidGraphSnapshot("graph hyperedges metadata is invalid")
    for hyperedge in hyperedges:
        if not isinstance(hyperedge, dict) or not isinstance(
            hyperedge.get("nodes"), list
        ):
            raise InvalidGraphSnapshot("graph hyperedge is invalid")
        if any(node not in graph for node in hyperedge["nodes"]):
            raise InvalidGraphSnapshot("graph hyperedge references an unknown node")


def _read_manifest(path: Path) -> GraphSnapshotManifest:
    try:
        return GraphSnapshotManifest.model_validate(_read_json_object(path))
    except ValueError as error:
        raise InvalidGraphSnapshot("snapshot manifest schema is invalid") from error


def _read_diagnostics(path: Path) -> GraphDiagnostics:
    try:
        return GraphDiagnostics.model_validate(_read_json_object(path))
    except ValueError as error:
        raise InvalidGraphSnapshot("snapshot diagnostics schema is invalid") from error


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidGraphSnapshot(f"invalid JSON artifact: {path.name}") from error
    if not isinstance(data, dict):
        raise InvalidGraphSnapshot(f"JSON artifact is not an object: {path.name}")
    return data


def _graph_to_extraction(graph: RepositoryGraph) -> dict[str, Any]:
    data = json_graph.node_link_data(graph, edges="links")
    return {
        "nodes": data["nodes"],
        "edges": data["links"],
        "hyperedges": graph.graph.get("hyperedges", []),
    }


def _graphify_manifest(file_index: FileIndex) -> dict[str, Any]:
    """Persist opaque Graphify operational input without making it authoritative."""
    return {
        "schema_version": 1,
        "files": [
            {"path": record.path, "git_object_id": record.git_object_id}
            for record in file_index.files
            if record.disposition.processing_mode == "extract"
            and record.disposition.read_mode == "full"
        ],
    }


def _require_incremental_compatibility(
    previous: GraphSnapshotManifest,
    context: RepositoryContext,
    file_index: FileIndex,
    changes: FileChangeSet,
    config: GraphConstructionConfig,
) -> None:
    mismatches: list[str] = []
    if previous.repository_id != context.repository_id:
        mismatches.append("repository_id")
    if previous.scope_path != context.scope_path:
        mismatches.append("scope_path")
    expected = {
        "graph_contract_version": GRAPH_CONTRACT_VERSION,
        "graphify_engine_version": GRAPHIFY_ENGINE_VERSION,
        "extractor_fingerprint": EXTRACTOR_FINGERPRINT,
        "inventory_policy_version": INVENTORY_POLICY_VERSION,
        "build_configuration_fingerprint": _canonical_sha256(
            config.model_dump(mode="json")
        ),
    }
    for field, value in expected.items():
        if getattr(previous, field) != value:
            mismatches.append(field)
    if changes.base_revision != previous.revision:
        mismatches.append("FileChangeSet.base_revision")
    if changes.target_revision != context.revision:
        mismatches.append("FileChangeSet.target_revision")
    if file_index.revision != context.revision:
        mismatches.append("target FileIndex revision")
    if (
        file_index.repository_id != context.repository_id
        or file_index.scope_path != context.scope_path
    ):
        mismatches.append("target FileIndex identity")
    if mismatches:
        raise FullRebuildRequired(
            "incremental snapshot requires a full rebuild: " + ", ".join(mismatches)
        )


def _validate_context_and_index(
    context: RepositoryContext,
    file_index: FileIndex,
) -> None:
    if (
        context.repository_id != file_index.repository_id
        or context.revision != file_index.revision
        or context.scope_path != file_index.scope_path
    ):
        raise InvalidGraphSnapshot("RepositoryContext and FileIndex identity differ")


def _validate_context_identity(
    manifest: GraphSnapshotManifest,
    context: RepositoryContext,
) -> None:
    if (
        manifest.repository_id != context.repository_id
        or manifest.revision != context.revision
        or manifest.scope_path != context.scope_path
    ):
        raise InvalidGraphSnapshot("snapshot manifest does not match RepositoryContext")


def _context_from_manifest(manifest: GraphSnapshotManifest) -> RepositoryContext:
    """Build a minimal internal identity solely for FileIndex consistency checks."""
    return RepositoryContext(
        repository_id=manifest.repository_id,
        root_path=Path("."),
        revision=manifest.revision,
        scope_path=manifest.scope_path,
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _artifact_reference(path: Path, relative_path: str) -> ArtifactReference:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise InvalidGraphSnapshot(
            f"artifact cannot be read: {relative_path}"
        ) from error
    return ArtifactReference(
        path=relative_path,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _diagnostics_summary(diagnostics: GraphDiagnostics) -> dict[str, int | str | bool]:
    return {
        "severity": diagnostics.severity,
        "publication_blocking": diagnostics.publication_blocking,
        "output_node_count": diagnostics.output_node_count,
        "output_edge_count": diagnostics.output_edge_count,
        "output_hyperedge_count": diagnostics.output_hyperedge_count,
        "community_count": diagnostics.community_count,
    }


def _snapshot_id(revision: str) -> str:
    return f"{revision[:12]}-{uuid.uuid4().hex}"


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _read_current_pointer(storage_root: Path) -> str:
    try:
        snapshot_id = (storage_root / "current").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise InvalidGraphSnapshot("current graph snapshot is not available") from error
    if not snapshot_id:
        raise InvalidGraphSnapshot("current graph snapshot pointer is empty")
    return snapshot_id


def _write_current_pointer(storage_root: Path, snapshot_id: str) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    temporary = storage_root / f".current-{uuid.uuid4().hex}.tmp"
    _write_text(temporary, snapshot_id + "\n")
    temporary.replace(storage_root / "current")


@contextmanager
def _writer_lock(storage_root: Path) -> Iterator[None]:
    storage_root.mkdir(parents=True, exist_ok=True)
    lock_path = storage_root / ".publish.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
