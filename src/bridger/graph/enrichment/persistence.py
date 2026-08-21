"""Immutable persistence and strict loading for Layer 5 overlays."""

import shutil
import tempfile
from pathlib import Path

import orjson
from pydantic import ValidationError

from bridger.artifacts.writer import write_artifact
from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.graph import GraphBuildResult
from bridger.graph.enrichment.errors import InvalidGraphEnrichment
from bridger.graph.enrichment.validation import validate_graph_enrichment

_ARTIFACT_NAME = "graph-enrichment.json"


def create_graph_enrichment(
    overlay: GraphEnrichmentOverlay,
    graph_build: GraphBuildResult,
    output_root: Path,
) -> Path:
    """Validate and atomically publish one immutable overlay under `.bridger`."""
    validate_graph_enrichment(overlay, graph_build)
    _require_path_segment(overlay.graph_snapshot_id, "graph_snapshot_id")
    _require_path_segment(overlay.overlay_id, "overlay_id")
    storage_root = Path(output_root) / "enrichment" / overlay.graph_snapshot_id
    artifact_root = storage_root / overlay.overlay_id
    if artifact_root.exists():
        raise InvalidGraphEnrichment(
            f"enrichment overlay already exists: {overlay.overlay_id}"
        )

    storage_root.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{overlay.overlay_id}-", dir=storage_root)
    )
    try:
        staging_artifact = staging_root / _ARTIFACT_NAME
        write_artifact(staging_artifact, overlay)
        loaded = load_graph_enrichment(
            staging_artifact,
            expected_graph_snapshot_id=graph_build.manifest.snapshot_id,
        )
        validate_graph_enrichment(loaded, graph_build)
        if loaded != overlay:
            raise InvalidGraphEnrichment("persisted overlay did not round-trip")
        if artifact_root.exists():
            raise InvalidGraphEnrichment(
                f"enrichment overlay already exists: {overlay.overlay_id}"
            )
        staging_root.replace(artifact_root)
    except BaseException:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    return artifact_root / _ARTIFACT_NAME


def load_graph_enrichment(
    artifact: Path,
    expected_graph_snapshot_id: str,
) -> GraphEnrichmentOverlay:
    """Load an overlay and require its exact deterministic snapshot binding."""
    artifact_path = Path(artifact)
    if artifact_path.is_dir():
        artifact_path = artifact_path / _ARTIFACT_NAME
    try:
        raw = orjson.loads(artifact_path.read_bytes())
    except (OSError, orjson.JSONDecodeError) as error:
        raise InvalidGraphEnrichment("invalid graph enrichment artifact") from error
    if not isinstance(raw, dict):
        raise InvalidGraphEnrichment("graph enrichment artifact is not an object")
    try:
        overlay = GraphEnrichmentOverlay.model_validate(raw)
    except ValidationError as error:
        raise InvalidGraphEnrichment("graph enrichment schema is invalid") from error
    if overlay.graph_snapshot_id != expected_graph_snapshot_id:
        raise InvalidGraphEnrichment(
            "graph enrichment does not match expected graph snapshot"
        )
    return overlay


def _require_path_segment(value: str, field_name: str) -> None:
    if Path(value).name != value or value in {".", ".."}:
        raise InvalidGraphEnrichment(
            f"{field_name} is not a safe artifact path segment"
        )


__all__ = ["create_graph_enrichment", "load_graph_enrichment"]
