"""Public init-command and canonical orchestration boundary tests."""

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import bridger.cli as cli
import bridger.init_pipeline as init_pipeline
import bridger.repository_brain.harness as harness
from bridger.contracts.files import IntakeConfiguration
from bridger.contracts.memory.core import FleetPhase
from bridger.init_pipeline import (
    InitMode,
    ReasoningEffort,
    RepositoryBrainBuildError,
    RepositoryBrainBuildResult,
    resolve_init_configuration,
)
from bridger.llm.profiles import LLMProfile
from bridger.memory import load_target_artifacts, resolve_target_activation
from bridger.memory.errors import TargetActivationError
from bridger.repository.service import prepare_repository
from bridger.repository_brain.harness import (
    _fleet_budget_for,
    _frontend_stack_present,
    _profiles,
    _target_budget_for,
    _worker_runtime_limits,
)

runner = CliRunner()
_DEFAULT_TARGETS_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "bridger"
    / "memory"
    / "default-targets"
)


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


def test_init_defaults_memory_reasoning_to_xhigh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    def build(configuration: object, **_: object) -> RepositoryBrainBuildResult:
        captured.append(configuration)
        return RepositoryBrainBuildResult(
            mode=InitMode.FULL,
            graph_build=SimpleNamespace(snapshot_root=Path("/tmp/graph")),
            publication_path=Path("/tmp/repository-brain.json"),
        )

    monkeypatch.setattr(cli, "build_repository_brain", build)

    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert captured[0].reasoning_effort is ReasoningEffort.XHIGH  # type: ignore[union-attr]


@pytest.mark.parametrize("value", list(ReasoningEffort))
def test_init_propagates_reasoning_override(
    monkeypatch: pytest.MonkeyPatch,
    value: ReasoningEffort,
) -> None:
    captured: list[object] = []

    def build(configuration: object, **_: object) -> RepositoryBrainBuildResult:
        captured.append(configuration)
        return RepositoryBrainBuildResult(
            mode=InitMode.FULL,
            graph_build=SimpleNamespace(snapshot_root=Path("/tmp/graph")),
            publication_path=Path("/tmp/repository-brain.json"),
        )

    monkeypatch.setattr(cli, "build_repository_brain", build)

    result = runner.invoke(cli.app, ["init", "--reasoning", value.value])

    assert result.exit_code == 0
    assert captured[0].reasoning_effort is value  # type: ignore[union-attr]


def test_init_rejects_invalid_reasoning_effort() -> None:
    result = runner.invoke(cli.app, ["init", "--reasoning", "invalid"])

    assert result.exit_code != 0


def test_deterministic_mode_disables_model_stages() -> None:
    configuration = resolve_init_configuration(InitMode.DETERMINISTIC)

    assert configuration.enable_model_stages is False
    assert configuration.test_budgets is False


def test_test_mode_uses_full_topology_with_reduced_budgets() -> None:
    configuration = resolve_init_configuration(InitMode.TEST)
    full_budget = _fleet_budget_for(False, target_capacity=4)
    test_budget = _fleet_budget_for(True, target_capacity=4)
    test_target_budget = _target_budget_for(True)

    assert configuration.enable_model_stages is True
    assert configuration.test_budgets is True
    assert test_budget.max_cycles < full_budget.max_cycles
    assert test_budget.max_model_calls < full_budget.max_model_calls
    assert test_budget.max_input_tokens < full_budget.max_input_tokens
    assert test_target_budget.max_input_tokens is None
    assert test_budget.max_input_tokens == 250_000
    assert test_budget.max_cycles == test_target_budget.max_cycles * 4


@pytest.mark.parametrize("test_budgets", [False, True])
def test_init_worker_profiles_keep_initial_input_within_v0_cap(
    test_budgets: bool,
) -> None:
    worker, reviewer = _profiles(
        LLMProfile(
            name="balanced",
            provider="openai",
            model="gpt-5.6-terra",
        ),
        test_budgets,
    )

    assert worker.provider_input_hard_cap_tokens <= 32_000
    assert reviewer.provider_input_hard_cap_tokens <= 32_000
    assert worker.reasoning_effort == reviewer.reasoning_effort == "xhigh"
    assert worker.model_context_window_tokens == 1_050_000
    assert reviewer.model_context_window_tokens == 1_050_000
    assert worker.provider_input_hard_cap_tokens == 32_000
    assert reviewer.provider_input_hard_cap_tokens == 32_000
    assert _worker_runtime_limits(test_budgets).active_context_soft_limit_tokens == (
        32_000 if test_budgets else 128_000
    )


