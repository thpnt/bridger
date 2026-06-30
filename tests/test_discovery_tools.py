import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agents.tool_context import ToolContext

from bridger.artifacts import write_artifact
from bridger.deterministic.repo_discovery.builder import AVAILABLE_TOOLS
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)
from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    FanInFile,
    FanOutFile,
    GraphSummaryArtifact,
    GraphSummaryCounts,
)
from bridger.models.repo_context import (
    CiFile,
    CiKind,
    ConfigFile,
    ConfigKind,
    DocsFile,
    DocsKind,
    InstructionFile,
    InstructionKind,
    ManifestFile,
    ManifestKind,
    RepoContextArtifact,
)
from bridger.models.repo_discovery import (
    RepoDiscoveryArtifact,
    RepoDiscoveryArtifacts,
    RepoDiscoveryBudgets,
    RepoDiscoveryCompactContext,
    RepoDiscoveryRepo,
)
from bridger.models.repo_graph import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    RepoGraphArtifact,
)
from bridger.models.symbol_index import SymbolIndexArtifact, SymbolKind, SymbolRecord
from bridger.tools.context import BridgerToolContext, build_tool_context
from bridger.tools.definitions.files import read_file_excerpt
from bridger.tools.errors import BridgerToolError
from bridger.tools.models import FileFilters, GrepFilters
from bridger.tools.registry import get_discovery_tools
from bridger.tools.services import ArtifactStore, BudgetService, PathSafetyService

GENERATED_AT = datetime(2026, 6, 19, tzinfo=UTC)
EXPECTED_TOOLS = [
    "inspect_repo_discovery",
    "list_files",
    "list_tree",
    "search_paths",
    "grep_contents",
    "read_file_excerpt",
    "inspect_manifest",
    "list_config_files",
    "list_docs_files",
    "list_instruction_files",
    "list_ci_files",
    "search_symbols",
    "list_symbols",
    "get_symbol",
    "read_symbol_excerpt",
    "get_file_overview",
    "get_graph_neighbors",
    "get_reverse_imports",
    "list_file_imports",
    "list_declared_entrypoints",
    "inspect_graph_summary",
    "validate_paths",
]


def indexed_file(root: Path, path: str) -> IndexedFile:
    content = (root / path).read_bytes()
    return IndexedFile(
        path=path,
        extension=Path(path).suffix,
        size_bytes=len(content),
        line_count=len(content.decode().splitlines()),
        sha256="0" * 64,
        is_binary=False,
        is_symlink=False,
        detected_encoding="utf-8",
    )


