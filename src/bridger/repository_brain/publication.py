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
    except BaseException:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()
        raise
    return destination / "repository-brain.json"
