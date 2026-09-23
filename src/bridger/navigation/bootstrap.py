"""Canonical construction of the Bridger consumption stack."""

from __future__ import annotations

from pathlib import Path

from bridger.contracts.files import IntakeConfiguration
from bridger.graph.enrichment import load_graph_enrichment, validate_graph_enrichment
from bridger.graph.lifecycle import (
    load_graph_snapshot_from_path,
    load_graph_snapshot_symbol_index,
    validate_graph_snapshot,
)
from bridger.navigation.brain import BrainNavigator
from bridger.navigation.bridger import BridgerNavigator
from bridger.navigation.navigator import RepositoryNavigator
from bridger.repository.file_index import build_file_index
from bridger.repository.service import resolve_repository
from bridger.repository_brain.loader import load_repository_brain
from bridger.repository_brain.publication import resolve_current_repository_brain


def load_bridger_navigator(
    repository_root: str | Path,
    *,
    publication_path: Path | None = None,
) -> BridgerNavigator:
    """Open one published Repository Brain and its repository authorities."""
    requested_root = Path(repository_root).expanduser().resolve()
    context = resolve_repository(requested_root)
    bridger_root = context.root_path / ".bridger"
    selected_publication = _select_publication(bridger_root, publication_path)
    published_brain = load_repository_brain(selected_publication)

    if context.revision != published_brain.manifest.repository_revision:
        raise ValueError(
            "active repository revision does not match the selected Repository Brain"
        )

    file_index = build_file_index(context, IntakeConfiguration())
    graph_build = load_graph_snapshot_from_path(
        Path(published_brain.manifest.graph_snapshot_root)
    )
    validate_graph_snapshot(
        graph_build.snapshot_root,
        expected_context=context,
        expected_file_index=file_index,
    )
    symbol_index = load_graph_snapshot_symbol_index(graph_build)
    overlay = load_graph_enrichment(
        bridger_root
        / "enrichment"
        / published_brain.manifest.graph_snapshot_id
        / published_brain.manifest.enrichment_overlay_id,
        published_brain.manifest.graph_snapshot_id,
    )
    validate_graph_enrichment(overlay, graph_build)

    repository_navigator = RepositoryNavigator(
        context,
        file_index,
        symbol_index,
        graph_build,
        overlay,
    )
    brain_navigator = BrainNavigator(
        selected_publication,
        repository_root=context.root_path,
    )
    try:
        return BridgerNavigator(brain_navigator, repository_navigator)
    except BaseException:
        brain_navigator.close()
        raise


def _select_publication(
    bridger_root: Path,
    publication_path: Path | None,
) -> Path:
    if publication_path is not None:
        return Path(publication_path)
    current = resolve_current_repository_brain(bridger_root)
    if current is None:
        raise ValueError("no current Repository Brain publication exists")
    return current


__all__ = ["load_bridger_navigator"]