@pytest.mark.parametrize("reasoning", list(ReasoningEffort))
def test_init_worker_and_reviewer_profiles_share_reasoning_policy(
    reasoning: ReasoningEffort,
) -> None:
    worker, reviewer = _profiles(
        LLMProfile(name="balanced", provider="openai", model="test-model"),
        False,
        reasoning,
    )

    expected = None if reasoning is ReasoningEffort.NONE else reasoning.value
    assert worker.reasoning_effort == reviewer.reasoning_effort == expected


@pytest.mark.parametrize(
    "dependency",
    [
        "react",
        "next",
        "vue",
        "nuxt",
        "angular",
        "@angular/core",
        "svelte",
        "@sveltejs/kit",
    ],
)
def test_frontend_framework_families_are_detected_from_dependencies(
    tmp_path: Path,
    dependency: str,
) -> None:
    repository = _repository_with_files(
        tmp_path,
        {"package.json": _package_manifest("devDependencies", dependency)},
    )
    context, file_index = prepare_repository(repository)

    assert _frontend_stack_present(
        context,
        file_index,
        SimpleNamespace(),
        SimpleNamespace(),
    )


def test_nested_workspace_manifest_activates_design_through_stage_zero(
    tmp_path: Path,
) -> None:
    repository = _repository_with_files(
        tmp_path,
        {
            "package.json": _package_manifest("devDependencies", "typescript"),
            "apps/web/package.json": _package_manifest("dependencies", "react"),
        },
    )
    context, file_index = prepare_repository(repository)
    catalog, definitions = load_target_artifacts(_DEFAULT_TARGETS_ROOT)

    active = resolve_target_activation(
        catalog,
        definitions,
        context,
        file_index,
        SimpleNamespace(),
        SimpleNamespace(),
        activation_rules={"frontend_stack_present_v1": _frontend_stack_present},
    )

    assert "design" in active


def test_frontend_mentions_and_path_names_do_not_activate_design(
    tmp_path: Path,
) -> None:
    repository = _repository_with_files(
        tmp_path,
        {
            "package.json": _package_manifest("devDependencies", "vite"),
            "src/react_helpers.ts": "export const framework = 'React';\n",
            "README.md": "This README mentions React, Vue, and Angular.\n",
        },
    )
    context, file_index = prepare_repository(repository)

    assert not _frontend_stack_present(
        context,
        file_index,
        SimpleNamespace(),
        SimpleNamespace(),
    )


def test_frontend_activation_reads_the_pinned_revision_not_dirty_manifest(
    tmp_path: Path,
) -> None:
    repository = _repository_with_files(
        tmp_path,
        {"package.json": _package_manifest("dependencies", "react")},
    )
    context, file_index = prepare_repository(repository)
    (repository / "package.json").write_text(
        _package_manifest("devDependencies", "vite"),
        encoding="utf-8",
    )

    assert _frontend_stack_present(
        context,
        file_index,
        SimpleNamespace(),
        SimpleNamespace(),
    )


def test_malformed_package_manifest_fails_deterministically(tmp_path: Path) -> None:
    repository = _repository_with_files(
        tmp_path,
        {"package.json": "{not-json\n"},
    )
    context, file_index = prepare_repository(repository)

    with pytest.raises(ValueError, match="invalid package manifest"):
        _frontend_stack_present(
            context,
            file_index,
            SimpleNamespace(),
            SimpleNamespace(),
        )


