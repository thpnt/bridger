"""Focused tests for the canonical consumption bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import bridger.navigation.bootstrap as bootstrap_module
from bridger.contracts.consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    IntelligenceResult,
    Lens,
    Provenance,
    ResultOperation,
    Substrate,
)
from bridger.contracts.files import FileDisposition, FileRecord
from bridger.contracts.navigation import FileOverview
from bridger.navigation import BridgerNavigator

REVISION = "a" * 40


class _FakeBrain:
    repository_revision = REVISION

    def __init__(self, publication_path: Path) -> None:
        self.publication_path = publication_path
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def search(self, request: IntelligenceQueryRequest) -> IntelligenceResult:
        item = IntelligenceItem(
            ref=BridgerRef(
                kind=BridgerRefKind.BRAIN_CONTEXT,
                target_ref={"document_id": "brain-doc", "start_line": 1, "end_line": 1},
                repository_revision=REVISION,
            ),
            kind=BridgerRefKind.BRAIN_CONTEXT,
            title="Brain document",
            content="Brain-backed result",
            provenance=Provenance(
                repository_revision=REVISION,
                substrate=Substrate.BRAIN,
                authority=Authority.DERIVED,
            ),
        )
        return IntelligenceResult(
            operation=ResultOperation.QUERY,
            repository_revision=REVISION,
            lens=request.lens,
            query=request.query,
            scope=request.scope,
            items=[item],
            completeness=Completeness(returned_count=1),
        )

    def read(self, request: IntelligenceReadRequest) -> IntelligenceResult:
        return IntelligenceResult(
            operation=ResultOperation.READ,
            repository_revision=REVISION,
            items=[],
            completeness=Completeness(returned_count=0),
        )


class _FakeRepository:
    source_identity = ("repository-1", REVISION, "snapshot-1", "overlay-1")

    def __init__(self, *_args: object) -> None:
        pass

    def get_file_overview(self, path: str) -> FileOverview:
        return FileOverview(
            file=FileRecord(
                path=path,
                git_object_id="b" * 40,
                size_bytes=1,
                content_type="source",
                disposition=FileDisposition(
                    read_mode="full",
                    processing_mode="extract",
                ),
            )
        )


def _manifest(
    graph_snapshot_root: Path,
    *,
    revision: str = REVISION,
) -> SimpleNamespace:
    return SimpleNamespace(
        repository_revision=revision,
        graph_snapshot_id="snapshot-1",
        graph_snapshot_root=str(graph_snapshot_root),
        enrichment_overlay_id="overlay-1",
    )


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    repository_root: Path,
    publication: Path,
    manifest: SimpleNamespace,
) -> tuple[list[Path], _FakeBrain]:
    selected_paths: list[Path] = []
    brain = _FakeBrain(publication)
    context = SimpleNamespace(root_path=repository_root, revision=REVISION)

    monkeypatch.setattr(bootstrap_module, "resolve_repository", lambda _root: context)
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_current_repository_brain",
        lambda _root: publication,
    )
    monkeypatch.setattr(
        bootstrap_module,
        "load_repository_brain",
        lambda path: SimpleNamespace(manifest=manifest),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "build_file_index",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "extract_repository_facts",
        lambda *_args, **_kwargs: (object(), object(), object()),
    )

    def load_graph(path: Path) -> object:
        selected_paths.append(path)
        return object()

    monkeypatch.setattr(bootstrap_module, "load_graph_snapshot_from_path", load_graph)
    monkeypatch.setattr(
        bootstrap_module,
        "load_graph_enrichment",
        lambda path, snapshot_id: selected_paths.append(path) or object(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "validate_graph_enrichment",
        lambda *_args: None,
    )
    monkeypatch.setattr(bootstrap_module, "RepositoryNavigator", _FakeRepository)
    monkeypatch.setattr(bootstrap_module, "BrainNavigator", lambda _path: brain)
    return selected_paths, brain


def test_default_publication_bootstrap_returns_usable_composite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = (
        tmp_path
        / ".bridger"
        / "published"
        / "publication-1"
        / ("repository-brain.json")
    )
    graph_root = tmp_path / ".bridger" / "graph" / "snapshots" / "snapshot-1"
    selected_paths, brain = _install_runtime(
        monkeypatch,
        tmp_path,
        publication,
        _manifest(graph_root),
    )

    with bootstrap_module.load_bridger_navigator(tmp_path) as navigator:
        query = navigator.query(
            IntelligenceQueryRequest(lens=Lens.GUARDRAILS, query="orientation")
        )
        read = navigator.read(
            IntelligenceReadRequest(
                ref=BridgerRef(
                    kind=BridgerRefKind.FILE,
                    target_ref="src/service.py",
                    repository_revision=REVISION,
                )
            )
        )

    assert isinstance(navigator, BridgerNavigator)
    assert query.items[0].provenance.substrate is Substrate.BRAIN
    assert read.items[0].provenance.substrate is Substrate.SOURCE
    assert selected_paths == [
        graph_root,
        tmp_path / ".bridger" / "enrichment" / "snapshot-1" / "overlay-1",
    ]
    assert brain.closed


def test_explicit_publication_is_used_without_current_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = tmp_path / "published" / "explicit" / "repository-brain.json"
    manifest = _manifest(tmp_path / "graph" / "snapshot-1")
    selected: list[Path] = []
    context = SimpleNamespace(root_path=tmp_path, revision=REVISION)

    monkeypatch.setattr(bootstrap_module, "resolve_repository", lambda _root: context)
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_current_repository_brain",
        lambda _root: pytest.fail("explicit publication must not resolve current"),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "load_repository_brain",
        lambda path: selected.append(path) or SimpleNamespace(manifest=manifest),
    )
    monkeypatch.setattr(bootstrap_module, "build_file_index", lambda *_args: object())
    monkeypatch.setattr(
        bootstrap_module,
        "extract_repository_facts",
        lambda *_args, **_kwargs: (object(), object(), object()),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "load_graph_snapshot_from_path",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "load_graph_enrichment",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "validate_graph_enrichment",
        lambda *_args: None,
    )
    monkeypatch.setattr(bootstrap_module, "RepositoryNavigator", _FakeRepository)
    monkeypatch.setattr(bootstrap_module, "BrainNavigator", _FakeBrain)

    navigator = bootstrap_module.load_bridger_navigator(
        tmp_path,
        publication_path=explicit,
    )
    navigator.close()

    assert selected == [explicit]


def test_revision_mismatch_fails_before_repository_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication.json"
    context = SimpleNamespace(root_path=tmp_path, revision=REVISION)
    monkeypatch.setattr(bootstrap_module, "resolve_repository", lambda _root: context)
    monkeypatch.setattr(
        bootstrap_module,
        "load_repository_brain",
        lambda _path: SimpleNamespace(
            manifest=_manifest(tmp_path / "graph", revision="b" * 40)
        ),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "build_file_index",
        lambda *_args: pytest.fail("FileIndex must not be built after a mismatch"),
    )

    with pytest.raises(ValueError, match="does not match"):
        bootstrap_module.load_bridger_navigator(
            tmp_path,
            publication_path=publication,
        )


def test_failed_composition_closes_brain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication.json"
    manifest = _manifest(tmp_path / "graph")
    _selected, brain = _install_runtime(
        monkeypatch,
        tmp_path,
        publication,
        manifest,
    )

    def fail_composition(*_args: object) -> BridgerNavigator:
        raise RuntimeError("composition failed")

    monkeypatch.setattr(bootstrap_module, "BridgerNavigator", fail_composition)

    with pytest.raises(RuntimeError, match="composition failed"):
        bootstrap_module.load_bridger_navigator(tmp_path)

    assert brain.closed
