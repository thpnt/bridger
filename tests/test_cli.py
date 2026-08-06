import asyncio
import json
from pathlib import Path

import pytest
from test_context_plan_builder import (
    finalization_call,
    read_app_ranges_call,
    synthesis_response,
    tool_response,
    valid_plan,
)
from typer.testing import CliRunner

from bridger.cli import app
from bridger.commands import init as init_command
from bridger.deterministic.context_plan.run_state import ContextPlanRunState
from bridger.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMTimeoutError,
)
from bridger.llm.testing import DummyLLMClient
from bridger.models.context_plan import (
    ContextPlanRepository,
    ContextPlanRun,
    ContextPlanRunStatus,
)
from bridger.tools.errors import BridgerToolError

runner = CliRunner()


def test_cli_imports() -> None:
    assert app is not None


def test_init_creates_project_files_in_fresh_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--fresh"])

    assert result.exit_code == 0
    assert (tmp_path / ".bridger").is_dir()
    assert (tmp_path / ".bridger" / "config.json").is_file()
    artifact_file = tmp_path / ".bridger" / "artifacts" / "file-index.json"
    artifact = json.loads(artifact_file.read_text())
    assert artifact_file.is_file()
    assert artifact["schema_version"] == 1
    assert artifact["stats"]["files_included"] == 0
    repo_context_file = tmp_path / ".bridger" / "artifacts" / "repo-context.json"
    repo_context = json.loads(repo_context_file.read_text())
    assert repo_context_file.is_file()
    assert repo_context["schema_version"] == 1
    assert repo_context["manifests"] == []
    symbol_index_file = tmp_path / ".bridger" / "artifacts" / "symbol-index.json"
    symbol_index = json.loads(symbol_index_file.read_text())
    assert symbol_index_file.is_file()
    assert symbol_index["schema_version"] == 2
    assert symbol_index["symbols"] == []
    assert not (tmp_path / ".bridger" / "artifacts" / "repo-graph.json").exists()
    assert not (tmp_path / ".bridger" / "artifacts" / "graph-summary.json").exists()
    bootstrap_file = tmp_path / ".bridger" / "artifacts" / "context-plan-bootstrap.json"
    bootstrap = json.loads(bootstrap_file.read_text())
    assert bootstrap["schema_version"] == 1
    assert len(bootstrap["artifact_checksums"]) == 3
    assert "Repository substrate ready" in result.stdout
    assert "Deterministic substrate" in result.stdout
    assert "Files" in result.stdout
    assert "Context" in result.stdout
    assert "Symbols" in result.stdout
    assert "Bootstrap" in result.stdout
    assert "Artifacts written to .bridger/artifacts/" in result.stdout
    assert ".bridger/artifacts/file-index.json" not in result.stdout
    assert ".bridger/artifacts/repo-context.json" not in result.stdout
    assert ".bridger/artifacts/symbol-index.json" not in result.stdout
    assert ".bridger/artifacts/context-plan-bootstrap.json" not in result.stdout
    assert not (tmp_path / ".bridger" / "artifacts" / "repo-discovery.json").exists()
    assert "0 parse errors" not in result.stdout
    assert "0 unresolved imports" not in result.stdout


def test_init_fresh_sets_project_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--fresh"])
    config = json.loads((tmp_path / ".bridger" / "config.json").read_text())

    assert result.exit_code == 0
    assert config["project_mode"] == "fresh"


def test_init_verbose_shows_artifact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--fresh", "--verbose"])

    assert result.exit_code == 0
    assert "Artifacts" in result.stdout
    assert ".bridger/artifacts/file-index.json" in result.stdout
    assert ".bridger/artifacts/repo-context.json" in result.stdout
    assert ".bridger/artifacts/symbol-index.json" in result.stdout
    assert ".bridger/artifacts/context-plan-bootstrap.json" in result.stdout


def test_init_reports_unreadable_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / ".bridger" / "config.json"
    config_file.parent.mkdir()
    config_file.write_text("user-authored content")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.CONFIGURATION
    assert config_file.read_text() == "user-authored content"
    assert "Project configuration is missing or invalid" in result.stdout


def test_init_runs_context_plan_with_dummy_client_and_production_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 1\n")
    client = dummy_client_for_success()
    original_factory = init_command.create_context_plan_builder
    selected_profiles: list[str] = []

    def tracking_factory(repo_root: Path, *, llm_client, model_profile: str):
        selected_profiles.append(model_profile)
        return original_factory(
            repo_root,
            llm_client=llm_client,
            model_profile=model_profile,
        )

    monkeypatch.setattr(init_command, "create_llm_client", lambda _: client)
    monkeypatch.setattr(init_command, "create_context_plan_builder", tracking_factory)

    result = runner.invoke(app, ["init", "--llm-profile", "test-profile"])

    assert result.exit_code == 0
    assert selected_profiles == ["test-profile"]
    assert (tmp_path / ".bridger/artifacts/context-plan.json").is_file()
    assert (tmp_path / ".bridger/artifacts/context-plan-run.json").is_file()
    assert "Repository substrate ready" in result.stdout
    assert "Generating Context Plan" in result.stdout
    assert "Context Plan validated" in result.stdout
    assert "Context Plan generated" in result.stdout
    assert ".bridger/artifacts/context-plan.json" in result.stdout
    assert (
        "Memory generation and AGENTS.md generation are not implemented yet"
        in result.stdout
    )


