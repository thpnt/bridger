"""Atomic publication of an accepted Repository Brain manifest."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.graph import GraphBuildResult
from bridger.contracts.memory.fleet_acceptance import AcceptedMemoryFleetResult
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.graph.enrichment.validation import validate_graph_enrichment
from bridger.graph.lifecycle import validate_graph_snapshot
from bridger.memory.persistence.store import require_path_segment

_MANIFEST_NAME = "repository-brain.json"
_COMPLETED_NAME = "repository-brain-complete"
_SUPERSEDED_NAME = "repository-brain-superseded"


def publish_repository_brain(
    graph_build: GraphBuildResult,
    accepted_fleet: AcceptedMemoryFleetResult,
    enrichment_overlay: GraphEnrichmentOverlay,
    output_root: Path,
    *,
    runtime_root: Path,
) -> Path:
    """Publish one immutable, provenance-bound Repository Brain manifest."""
    validate_graph_snapshot(graph_build.snapshot_root)
    validate_graph_enrichment(enrichment_overlay, graph_build)
    if accepted_fleet.source.graph_snapshot_id != graph_build.manifest.snapshot_id:
        raise ValueError("accepted fleet belongs to another graph snapshot")
    if accepted_fleet.source.enrichment_overlay_id != enrichment_overlay.overlay_id:
        raise ValueError("accepted fleet belongs to another enrichment overlay")

    manifest = RepositoryBrainManifest(
        repository_id=graph_build.manifest.repository_id,
        repository_revision=graph_build.manifest.revision,
        graph_snapshot_id=graph_build.manifest.snapshot_id,
        graph_snapshot_root=str(graph_build.snapshot_root),
        enrichment_overlay_id=enrichment_overlay.overlay_id,
        fleet_run_id=accepted_fleet.fleet_run_id,
        memory_runtime_root=str(runtime_root),
        memory_output_root=str(output_root),
        accepted_memory_fleet_result_id=(
            accepted_fleet.accepted_memory_fleet_result_id
        ),
        memory_target_catalog_id=accepted_fleet.target_catalog_id,
        memory_target_catalog_version=accepted_fleet.target_catalog_version,
        accepted_target_result_refs=list(accepted_fleet.accepted_target_result_refs),
    )
    encoded = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    publication_id = hashlib.sha256(encoded).hexdigest()[:16]
    destination = output_root.parent / "published" / publication_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        manifest_path = destination / "repository-brain.json"
        if manifest_path.read_bytes() != encoded:
            raise ValueError("published Repository Brain identity collision")
        return manifest_path

    staging = Path(
        tempfile.mkdtemp(prefix=f".{publication_id}-", dir=destination.parent)
    )
    try:
        manifest_path = staging / "repository-brain.json"
        manifest_path.write_bytes(encoded)
        with manifest_path.open("rb") as stream:
            os.fsync(stream.fileno())
        staging.replace(destination)
        _fsync_directory(destination.parent)
    except BaseException:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()
        raise
    return destination / "repository-brain.json"


def resolve_current_repository_brain(bridger_root: Path) -> Path | None:
    """Resolve and validate the explicitly selected Repository Brain."""
    current_path = bridger_root / "current"
    if current_path.is_symlink():
        raise ValueError("current pointer is not a regular file")
    if not current_path.exists():
        return None
    if not current_path.is_file():
        raise ValueError("current pointer is not a regular file")

    try:
        pointer = current_path.read_bytes().decode("ascii")
    except (OSError, UnicodeError) as error:
        raise ValueError("current pointer is not valid") from error
    if pointer.endswith("\n"):
        pointer = pointer[:-1]
    if not pointer or "\n" in pointer or "\r" in pointer:
        raise ValueError("current pointer is not a single publication ID")
    require_path_segment(pointer, "publication_id")

    publication_path = bridger_root / "published" / pointer / _MANIFEST_NAME
    _publication_id_from_path(bridger_root, publication_path)
    return publication_path


def set_current_repository_brain(
    bridger_root: Path,
    publication_path: Path,
) -> None:
    """Atomically select one existing immutable Repository Brain publication."""
    publication_id = _publication_id_from_path(bridger_root, publication_path)
    current_path = bridger_root / "current"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=current_path.parent,
            prefix=f".{current_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(f"{publication_id}\n".encode("ascii"))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, current_path)
        _fsync_directory(current_path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def clear_current_repository_brain(bridger_root: Path) -> None:
    """Durably invalidate the selected Brain before a fresh replacement build."""
    current_path = bridger_root / "current"
    if current_path.exists() or current_path.is_symlink():
        current_path.unlink()
        _fsync_directory(bridger_root)


def mark_repository_brain_complete(
    runtime_root: Path, fleet_run_id: str, publication_id: str
) -> None:
    """Record that final promotion completed for a fleet run."""
    marker = runtime_root / fleet_run_id / _COMPLETED_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    completed_id = completed_repository_brain_id(runtime_root, fleet_run_id)
    if completed_id is not None:
        if completed_id != publication_id:
            raise ValueError("fleet completion refers to another publication")
        return
    _write_durable_marker(marker, f"{publication_id}\n".encode("ascii"))


def supersede_existing_fleets(runtime_root: Path) -> None:
    """Exclude earlier runs from recovery when starting an explicit fresh build."""
    if not runtime_root.is_dir():
        return
    for run_root in runtime_root.iterdir():
        if (
            run_root.is_dir()
            and not run_root.is_symlink()
            and (run_root / "fleet-spec.json").is_file()
        ):
            _write_durable_marker(run_root / _SUPERSEDED_NAME, b"fresh\n")


def is_repository_brain_superseded(runtime_root: Path, fleet_run_id: str) -> bool:
    marker = runtime_root / fleet_run_id / _SUPERSEDED_NAME
    if not marker.exists():
        return False
    if marker.read_bytes() != b"fresh\n":
        raise ValueError("fleet supersession marker is invalid")
    return True


def _write_durable_marker(marker: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=marker.parent, prefix=f".{marker.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, marker)
        _fsync_directory(marker.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def completed_repository_brain_id(runtime_root: Path, fleet_run_id: str) -> str | None:
    marker = runtime_root / fleet_run_id / _COMPLETED_NAME
    if not marker.exists():
        return None
    publication_id = marker.read_text(encoding="ascii").removesuffix("\n")
    require_path_segment(publication_id, "publication_id")
    return publication_id


def _publication_id_from_path(bridger_root: Path, publication_path: Path) -> str:
    """Validate a publication path and return its content-addressed identity."""
    root = bridger_root.resolve()
    candidate = publication_path.resolve()
    published_root = root / "published"
    try:
        relative = candidate.relative_to(published_root)
    except ValueError as error:
        raise ValueError("publication must be under the published directory") from error
    if (
        publication_path.name != _MANIFEST_NAME
        or len(relative.parts) != 2
        or relative.parts[1] != _MANIFEST_NAME
        or candidate != published_root / relative.parts[0] / _MANIFEST_NAME
        or not publication_path.is_file()
    ):
        raise ValueError("publication path is not canonical")

    publication_id = relative.parts[0]
    require_path_segment(publication_id, "publication_id")
    try:
        encoded = publication_path.read_bytes()
    except OSError as error:
        raise ValueError("could not read published Repository Brain") from error
    if hashlib.sha256(encoded).hexdigest()[:16] != publication_id:
        raise ValueError("publication path does not match manifest identity")
    return publication_id


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