def test_unreadable_package_manifest_fails_through_stage_zero(tmp_path: Path) -> None:
    repository = _repository_with_files(
        tmp_path,
        {"package.json": _package_manifest("dependencies", "react")},
    )
    context, file_index = prepare_repository(
        repository,
        configuration=IntakeConfiguration(
            sensitive_path_patterns=("package.json",),
        ),
    )
    catalog, definitions = load_target_artifacts(_DEFAULT_TARGETS_ROOT)

    with pytest.raises(TargetActivationError, match="activation rule failed"):
        resolve_target_activation(
            catalog,
            definitions,
            context,
            file_index,
            SimpleNamespace(),
            SimpleNamespace(),
            activation_rules={"frontend_stack_present_v1": _frontend_stack_present},
        )


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
    monkeypatch.setattr(
        harness,
        "prepare_model_layers",
        lambda *_args, **_kwargs: (
            LLMProfile(name="balanced", provider="openai", model="test-model"),
            SimpleNamespace(),
        ),
    )

    async def model_stage(*_args: object) -> Path:
        return tmp_path / "published" / "repository-brain.json"

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", model_stage)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(mode, repository_root=tmp_path)
    )

    assert result.publication_path == tmp_path / "published" / "repository-brain.json"


@pytest.mark.parametrize("mode", [InitMode.FULL, InitMode.TEST])
def test_model_pipeline_prepares_enrichment_before_entering_memory_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: InitMode,
) -> None:
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "graph")
    events: list[str] = []
    enrichment = SimpleNamespace()

    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _: ("context", "index"),
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

    def prepare_layers(*_args: object, **_kwargs: object) -> tuple[object, object]:
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        events.append("enrichment")
        return SimpleNamespace(), enrichment

    async def run_memory(*args: object, **_kwargs: object) -> Path:
        asyncio.get_running_loop()
        assert events == ["enrichment"]
        assert args[-1] is enrichment
        events.append("memory")
        return tmp_path / "published" / "repository-brain.json"

    monkeypatch.setattr(harness, "prepare_model_layers", prepare_layers)
    monkeypatch.setattr(harness, "run_memory_harness", run_memory)

    result = init_pipeline.build_repository_brain(
        resolve_init_configuration(mode, repository_root=tmp_path)
    )

    assert result.publication_path == tmp_path / "published" / "repository-brain.json"
    assert events == ["enrichment", "memory"]


def test_memory_harness_closes_client_before_store_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    created_loop: asyncio.AbstractEventLoop | None = None
    closed_loop: asyncio.AbstractEventLoop | None = None

    class Client:
        async def close(self) -> None:
            nonlocal closed_loop
            closed_loop = asyncio.get_running_loop()
            events.append("client")

    class Store:
        def close(self) -> None:
            events.append("store")

    fleet_state = SimpleNamespace(phase=FleetPhase.ACCEPTED)
    monkeypatch.setattr(
        harness,
        "load_target_artifacts",
        lambda _root: (SimpleNamespace(targets=[object()]), []),
    )
    monkeypatch.setattr(
        harness,
        "_profiles",
        lambda *_args: (
            SimpleNamespace(profile_id="worker"),
            SimpleNamespace(profile_id="reviewer"),
        ),
    )
    monkeypatch.setattr(harness, "bind_memory_run", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        harness,
        "initialize_fleet",
        lambda *_args: (fleet_state, [], [], []),
    )
    monkeypatch.setattr(
        harness,
        "initialize_persistence",
        lambda *_args: Store(),
    )
    monkeypatch.setattr(harness, "RepositoryNavigator", lambda *_args: object())
    monkeypatch.setattr(harness, "build_graph_overview", lambda *_args: object())

    def create_client(_profile: LLMProfile) -> Client:
        nonlocal created_loop
        created_loop = asyncio.get_running_loop()
        return Client()

    monkeypatch.setattr(harness, "create_llm_client_from_profile", create_client)
    configuration = resolve_init_configuration(
        InitMode.FULL,
        repository_root=tmp_path,
    )
    profile = LLMProfile(
        name="test",
        provider="openai",
        model="test-model",
    )

    with pytest.raises(RepositoryBrainBuildError, match="without publication"):
        asyncio.run(
            harness.run_memory_harness(
                configuration,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                profile,
                SimpleNamespace(),
            )
        )

    assert events == ["client", "store"]
    assert created_loop is closed_loop
    assert closed_loop is not None
    assert closed_loop.is_closed()


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


def _repository_with_files(tmp_path: Path, files: dict[str, str]) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Bridger Test")
    for relative_path, content in files.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


def _package_manifest(section: str, dependency: str) -> str:
    return json.dumps({section: {dependency: "1.0.0"}}) + "\n"