def test_init_verbose_shows_context_plan_operational_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 1\n")
    client = dummy_client_for_success()
    monkeypatch.setattr(init_command, "create_llm_client", lambda _: client)

    result = runner.invoke(app, ["init", "--verbose"])

    assert result.exit_code == 0
    assert "Context Plan run details" in result.stdout
    assert "Model turns" in result.stdout
    assert "Input tokens" in result.stdout
    assert "Finalization requests" in result.stdout
    assert "Repository bootstrap facts" not in result.stdout
    assert "OPENAI_API_KEY" not in result.stdout


@pytest.mark.parametrize(
    ("error", "exit_code", "expected"),
    [
        (LLMConfigurationError("profile is invalid"), 2, "profile is invalid"),
        (LLMAuthenticationError("authentication failed"), 4, "authentication failed"),
        (LLMTimeoutError("request timed out"), 4, "request timed out"),
        (
            LLMProviderError(
                "OpenAI request failed with code invalid_function_parameters: "
                "Invalid schema for function 'inspect_repo_discovery'."
            ),
            4,
            "inspect_repo_discovery",
        ),
    ],
)
def test_init_maps_llm_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    exit_code: int,
    expected: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_error(_: str):
        raise error

    monkeypatch.setattr(init_command, "create_llm_client", raise_error)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == exit_code
    assert expected in result.stdout
    assert "Context Plan generation failed" in result.stdout


def test_init_maps_missing_artifact_to_prerequisite_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_command, "create_llm_client", lambda _: DummyLLMClient([]))

    def missing_artifact(*args, **kwargs):
        raise BridgerToolError("artifact_missing", "Required artifact is missing")

    monkeypatch.setattr(init_command, "create_context_plan_builder", missing_artifact)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.PREREQUISITES
    assert "Required artifact is missing" in result.stdout


def test_init_maps_incompatible_tree_sitter_to_prerequisite_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def incompatible_tree_sitter(*args, **kwargs):
        raise init_command.TreeSitterCompatibilityError(
            "Tree-sitter 0.26.0 is incompatible with Bridger's language bindings."
        )

    monkeypatch.setattr(
        init_command,
        "build_symbol_index_for_project",
        incompatible_tree_sitter,
    )

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.PREREQUISITES
    assert "Tree-sitter 0.26.0 is incompatible" in result.stdout
    assert "Reinstall Bridger so tree-sitter 0.25.x is selected" in result.stdout


def test_init_maps_artifact_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(init_command, "write_artifact", fail_write)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.ARTIFACT_WRITE
    assert "Could not write a Bridger artifact" in result.stdout


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ContextPlanRunStatus.BUDGET_EXHAUSTED, "Discovery budget was exhausted"),
        (ContextPlanRunStatus.STALLED, "Discovery stalled without sufficient progress"),
    ],
)
def test_init_maps_terminal_discovery_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: ContextPlanRunStatus,
    expected: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    state = ContextPlanRunState(
        run_id="run-terminal",
        repo=ContextPlanRepository(root_name="fixture", revision=None),
        safe_file_count=0,
    )
    state.start()
    if status is ContextPlanRunStatus.BUDGET_EXHAUSTED:
        state.mark_budget_exhausted()
    else:
        state.mark_stalled()
    run = state.snapshot()

    class FixedRunBuilder:
        async def build(self, *, run_id: str) -> ContextPlanRun:
            return run

    monkeypatch.setattr(init_command, "create_llm_client", lambda _: DummyLLMClient([]))
    monkeypatch.setattr(
        init_command,
        "create_context_plan_builder",
        lambda *args, **kwargs: FixedRunBuilder(),
    )

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.BUDGET_OR_STALLED
    assert expected in result.stdout


def test_init_maps_unexpected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_unexpected(_: str):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(init_command, "create_llm_client", fail_unexpected)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.UNEXPECTED
    assert "An unexpected internal error occurred" in result.stdout
    assert "secret internal detail" not in result.stdout


def test_init_interruption_persists_run_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 1\n")
    monkeypatch.setattr(
        init_command,
        "create_llm_client",
        lambda _: DummyLLMClient([asyncio.CancelledError()]),
    )

    result = runner.invoke(app, ["init"])

    run_path = tmp_path / ".bridger/artifacts/context-plan-run.json"
    run = ContextPlanRun.model_validate_json(run_path.read_bytes())
    assert result.exit_code == init_command.InitExitCode.INTERRUPTED
    assert run.status.value == "interrupted"
    assert "Run record: .bridger/artifacts/context-plan-run.json" in result.stdout
    assert "Context Plan generated" not in result.stdout


def test_init_preserves_existing_context_plan_after_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 1\n")
    artifacts = tmp_path / ".bridger/artifacts"
    artifacts.mkdir(parents=True)
    plan_path = artifacts / "context-plan.json"
    plan_path.write_bytes(b"previous valid plan")
    client = DummyLLMClient(
        [
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call()),
            synthesis_response(valid_plan(line_end=99)),
            synthesis_response(valid_plan(line_end=99)),
        ]
    )
    monkeypatch.setattr(init_command, "create_llm_client", lambda _: client)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == init_command.InitExitCode.VALIDATION
    assert plan_path.read_bytes() == b"previous valid plan"
    assert "Run record: .bridger/artifacts/context-plan-run.json" in result.stdout


def dummy_client_for_success() -> DummyLLMClient:
    return DummyLLMClient(
        [
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call()),
            synthesis_response(valid_plan()),
        ]
    )


def test_update() -> None:
    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0


def test_prompt_includes_task() -> None:
    result = runner.invoke(app, ["prompt", "Add auth"])

    assert result.exit_code == 0
    assert "Add auth" in result.stdout


def test_inspect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["inspect"])

    assert result.exit_code == 0
