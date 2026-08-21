"""Public init-command and canonical orchestration boundary tests."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import cli
import init_pipeline
from init_pipeline import (
    InitMode,
    RepositoryBrainBuildError,
    RepositoryBrainBuildResult,
    resolve_init_configuration,
)
from repository_brain.harness import _budget_for

runner = CliRunner()


@pytest.mark.parametrize(
    ("arguments", "expected_mode"),
    [
        ([], InitMode.FULL),
        (["--mode", "full"], InitMode.FULL),
        (["--mode", "test"], InitMode.TEST),
    ],
)
def test_init_resolves_the_requested_mode(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected_mode: InitMode,
) -> None:
    captured: list[object] = []

    def build(
        configuration: object,
        **_: object,
    ) -> RepositoryBrainBuildResult:
        captured.append(configuration)
        return RepositoryBrainBuildResult(
            mode=expected_mode,
            graph_build=SimpleNamespace(snapshot_root=Path("/tmp/graph")),
            publication_path=Path("/tmp/repository-brain.json"),
        )

    monkeypatch.setattr(cli, "build_repository_brain", build)

    result = runner.invoke(cli.app, ["init", *arguments])

    assert result.exit_code == 0
    assert captured[0].mode is expected_mode  # type: ignore[union-attr]


def test_deterministic_mode_disables_model_stages() -> None:
    configuration = resolve_init_configuration(InitMode.DETERMINISTIC)

    assert configuration.enable_model_stages is False
    assert configuration.test_budgets is False


def test_test_mode_uses_full_topology_with_reduced_budgets() -> None:
    configuration = resolve_init_configuration(InitMode.TEST)
    full_budget = _budget_for(False)
    test_budget = _budget_for(True)

    assert configuration.enable_model_stages is True
    assert configuration.test_budgets is True
    assert test_budget.max_cycles < full_budget.max_cycles
    assert test_budget.max_model_calls < full_budget.max_model_calls
    assert test_budget.max_input_tokens < full_budget.max_input_tokens


def test_deterministic_pipeline_never_enters_model_stages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "graph")
    calls: list[str] = []

    monkeypatch.setattr(
        init_pipeline, "prepare_repository", lambda _: ("context", "index")
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: ("symbols", "report", "extraction"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "build_graph_intelligence",
        lambda *_args, **_kwargs: ("graph", "diagnostics", "structural"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "create_graph_snapshot",
        lambda *_args, **_kwargs: graph_build,
    )

    async def model_stage(*_args: object) -> Path:
        calls.append("model")
        raise AssertionError("deterministic mode must not run model stages")

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", model_stage)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(InitMode.DETERMINISTIC, repository_root=tmp_path)
    )

    assert result.graph_build is graph_build
    assert result.publication_path is None
    assert calls == []


@pytest.mark.parametrize("mode", [InitMode.FULL, InitMode.TEST])
def test_model_modes_enter_the_shared_full_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: InitMode,
) -> None:
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "graph")
    monkeypatch.setattr(
        init_pipeline, "prepare_repository", lambda _: ("context", "index")
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: ("symbols", "report", "extraction"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "build_graph_intelligence",
        lambda *_args, **_kwargs: ("graph", "diagnostics", "structural"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "create_graph_snapshot",
        lambda *_args, **_kwargs: graph_build,
    )

    async def model_stage(*_args: object) -> Path:
        return tmp_path / "published" / "repository-brain.json"

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", model_stage)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(mode, repository_root=tmp_path)
    )

    assert result.publication_path == tmp_path / "published" / "repository-brain.json"


def test_init_surfaces_pipeline_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_: object, **__: object) -> RepositoryBrainBuildResult:
        raise RepositoryBrainBuildError("provider unavailable")

    monkeypatch.setattr(cli, "build_repository_brain", fail)

    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 1
    assert "provider unavailable" in result.output


def test_invalid_mode_fails_cleanly() -> None:
    result = runner.invoke(cli.app, ["init", "--mode", "invalid"])

    assert result.exit_code == 2
    assert "Invalid value for '--mode'" in result.output


def test_deterministic_command_builds_a_real_graph_without_model_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Bridger Test")
    (repository / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    _git(repository, "add", "app.py")
    _git(repository, "commit", "-m", "initial")
    monkeypatch.chdir(repository)

    result = runner.invoke(cli.app, ["init", "--mode", "deterministic"])

    assert result.exit_code == 0, result.output
    assert (repository / ".bridger" / "graph" / "current").is_file()
    assert "Deterministic graph snapshot published" in result.output


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
