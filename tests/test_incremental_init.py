"""Incremental Repository Brain init lifecycle tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import bridger.cli as cli
import bridger.init_pipeline as init_pipeline
import bridger.repository_brain.harness as harness
from bridger.init_pipeline import (
    InitMode,
    RepositoryBrainBuildError,
    RepositoryBrainBuildResult,
    resolve_init_configuration,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def configured_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_compatible_current_brain_wins_before_recovery_and_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    file_index = object()
    publication_path = tmp_path / ".bridger" / "published" / "brain.json"
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "graph-snapshot")
    manifest = _manifest(context)
    validated: list[tuple[object, ...]] = []
    prepared: list[Path] = []
    stages: list[str] = []

    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, file_index),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: publication_path,
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_repository_brain",
        lambda path: (
            SimpleNamespace(manifest=manifest) if path == publication_path else None
        ),
    )
    monkeypatch.setattr(
        harness,
        "load_memory_target_catalog",
        lambda _configuration: _catalog(),
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_graph_snapshot",
        lambda root, snapshot_id: (
            graph_build
            if (root, snapshot_id)
            == (tmp_path / ".bridger" / "graph", manifest.graph_snapshot_id)
            else None
        ),
    )

    def validate(snapshot_root: Path, **kwargs: object) -> None:
        validated.append((snapshot_root, kwargs))

    monkeypatch.setattr(init_pipeline, "validate_graph_snapshot", validate)
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda _configuration, path: prepared.append(path),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: pytest.fail("current reuse must precede recovery"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: pytest.fail("reuse must skip extraction"),
    )

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.FULL, repository_root=tmp_path),
        on_stage=stages.append,
    )

    assert result == RepositoryBrainBuildResult(
        mode=InitMode.FULL,
        graph_build=graph_build,
        publication_path=publication_path,
        token_usage_report_path=None,
        reused=True,
    )
    assert result.runtime_metrics_report_path is not None
    assert result.runtime_metrics_report_path.exists()
    assert validated == [
        (
            graph_build.snapshot_root,
            {
                "expected_context": context,
                "expected_file_index": file_index,
                "expected_config": init_pipeline.GraphConstructionConfig(),
            },
        )
    ]
    assert prepared == [publication_path]
    assert stages[-1] == "Preparing Repository Brain index"


def test_missing_current_falls_through_to_incomplete_fleet_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    recovery_spec = object()
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: None,
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: recovery_spec,
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
    )

    assert result.reused is False
    assert received_recovery == [recovery_spec]


@pytest.mark.parametrize(
    "manifest_update",
    [
        {"repository_revision": "b" * 40},
        {"memory_target_catalog_id": "obsolete-catalog"},
    ],
)
def test_incompatible_current_falls_through_to_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    manifest_update: dict[str, str],
) -> None:
    context = _context(tmp_path)
    recovery_spec = object()
    manifest = _manifest(context, **manifest_update)
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: tmp_path / "repository-brain.json",
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_repository_brain",
        lambda _path: SimpleNamespace(manifest=manifest),
    )
    monkeypatch.setattr(
        harness,
        "load_memory_target_catalog",
        lambda _configuration: _catalog(),
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_graph_snapshot",
        lambda *_args: pytest.fail("an incompatible Brain must not load its graph"),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: recovery_spec,
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
    )

    assert result.reused is False
    assert received_recovery == [recovery_spec]


def test_corrupt_authoritative_current_pointer_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    bridger_root = tmp_path / ".bridger"
    bridger_root.mkdir()
    (bridger_root / "current").write_text("dangling-publication\n", encoding="ascii")
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: pytest.fail("corrupt current state must not fall back"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: pytest.fail("corrupt current state must fail early"),
    )

    with pytest.raises(RepositoryBrainBuildError, match="publication path"):
        init_pipeline.build_repository_brain(
            resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
        )


def test_bound_graph_validation_failure_prevents_reuse_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "corrupt-graph")
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: tmp_path / "repository-brain.json",
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_repository_brain",
        lambda _path: SimpleNamespace(manifest=_manifest(context)),
    )
    monkeypatch.setattr(
        harness,
        "load_memory_target_catalog",
        lambda _configuration: _catalog(),
    )
    monkeypatch.setattr(
        init_pipeline,
        "load_graph_snapshot",
        lambda *_args: graph_build,
    )
    monkeypatch.setattr(
        init_pipeline,
        "validate_graph_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("corrupt graph")),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: pytest.fail("corrupt graph must not fall back"),
    )

    with pytest.raises(RepositoryBrainBuildError, match="corrupt graph"):
        init_pipeline.build_repository_brain(
            resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
        )


def test_fresh_bypasses_current_and_recovery_without_deleting_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    bridger_root = tmp_path / ".bridger"
    current = bridger_root / "current"
    runtime_marker = bridger_root / "runtime" / "old-run" / "marker"
    current.parent.mkdir()
    runtime_marker.parent.mkdir(parents=True)
    current.write_text("existing-publication\n", encoding="ascii")
    runtime_marker.write_text("existing-runtime", encoding="utf-8")
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: pytest.fail("fresh must bypass current resolution"),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: pytest.fail("fresh must bypass recovery discovery"),
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(
            InitMode.FULL,
            repository_root=tmp_path,
            fresh=True,
        )
    )

    assert result.reused is False
    assert received_recovery == [None]
    assert current.read_text(encoding="ascii") == "existing-publication\n"
    assert runtime_marker.read_text(encoding="utf-8") == "existing-runtime"


def test_test_mode_skips_production_current_but_preserves_test_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    recovery_spec = object()
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "resolve_current_repository_brain",
        lambda _root: pytest.fail("test mode must not inspect production current"),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: recovery_spec,
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)

    init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.TEST, repository_root=tmp_path)
    )

    assert received_recovery == [recovery_spec]


def test_test_mode_fresh_bypasses_test_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: pytest.fail("fresh test mode must bypass recovery"),
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)

    init_pipeline.build_repository_brain(
        resolve_init_configuration(
            InitMode.TEST,
            repository_root=tmp_path,
            fresh=True,
        )
    )

    assert received_recovery == [None]


@pytest.mark.parametrize(("arguments", "expected"), [([], False), (["--fresh"], True)])
def test_cli_propagates_fresh_flag(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected: bool,
) -> None:
    captured: list[bool] = []

    def build(configuration: object, **_kwargs: object) -> RepositoryBrainBuildResult:
        captured.append(configuration.fresh)  # type: ignore[attr-defined]
        return RepositoryBrainBuildResult(
            mode=InitMode.FULL,
            graph_build=SimpleNamespace(snapshot_root=Path("/tmp/graph")),
            publication_path=Path("/tmp/repository-brain.json"),
        )

    monkeypatch.setattr(cli, "build_repository_brain", build)

    result = runner.invoke(cli.app, ["init", *arguments])

    assert result.exit_code == 0
    assert captured == [expected]


def test_cli_reports_reuse_without_historical_token_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    publication_path = tmp_path / "published" / "repository-brain.json"
    historical_report = tmp_path / "historical-token-usage.json"
    monkeypatch.setattr(
        cli,
        "build_repository_brain",
        lambda _configuration, **_kwargs: RepositoryBrainBuildResult(
            mode=InitMode.FULL,
            graph_build=SimpleNamespace(snapshot_root=tmp_path / "graph"),
            publication_path=publication_path,
            token_usage_report_path=historical_report,
            reused=True,
        ),
    )

    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert f"Repository Brain reused from {publication_path}" in result.output
    assert "Repository Brain published at" not in result.output
    assert "Token usage" not in result.output


def test_reused_current_index_failure_fails_without_brain_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    publication_path = tmp_path / ".bridger" / "published" / "brain.json"
    reused = RepositoryBrainBuildResult(
        mode=InitMode.FULL,
        graph_build=SimpleNamespace(snapshot_root=tmp_path / "graph"),
        publication_path=publication_path,
        reused=True,
    )
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (_context(tmp_path), object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "_reuse_current_repository_brain",
        lambda *_args: reused,
    )
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("index failed")),
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: pytest.fail("index failure must not rebuild Brain"),
    )

    with pytest.raises(RepositoryBrainBuildError, match="index failed"):
        init_pipeline.build_repository_brain(
            resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
        )


def test_index_readiness_loads_the_exact_publication_and_canonical_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
    publication_path = tmp_path / ".bridger" / "published" / "brain.json"
    brain = object()
    calls: list[tuple[object, Path]] = []
    monkeypatch.setattr(
        init_pipeline,
        "load_repository_brain",
        lambda path: brain if path == publication_path else pytest.fail("wrong Brain"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "ensure_brain_index",
        lambda loaded, cache, *, progress=None: calls.append((loaded, cache, progress)),
    )

    init_pipeline._ensure_repository_brain_index(configuration, publication_path)

    assert calls == [(brain, configuration.bridger_root / "cache", None)]


def test_index_readiness_threads_the_init_progress_observer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(InitMode.FULL, repository_root=tmp_path)
    publication_path = tmp_path / ".bridger" / "published" / "brain.json"
    observer = object()
    calls: list[object] = []
    monkeypatch.setattr(init_pipeline, "load_repository_brain", lambda _path: object())
    monkeypatch.setattr(
        init_pipeline,
        "ensure_brain_index",
        lambda *_args, progress: calls.append(progress),
    )

    init_pipeline._ensure_repository_brain_index(
        configuration,
        publication_path,
        progress=observer,
    )

    assert calls == [observer]


def test_fresh_publication_is_indexed_before_current_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    publication_path = tmp_path / ".bridger" / "published" / "brain.json"
    events: list[tuple[str, Path]] = []
    _patch_pipeline_completion(monkeypatch, tmp_path)

    async def publish(*_args: object) -> Path:
        events.append(("publish", publication_path))
        return publication_path

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", publish)
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda _configuration, path: events.append(("ensure", path)),
    )
    monkeypatch.setattr(
        init_pipeline,
        "set_current_repository_brain",
        lambda _root, path: events.append(("current", path)),
    )
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (_context(tmp_path), object()),
    )

    init_pipeline.build_repository_brain(
        resolve_init_configuration(
            InitMode.FULL,
            repository_root=tmp_path,
            fresh=True,
        )
    )

    assert events == [
        ("publish", publication_path),
        ("ensure", publication_path),
        ("current", publication_path),
    ]


def test_failed_new_index_preserves_previous_current(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = tmp_path / ".bridger" / "current"
    current.parent.mkdir()
    current.write_text("publication-a\n", encoding="ascii")
    _patch_pipeline_completion(monkeypatch, tmp_path)
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (_context(tmp_path), object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("index failed")),
    )
    monkeypatch.setattr(
        init_pipeline,
        "set_current_repository_brain",
        lambda *_args: pytest.fail("failed index must not promote publication"),
    )

    with pytest.raises(RepositoryBrainBuildError, match="index failed"):
        init_pipeline.build_repository_brain(
            resolve_init_configuration(
                InitMode.FULL,
                repository_root=tmp_path,
                fresh=True,
            )
        )

    assert current.read_text(encoding="ascii") == "publication-a\n"


def test_recovery_publication_uses_shared_index_and_promotion_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    recovery_spec = object()
    events: list[str] = []
    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, object()),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: recovery_spec,
    )
    received_recovery = _patch_pipeline_completion(monkeypatch, tmp_path)
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda *_args: events.append("ensure"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "set_current_repository_brain",
        lambda *_args: events.append("current"),
    )

    init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.TEST, repository_root=tmp_path)
    )

    assert received_recovery == [recovery_spec]
    assert events == ["ensure", "current"]


def _patch_pipeline_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> list[object]:
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "new-graph")
    received_recovery: list[object] = []
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: (object(), object(), object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "build_graph_intelligence",
        lambda *_args: (object(), object(), object()),
    )
    monkeypatch.setattr(
        init_pipeline,
        "create_graph_snapshot",
        lambda *_args: graph_build,
    )
    monkeypatch.setattr(
        harness,
        "load_recovery_model_layers",
        lambda *_args: (graph_build, object(), object()),
    )
    monkeypatch.setattr(
        harness,
        "prepare_model_layers",
        lambda *_args: (object(), object()),
    )

    async def run_model(*args: object) -> Path:
        received_recovery.append(args[-1])
        return tmp_path / "new-publication.json"

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", run_model)
    monkeypatch.setattr(
        init_pipeline,
        "_ensure_repository_brain_index",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        init_pipeline,
        "set_current_repository_brain",
        lambda *_args: None,
    )
    return received_recovery


def _context(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        repository_id="repository-1",
        revision="a" * 40,
        root_path=tmp_path,
    )


def _manifest(context: SimpleNamespace, **updates: str) -> SimpleNamespace:
    values = {
        "repository_id": context.repository_id,
        "repository_revision": context.revision,
        "memory_target_catalog_id": "full-catalog",
        "memory_target_catalog_version": "1",
        "graph_snapshot_id": "graph-1",
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _catalog() -> SimpleNamespace:
    return SimpleNamespace(catalog_id="full-catalog", catalog_version="1")