@pytest.fixture
def tool_repo(tmp_path: Path) -> tuple[Path, BridgerToolContext]:
    contents = {
        "src/app.py": (
            "from src.util import helper\n\ndef main():\n    return helper()\n"
        ),
        "src/util.py": "def helper():\n    return 'needle'\n",
        "pyproject.toml": "[project]\nname = 'fixture'\n",
        "ruff.toml": "line-length = 88\n",
        "README.md": "fixture docs\n",
        "AGENTS.md": "fixture instructions\n",
        ".github/workflows/test.yml": "name: test\n",
    }
    for path, content in contents.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    files = [indexed_file(tmp_path, path) for path in sorted(contents)]
    file_index = FileIndexArtifact(
        generated_at=GENERATED_AT,
        repo_root_name="fixture",
        files=files,
        skipped_files=[SkippedFile(path=".env", skip_reason=SkipReason.SENSITIVE_FILE)],
        stats=FileIndexStats(
            files_seen=len(files) + 1,
            files_included=len(files),
            files_skipped=1,
            total_included_bytes=sum(item.size_bytes for item in files),
        ),
    )
    repo_context = RepoContextArtifact(
        generated_at=GENERATED_AT,
        manifests=[
            ManifestFile(
                path="pyproject.toml",
                kind=ManifestKind.PYTHON_PYPROJECT,
                parsed={"project_name": "fixture"},
            )
        ],
        config_files=[ConfigFile(path="ruff.toml", kind=ConfigKind.PYTHON_TOOL_CONFIG)],
        ci_files=[
            CiFile(
                path=".github/workflows/test.yml",
                kind=CiKind.GITHUB_ACTIONS_WORKFLOW,
            )
        ],
        instruction_files=[
            InstructionFile(path="AGENTS.md", kind=InstructionKind.AGENT_INSTRUCTIONS)
        ],
        docs_files=[DocsFile(path="README.md", kind=DocsKind.README)],
        parse_errors=[],
    )
    symbols = SymbolIndexArtifact(
        generated_at=GENERATED_AT,
        symbols=[
            SymbolRecord(
                id="sym:src/app.py:3:main",
                path="src/app.py",
                name="main",
                kind=SymbolKind.FUNCTION,
                line_start=3,
                line_end=4,
                declaration="def main()",
                extractor="tree_sitter_python",
            ),
            SymbolRecord(
                id="sym:src/util.py:1:helper",
                path="src/util.py",
                name="helper",
                kind=SymbolKind.FUNCTION,
                line_start=1,
                line_end=2,
                declaration="def helper()",
                extractor="tree_sitter_python",
            ),
        ],
        parse_errors=[],
    )
    graph = RepoGraphArtifact(
        generated_at=GENERATED_AT,
        nodes=[
            GraphNode(id="file:src/app.py", kind=GraphNodeKind.FILE, path="src/app.py"),
            GraphNode(
                id="file:src/util.py", kind=GraphNodeKind.FILE, path="src/util.py"
            ),
            GraphNode(
                id="manifest:pyproject.toml:project.scripts.fixture",
                kind=GraphNodeKind.MANIFEST_ENTRY,
                path="pyproject.toml",
                key="project.scripts.fixture",
            ),
        ],
        edges=[
            GraphEdge(
                from_id="file:src/app.py",
                to_id="file:src/util.py",
                kind=GraphEdgeKind.IMPORTS,
                import_text="from src.util import helper",
            ),
            GraphEdge(
                from_id="manifest:pyproject.toml:project.scripts.fixture",
                to_id="file:src/app.py",
                kind=GraphEdgeKind.DECLARES_ENTRYPOINT,
            ),
        ],
    )
    summary = GraphSummaryArtifact(
        generated_at=GENERATED_AT,
        counts=GraphSummaryCounts(file_nodes=2, import_edges=1),
        top_fan_in_files=[FanInFile(path="src/util.py", incoming_edges=1)],
        top_fan_out_files=[FanOutFile(path="src/app.py", outgoing_edges=1)],
        declared_entrypoints=[
            DeclaredEntrypointSummary(
                path="src/app.py", source="pyproject.toml:project.scripts.fixture"
            )
        ],
    )
    budgets = RepoDiscoveryBudgets(
        max_files_read=3,
        max_excerpts=5,
        max_grep_results=1,
        max_symbol_results=1,
        max_graph_neighbors=1,
        max_file_excerpt_lines=2,
    )
    discovery = RepoDiscoveryArtifact(
        generated_at=GENERATED_AT,
        repo=RepoDiscoveryRepo(root_name="fixture", revision="test"),
        artifacts=RepoDiscoveryArtifacts(
            file_index=".bridger/artifacts/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
            repo_graph=".bridger/artifacts/repo-graph.json",
            graph_summary=".bridger/artifacts/graph-summary.json",
        ),
        artifact_checksums={
            name: "0" * 64
            for name in [
                "file-index.json",
                "repo-context.json",
                "symbol-index.json",
                "repo-graph.json",
                "graph-summary.json",
            ]
        },
        compact_context=RepoDiscoveryCompactContext(
            file_count=len(files),
            skipped_file_count=1,
            manifest_files=["pyproject.toml"],
            config_files=["ruff.toml"],
            instruction_files=["AGENTS.md"],
            docs_files=["README.md"],
            ci_files=[".github/workflows/test.yml"],
            declared_entrypoints=summary.declared_entrypoints,
            graph_counts=summary.counts,
        ),
        available_tools=AVAILABLE_TOOLS,
        budgets=budgets,
    )
    artifacts = {
        "file-index.json": file_index,
        "repo-context.json": repo_context,
        "symbol-index.json": symbols,
        "repo-graph.json": graph,
        "graph-summary.json": summary,
        "repo-discovery.json": discovery,
    }
    for name, artifact in artifacts.items():
        write_artifact(tmp_path / ".bridger" / "artifacts" / name, artifact)
    return tmp_path, build_tool_context(tmp_path)


