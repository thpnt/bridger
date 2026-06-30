import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bridger.cli import app

runner = CliRunner()


def test_cli_imports() -> None:
    assert app is not None


def test_init_creates_project_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

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
    assert symbol_index["schema_version"] == 1
    assert symbol_index["symbols"] == []
    repo_graph_file = tmp_path / ".bridger" / "artifacts" / "repo-graph.json"
    repo_graph = json.loads(repo_graph_file.read_text())
    assert repo_graph["schema_version"] == 1
    graph_summary_file = tmp_path / ".bridger" / "artifacts" / "graph-summary.json"
    graph_summary = json.loads(graph_summary_file.read_text())
    assert graph_summary["schema_version"] == 1
    repo_discovery_file = tmp_path / ".bridger" / "artifacts" / "repo-discovery.json"
    repo_discovery = json.loads(repo_discovery_file.read_text())
    assert repo_discovery["schema_version"] == 1
    assert len(repo_discovery["artifact_checksums"]) == 5
    assert "Bridger initialized" in result.stdout
    assert "Deterministic substrate" in result.stdout
    assert "Files" in result.stdout
    assert "Context" in result.stdout
    assert "Symbols" in result.stdout
    assert "Graph" in result.stdout
    assert "Bootstrap" in result.stdout
    assert "Artifacts written to .bridger/artifacts/" in result.stdout
    assert ".bridger/artifacts/file-index.json" not in result.stdout
    assert ".bridger/artifacts/repo-context.json" not in result.stdout
    assert ".bridger/artifacts/symbol-index.json" not in result.stdout
    assert ".bridger/artifacts/repo-graph.json" not in result.stdout
    assert ".bridger/artifacts/graph-summary.json" not in result.stdout
    assert ".bridger/artifacts/repo-discovery.json" not in result.stdout
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

    result = runner.invoke(app, ["init", "--verbose"])

    assert result.exit_code == 0
    assert "Artifacts" in result.stdout
    assert ".bridger/artifacts/file-index.json" in result.stdout
    assert ".bridger/artifacts/repo-context.json" in result.stdout
    assert ".bridger/artifacts/symbol-index.json" in result.stdout
    assert ".bridger/artifacts/repo-graph.json" in result.stdout
    assert ".bridger/artifacts/graph-summary.json" in result.stdout
    assert ".bridger/artifacts/repo-discovery.json" in result.stdout


def test_init_preserves_unreadable_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / ".bridger" / "config.json"
    config_file.parent.mkdir()
    config_file.write_text("user-authored content")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert config_file.read_text() == "user-authored content"


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


def test_inspect_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["inspect", "--graph"])

    assert result.exit_code == 0
