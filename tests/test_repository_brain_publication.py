"""Focused Repository Brain publication selection tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import bridger.repository_brain.publication as publication_module
from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.graph import GraphBuildResult
from bridger.contracts.memory.fleet_acceptance import AcceptedMemoryFleetResult


def test_publishing_does_not_change_current_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_upstream_validation(monkeypatch)
    bridger_root = tmp_path / ".bridger"
    first = _publish(bridger_root, "first")
    first_bytes = first.read_bytes()
    publication_module.set_current_repository_brain(bridger_root, first)

    second = _publish(bridger_root, "second")
    second_bytes = second.read_bytes()

    assert publication_module.resolve_current_repository_brain(bridger_root) == first
    publication_module.set_current_repository_brain(bridger_root, second)
    assert publication_module.resolve_current_repository_brain(bridger_root) == second
    assert first.read_bytes() == first_bytes
    assert second.read_bytes() == second_bytes
    assert not list(bridger_root.glob(".current.*.tmp"))


def test_resolving_without_current_returns_none(tmp_path: Path) -> None:
    bridger_root = tmp_path / ".bridger"
    (bridger_root / "published").mkdir(parents=True)

    assert publication_module.resolve_current_repository_brain(bridger_root) is None


def test_current_pointer_contains_id_and_resolves_canonical_manifest(
    tmp_path: Path,
) -> None:
    bridger_root = tmp_path / ".bridger"
    publication = _write_publication(bridger_root, b"repository-brain")
    (bridger_root / "current").write_text(
        f"{publication.parent.name}\n",
        encoding="ascii",
    )

    assert (
        publication_module.resolve_current_repository_brain(bridger_root) == publication
    )


@pytest.mark.parametrize("pointer", ["", "../outside", "id/child", "id\nother"])
def test_malformed_current_pointer_fails_explicitly(
    tmp_path: Path,
    pointer: str,
) -> None:
    bridger_root = tmp_path / ".bridger"
    bridger_root.mkdir()
    (bridger_root / "current").write_text(pointer, encoding="ascii")

    with pytest.raises(ValueError):
        publication_module.resolve_current_repository_brain(bridger_root)


def test_dangling_current_pointer_does_not_fall_back(tmp_path: Path) -> None:
    bridger_root = tmp_path / ".bridger"
    bridger_root.mkdir()
    (bridger_root / "current").write_text("a" * 16 + "\n", encoding="ascii")

    with pytest.raises(ValueError):
        publication_module.resolve_current_repository_brain(bridger_root)


def test_invalid_content_identity_is_rejected_for_resolution_and_promotion(
    tmp_path: Path,
) -> None:
    bridger_root = tmp_path / ".bridger"
    publication = _write_publication(bridger_root, b"original")
    (bridger_root / "current").write_text(
        f"{publication.parent.name}\n",
        encoding="ascii",
    )
    publication.write_bytes(b"drifted")

    with pytest.raises(ValueError):
        publication_module.resolve_current_repository_brain(bridger_root)
    with pytest.raises(ValueError):
        publication_module.set_current_repository_brain(bridger_root, publication)


def test_promotion_rejects_publication_outside_canonical_tree(tmp_path: Path) -> None:
    bridger_root = tmp_path / ".bridger"
    outside = tmp_path / "elsewhere" / "repository-brain.json"
    outside.parent.mkdir()
    outside.write_bytes(b"repository-brain")

    with pytest.raises(ValueError):
        publication_module.set_current_repository_brain(bridger_root, outside)


def test_failed_pointer_replacement_preserves_previous_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridger_root = tmp_path / ".bridger"
    first = _write_publication(bridger_root, b"first")
    second = _write_publication(bridger_root, b"second")
    publication_module.set_current_repository_brain(bridger_root, first)

    def fail_replace(
        _source: str | bytes | Path,
        _destination: str | bytes | Path,
    ) -> None:
        raise OSError("replacement failed")

    monkeypatch.setattr(publication_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        publication_module.set_current_repository_brain(bridger_root, second)

    current = bridger_root / "current"
    assert current.read_text(encoding="ascii") == f"{first.parent.name}\n"
    assert not list(bridger_root.glob(".current.*.tmp"))


def _write_publication(bridger_root: Path, content: bytes) -> Path:
    publication_id = hashlib.sha256(content).hexdigest()[:16]
    publication = bridger_root / "published" / publication_id / "repository-brain.json"
    publication.parent.mkdir(parents=True, exist_ok=True)
    publication.write_bytes(content)
    return publication


def _publish(bridger_root: Path, revision: str) -> Path:
    graph_snapshot_id = f"snapshot-{revision}"
    graph = GraphBuildResult.model_construct(
        manifest=SimpleNamespace(
            repository_id="repository-1",
            revision=revision,
            snapshot_id=graph_snapshot_id,
        ),
        snapshot_root=bridger_root / "graphs" / graph_snapshot_id,
    )
    enrichment = GraphEnrichmentOverlay.model_construct(
        overlay_id=f"overlay-{revision}",
        graph_snapshot_id=graph_snapshot_id,
    )
    accepted = AcceptedMemoryFleetResult.model_construct(
        accepted_memory_fleet_result_id=f"accepted-{revision}",
        fleet_run_id=f"fleet-{revision}",
        source=SimpleNamespace(
            graph_snapshot_id=graph_snapshot_id,
            enrichment_overlay_id=enrichment.overlay_id,
        ),
        target_catalog_id="catalog-1",
        target_catalog_version="1",
        accepted_target_result_refs=[f"accepted-target-{revision}"],
    )
    memory_root = bridger_root / "memory"
    return publication_module.publish_repository_brain(
        graph,
        accepted,
        enrichment,
        memory_root,
        runtime_root=bridger_root / "runtime",
    )


def _disable_upstream_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publication_module, "validate_graph_snapshot", lambda *_: None)
    monkeypatch.setattr(
        publication_module,
        "validate_graph_enrichment",
        lambda *_: None,
    )
