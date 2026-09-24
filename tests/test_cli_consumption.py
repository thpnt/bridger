"""CLI adapter tests for canonical consumption commands."""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text
from typer.testing import CliRunner

import bridger.cli as cli
from bridger.contracts.consumption import (
    Completeness,
    ConsumptionRevision,
    ImpactGraph,
    ImpactResolutionIssue,
    ImpactResult,
    UnderstandGraphContext,
    UnderstandResult,
)
from bridger.presentation import render_intelligence_json, render_intelligence_markdown

runner = CliRunner()
_REVISION = ConsumptionRevision(
    repository_id="repo",
    repository_revision="a" * 40,
    graph_snapshot_id="graph",
    enrichment_overlay_id="overlay",
)


def _understand(*, truncated: bool = False) -> UnderstandResult:
    return UnderstandResult(
        query="How does auth work?",
        revision=_REVISION,
        graph_context=UnderstandGraphContext(),
        completeness=Completeness(brain_truncated=truncated),
    )


def _impact(*, unresolved: bool = False) -> ImpactResult:
    return ImpactResult(
        revision=_REVISION,
        requested_symbols=["AuthService"],
        resolution_issues=(
            [ImpactResolutionIssue(selector="AuthService", reason="ambiguous")]
            if unresolved
            else []
        ),
        affected_graph=None if unresolved else ImpactGraph(),
        completeness=Completeness(),
    )


class _Navigator:
    def __init__(self, result: UnderstandResult | ImpactResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, object]] = []
        self.closed = False

    def __enter__(self) -> _Navigator:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def understand(self, query: str) -> UnderstandResult:
        self.calls.append(("understand", query))
        if isinstance(self.result, Exception):
            raise self.result
        assert isinstance(self.result, UnderstandResult)
        return self.result

    def impact(self, symbols: list[str]) -> ImpactResult:
        self.calls.append(("impact", list(symbols)))
        if isinstance(self.result, Exception):
            raise self.result
        assert isinstance(self.result, ImpactResult)
        return self.result


def test_understand_delegates_once_from_current_nested_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    navigator = _Navigator(_understand())
    requested_roots: list[Path] = []
    nested = tmp_path / "packages" / "api"
    nested.mkdir(parents=True)
    monkeypatch.setattr(cli.Path, "cwd", lambda: nested)

    class Context:
        def __enter__(self) -> _Navigator:
            return navigator

        def __exit__(self, *_: object) -> None:
            navigator.closed = True

    def load(root: Path) -> Context:
        requested_roots.append(root)
        return Context()

    monkeypatch.setattr(cli, "load_bridger_navigator", load)
    result = runner.invoke(cli.app, ["understand", "How does auth work?"])

    assert result.exit_code == 0
    assert requested_roots == [nested]
    assert navigator.calls == [("understand", "How does auth work?")]
    assert navigator.closed
    assert result.stdout == render_intelligence_markdown(navigator.result)


def test_impact_preserves_positional_symbol_order(monkeypatch) -> None:
    navigator = _Navigator(_impact())
    monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)

    result = runner.invoke(cli.app, ["impact", "AuthService", "validate_token"])

    assert result.exit_code == 0
    assert navigator.calls == [("impact", ["AuthService", "validate_token"])]
    assert navigator.closed


def test_json_output_is_canonical_for_both_commands(monkeypatch) -> None:
    for command, result_model, arguments in (
        ("understand", _understand(), ["How does auth work?"]),
        ("impact", _impact(), ["AuthService"]),
    ):
        navigator = _Navigator(result_model)
        monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)
        result = runner.invoke(cli.app, [command, *arguments, "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == render_intelligence_json(result_model)
        assert "\x1b[" not in result.stdout
        assert navigator.closed


def test_interactive_markdown_uses_rich_console(monkeypatch) -> None:
    navigator = _Navigator(_understand())
    monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)
    calls: list[object] = []

    class InteractiveConsole:
        is_terminal = True

        def print(self, value: object, **_: object) -> None:
            calls.append(value)

    monkeypatch.setattr(cli, "console", InteractiveConsole())
    result = runner.invoke(cli.app, ["understand", "How does auth work?"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0].__class__.__name__ == "Markdown"


def test_unresolved_impact_and_truncated_understand_are_successful(monkeypatch) -> None:
    for command, result_model, arguments in (
        ("impact", _impact(unresolved=True), ["AuthService"]),
        ("understand", _understand(truncated=True), ["How does auth work?"]),
    ):
        navigator = _Navigator(result_model)
        monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)
        result = runner.invoke(cli.app, [command, *arguments])

        assert result.exit_code == 0
        assert result.stdout == render_intelligence_markdown(result_model)


def test_operation_failures_go_to_stderr_and_close_navigator(monkeypatch) -> None:
    for command, arguments in (
        ("understand", ["question"]),
        ("impact", ["AuthService"]),
    ):
        navigator = _Navigator(RuntimeError("retrieval failed"))
        monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)

        result = runner.invoke(cli.app, [command, *arguments])

        assert result.exit_code == 1
        assert result.stdout == ""
        assert "Error: retrieval failed" in result.stderr
        assert navigator.closed


def test_interactive_operation_failure_uses_stderr_rich_console(monkeypatch) -> None:
    calls: list[object] = []

    class InteractiveErrorConsole:
        is_terminal = True

        def print(self, value: object) -> None:
            calls.append(value)

    monkeypatch.setattr(cli, "error_console", InteractiveErrorConsole())
    navigator = _Navigator(RuntimeError("unsupported snapshot manifest schema"))
    monkeypatch.setattr(cli, "load_bridger_navigator", lambda _: navigator)

    result = runner.invoke(cli.app, ["understand", "question"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert len(calls) == 1
    assert isinstance(calls[0], Text)
    assert calls[0].plain == "Error: unsupported snapshot manifest schema"
    assert calls[0].style.bold
    assert calls[0].style.color.name == "red"


def test_bootstrap_failure_is_reported_on_stderr(monkeypatch) -> None:
    def fail(_: Path) -> _Navigator:
        raise ValueError("not inside repository")

    monkeypatch.setattr(cli, "load_bridger_navigator", fail)
    result = runner.invoke(cli.app, ["impact", "AuthService"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Error: not inside repository" in result.stderr


def test_impact_requires_at_least_one_symbol() -> None:
    result = runner.invoke(cli.app, ["impact"])

    assert result.exit_code != 0
    assert "Missing argument" in result.output
