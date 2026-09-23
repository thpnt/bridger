"""MCP adapter contract and stdio boundary tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent
from typer.testing import CliRunner

import bridger.mcp_server as adapter
from bridger.cli import app
from bridger.contracts.consumption import (
    Completeness,
    ConsumptionRevision,
    ImpactResolutionIssue,
    ImpactResult,
    UnderstandGraphContext,
    UnderstandResult,
)
from bridger.presentation import render_intelligence_markdown
from bridger.repository_brain.loader import RepositoryBrainLoadError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("# Fixture\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        check=True,
    )
    (tmp_path / "src" / "nested").mkdir(parents=True)
    return tmp_path


class _Navigator:
    def __init__(self) -> None:
        self.understand_calls: list[str] = []
        self.impact_calls: list[list[str]] = []
        self.close_calls = 0
        revision = ConsumptionRevision(
            repository_id="fixture",
            repository_revision="a" * 40,
            graph_snapshot_id="graph",
            enrichment_overlay_id="overlay",
        )
        self.understand_result = UnderstandResult(
            query="where",
            revision=revision,
            graph_context=UnderstandGraphContext(),
            completeness=Completeness(),
        )
        self.impact_result = ImpactResult(
            revision=revision,
            requested_symbols=["CallManager"],
            resolution_issues=[
                ImpactResolutionIssue(selector="CallManager", reason="ambiguous")
            ],
            completeness=Completeness(),
        )

    def understand(self, query: str) -> UnderstandResult:
        self.understand_calls.append(query)
        return self.understand_result

    def impact(self, symbols: list[str]) -> ImpactResult:
        self.impact_calls.append(symbols)
        return self.impact_result

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.anyio
async def test_tools_are_lazy_delegate_and_close_once(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigator = _Navigator()
    loaded: list[Path] = []

    def load(root: Path) -> _Navigator:
        loaded.append(root)
        return navigator

    monkeypatch.setattr(adapter, "load_bridger_navigator", load)
    server = adapter.create_mcp_server(repository)
    assert loaded == []
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {"understand", "impact"}
        assert all(tool.output_schema is None for tool in tools)
        assert set(tools[0].input_schema["properties"]) in ({"query"}, {"symbols"})
        assert loaded == []

        for _ in range(2):
            result = await client.call_tool("understand", {"query": "where"})
            assert result.is_error is not True
            assert result.structured_content is None
            assert result.content == [
                TextContent(
                    type="text",
                    text=render_intelligence_markdown(navigator.understand_result),
                )
            ]

        result = await client.call_tool("impact", {"symbols": ["CallManager"]})
        assert result.is_error is not True
        assert result.structured_content is None
        assert result.content[0].text == render_intelligence_markdown(
            navigator.impact_result
        )
        assert "ambiguous" in result.content[0].text
        assert loaded == [repository]
        assert navigator.understand_calls == ["where", "where"]
        assert navigator.impact_calls == [["CallManager"]]
    assert navigator.close_calls == 1


@pytest.mark.anyio
async def test_unused_navigator_is_never_opened_or_closed(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        adapter, "load_bridger_navigator", lambda _root: pytest.fail("loaded")
    )
    async with Client(adapter.create_mcp_server(repository)) as client:
        assert len((await client.list_tools()).tools) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        ValueError("no current Repository Brain publication exists"),
        ValueError("active repository revision does not match the selected Brain"),
        RepositoryBrainLoadError("could not load a coherent published Brain"),
        RuntimeError("crashed"),
    ],
)
async def test_adapter_failures_are_tool_errors(
    repository: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fail(_root: Path) -> _Navigator:
        raise failure

    monkeypatch.setattr(adapter, "load_bridger_navigator", fail)
    async with Client(adapter.create_mcp_server(repository)) as client:
        result = await client.call_tool("understand", {"query": "where"})
        assert result.is_error is True
        assert result.structured_content is None


@pytest.mark.anyio
async def test_invalid_query_is_an_actionable_tool_error(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    navigator = _Navigator()

    def invalid(_query: str) -> UnderstandResult:
        raise ValueError("query must be non-empty")

    navigator.understand = invalid  # type: ignore[method-assign]
    monkeypatch.setattr(adapter, "load_bridger_navigator", lambda _root: navigator)
    async with Client(adapter.create_mcp_server(repository)) as client:
        result = await client.call_tool("understand", {"query": ""})
        assert result.is_error is True
        assert "query must be non-empty" in result.content[0].text


@pytest.mark.parametrize("location", [".", "src/nested"])
def test_launcher_resolves_root_from_default_and_override(
    repository: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    selected: list[Path] = []

    class _Server:
        def run(self, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(
        adapter, "create_mcp_server", lambda root: selected.append(root) or _Server()
    )
    requested = repository / location
    adapter.run_mcp_server(requested)
    assert selected == [repository]

    selected.clear()
    monkeypatch.chdir(requested)
    monkeypatch.setattr(adapter, "run_mcp_server", lambda path: selected.append(path))
    assert CliRunner().invoke(app, ["mcp"]).exit_code == 0
    assert selected == [requested]
    assert (
        CliRunner().invoke(app, ["mcp", "--repository", str(requested)]).exit_code == 0
    )
    assert selected == [requested, requested]


def test_invalid_repository_exits_without_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        adapter.run_mcp_server(tmp_path)
    output = capsys.readouterr()
    assert error.value.code == 1
    assert output.out == ""
    assert "not a Git repository" in output.err


@pytest.mark.anyio
async def test_real_stdio_subprocess_lists_tools_and_returns_tool_error(
    repository: Path,
) -> None:
    executable = Path(sys.executable).with_name("bridger")
    assert executable.is_file()
    parameters = StdioServerParameters(
        command=str(executable),
        args=["mcp", "--repository", str(repository / "src" / "nested")],
    )
    async with Client(parameters) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {"understand", "impact"}
        result = await client.call_tool("understand", {"query": "where"})
        assert result.is_error is True
        assert "no current Repository Brain publication" in result.content[0].text