def test_artifact_store_loads_all_artifacts_and_caches(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, _ = tool_repo
    store = ArtifactStore(root)

    first = store.load_file_index()

    assert first is store.load_file_index()
    assert store.load_repo_context().manifests
    assert store.load_symbol_index().symbols
    assert store.load_repo_graph().edges
    assert store.load_graph_summary().counts.import_edges == 1
    assert store.load_repo_discovery().repo.root_name == "fixture"


def test_artifact_store_reports_missing_and_invalid(tmp_path: Path) -> None:
    with pytest.raises(BridgerToolError, match="file-index.json") as missing:
        ArtifactStore(tmp_path).load_file_index()
    assert missing.value.payload.error == "artifact_missing"

    path = tmp_path / ".bridger" / "artifacts" / "file-index.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(BridgerToolError) as invalid:
        ArtifactStore(tmp_path).load_file_index()
    assert invalid.value.payload.error == "artifact_invalid"


@pytest.mark.parametrize("path", ["/src/app.py", "../src/app.py", "src\\app.py"])
def test_path_safety_rejects_unsafe_paths(
    tool_repo: tuple[Path, BridgerToolContext], path: str
) -> None:
    _, context = tool_repo
    with pytest.raises(BridgerToolError) as error:
        context.path_safety.validate_file(path)
    assert error.value.payload.error == "invalid_path"


def test_path_safety_accepts_safe_path_and_rejects_skipped_unknown_and_prefix(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    assert context.path_safety.validate_file("src/app.py") == "src/app.py"
    assert context.path_safety.validate_prefix("src") == "src"
    with pytest.raises(BridgerToolError) as skipped:
        context.path_safety.validate_file(".env")
    assert skipped.value.payload.error == "path_skipped"
    with pytest.raises(BridgerToolError) as unknown:
        context.path_safety.validate_file("missing.py")
    assert unknown.value.payload.error == "path_not_indexed"
    with pytest.raises(BridgerToolError):
        context.path_safety.validate_prefix("missing")


def test_budget_service_uses_defaults_and_caps_requested_limits() -> None:
    defaults = BudgetService()
    custom = BudgetService(RepoDiscoveryBudgets(max_grep_results=2))
    assert defaults.values == RepoDiscoveryBudgets()
    assert custom.grep_limit(10) == 2
    assert custom.grep_limit(1) == 1


def test_file_inventory_tree_search_and_validation_are_bounded(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    listed = context.file_index.list_files(FileFilters(extension=".py"))
    tree = context.file_index.list_tree("src", depth=1, limit=1)
    searched = context.file_index.search_paths("src/")
    validated = context.file_index.validate_paths(["src/app.py", ".env", "none.py"])

    assert [item["path"] for item in listed["files"]] == ["src/app.py", "src/util.py"]
    assert tree["truncated"] is True
    assert tree["entries"] == [{"path": "src/app.py", "kind": "file"}]
    assert searched["total_matches"] == 2
    assert [item["valid"] for item in validated["results"]] == [True, False, False]


def test_file_excerpt_and_grep_enforce_budgets(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    excerpt = context.file_read.read_excerpt("src/app.py", 2, 4)
    grep = context.search.grep("return", GrepFilters())

    assert excerpt["line_start"] == 2
    assert excerpt["line_end"] == 3
    assert excerpt["truncated"] is True
    assert grep["total_matches"] == 2
    assert len(grep["results"]) == 1
    assert grep["truncated"] is True
    assert {"path", "line_number", "match"} <= set(grep["results"][0])


def test_file_read_rejects_indexed_path_replaced_by_outside_symlink(
    tool_repo: tuple[Path, BridgerToolContext], tmp_path: Path
) -> None:
    root, context = tool_repo
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret\n")
    indexed = root / "src" / "app.py"
    indexed.unlink()
    indexed.symlink_to(outside)

    with pytest.raises(BridgerToolError) as error:
        context.file_read.read_excerpt("src/app.py")

    assert error.value.payload.error == "invalid_path"


def test_repo_context_services_return_only_factual_indexed_entries(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    assert context.repo_context.inspect_manifest("pyproject.toml")["manifest"][
        "parsed"
    ] == {"project_name": "fixture"}
    assert context.repo_context.list_config_files()["config_files"]
    assert context.repo_context.list_docs_files()["docs_files"]
    assert context.repo_context.list_instruction_files()["instruction_files"]
    assert context.repo_context.list_ci_files()["ci_files"]
    with pytest.raises(BridgerToolError) as error:
        context.repo_context.inspect_manifest("src/app.py")
    assert error.value.payload.error == "manifest_not_found"


def test_symbol_services_are_bounded_and_support_safe_excerpts(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    searched = context.symbols.search("def")
    listed = context.symbols.list_for_path("src/app.py")
    symbol = context.symbols.get("sym:src/app.py:3:main")
    excerpt = context.file_read.read_excerpt(
        symbol.path, symbol.line_start, symbol.line_end
    )

    assert searched["total_matches"] == 2
    assert len(searched["symbols"]) == 1
    assert listed["symbols"][0]["id"] == symbol.id
    assert excerpt["content"] == "def main():\n    return helper()"
    with pytest.raises(BridgerToolError) as error:
        context.symbols.get("missing")
    assert error.value.payload.error == "symbol_not_found"


def test_graph_services_return_only_structural_facts(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    imports = context.graph.imports("src/app.py")
    reverse = context.graph.reverse_imports("src/util.py")
    neighbors = context.graph.neighbors("src/app.py")
    entrypoints = context.graph.declared_entrypoints()
    summary = context.graph_summary.inspect()

    assert imports["imports"][0]["path"] == "src/util.py"
    assert reverse["imported_by"][0]["path"] == "src/app.py"
    assert neighbors["neighbors"][0]["kind"] == "declares_entrypoint"
    assert entrypoints["entrypoints"][0]["path"] == "src/app.py"
    assert summary["summary"]["counts"]["import_edges"] == 1
    forbidden = {"summary_text", "role", "domain", "architecture"}
    serialized = json.dumps([imports, reverse, neighbors, summary])
    assert all(field not in serialized for field in forbidden)


def invoke_tool(
    context: BridgerToolContext, name: str, arguments: dict[str, object]
) -> dict[str, object]:
    tool = next(item for item in get_discovery_tools() if item.name == name)
    tool_context = ToolContext(
        context=context,
        tool_name=name,
        tool_call_id="test",
        tool_arguments=json.dumps(arguments),
    )
    result = asyncio.run(tool.on_invoke_tool(tool_context, json.dumps(arguments)))
    assert isinstance(result, dict)
    return result


def test_wrappers_compose_services_and_serialize_errors(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    symbol_result = invoke_tool(
        context,
        "read_symbol_excerpt",
        {"symbol_id": "sym:src/app.py:3:main", "context_lines": 1},
    )
    overview = invoke_tool(context, "get_file_overview", {"path": "src/app.py"})
    invalid = invoke_tool(context, "read_file_excerpt", {"path": "/etc/passwd"})

    assert symbol_result["ok"] is True
    assert symbol_result["symbol"]["id"] == "sym:src/app.py:3:main"
    assert symbol_result["excerpt"]["path"] == "src/app.py"
    assert overview["file"]["path"] == "src/app.py"
    assert overview["imports"][0]["path"] == "src/util.py"
    assert invalid == {
        "ok": False,
        "error": "invalid_path",
        "message": "Path must be repository-relative and stay in the repo",
    }


def test_registry_and_repo_discovery_declaration_are_stable_and_consistent() -> None:
    tools = get_discovery_tools()
    assert [tool.name for tool in tools] == EXPECTED_TOOLS
    assert AVAILABLE_TOOLS == EXPECTED_TOOLS
    assert all(
        tool.params_json_schema["additionalProperties"] is False for tool in tools
    )
    assert read_file_excerpt.name == "read_file_excerpt"


def test_path_safety_can_be_constructed_from_file_index(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    service = PathSafetyService(
        context.artifact_store.load_file_index(), context.repo_root
    )
    assert service.safe_paths == context.path_safety.safe_paths
