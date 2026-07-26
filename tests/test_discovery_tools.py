import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agents.tool_context import ToolContext

from bridger.artifacts import write_artifact
from bridger.deterministic.context_plan_bootstrap.builder import AVAILABLE_TOOLS
from bridger.models.context_plan_bootstrap import (
    ContextPlanBootstrapArtifact,
    ContextPlanBootstrapArtifacts,
    ContextPlanBootstrapBudgets,
    ContextPlanBootstrapCompactContext,
    ContextPlanBootstrapRepo,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
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
from bridger.models.symbol_index import (
    SourceRange,
    SymbolFileExtraction,
    SymbolIndexArtifact,
    SymbolKind,
    SymbolRecord,
)
from bridger.tools.context import BridgerToolContext, build_tool_context
from bridger.tools.errors import BridgerToolError
from bridger.tools.registry import get_discovery_tools
from bridger.tools.services import ArtifactStore, PathSafetyService

GENERATED_AT = datetime(2026, 6, 19, tzinfo=UTC)


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
                language="python",
                name="main",
                qualified_name="main",
                kind=SymbolKind.FUNCTION,
                declaration_range=SourceRange(
                    start_line=3,
                    start_column=0,
                    end_line=4,
                    end_column=22,
                    start_byte=32,
                    end_byte=54,
                ),
                body_range=SourceRange(
                    start_line=3,
                    start_column=11,
                    end_line=4,
                    end_column=22,
                    start_byte=43,
                    end_byte=54,
                ),
                body_available=True,
                declaration_preview="def main()",
                signature="def main()",
                extractor="tree_sitter_python",
            ),
            SymbolRecord(
                id="sym:src/util.py:1:helper",
                path="src/util.py",
                language="python",
                name="helper",
                qualified_name="helper",
                kind=SymbolKind.FUNCTION,
                declaration_range=SourceRange(
                    start_line=1,
                    start_column=0,
                    end_line=2,
                    end_column=21,
                    start_byte=0,
                    end_byte=21,
                ),
                body_range=SourceRange(
                    start_line=1,
                    start_column=13,
                    end_line=2,
                    end_column=21,
                    start_byte=13,
                    end_byte=21,
                ),
                body_available=True,
                declaration_preview="def helper()",
                signature="def helper()",
                extractor="tree_sitter_python",
            ),
        ],
        files=[
            SymbolFileExtraction(
                path="src/app.py",
                language="python",
                status="success",
                symbol_count=1,
            ),
            SymbolFileExtraction(
                path="src/util.py",
                language="python",
                status="success",
                symbol_count=1,
            ),
        ],
    )
    budgets = ContextPlanBootstrapBudgets(
        max_files_read=3,
        max_excerpts=5,
        max_grep_results=1,
        max_symbol_results=1,
        max_file_excerpt_lines=2,
    )
    discovery = ContextPlanBootstrapArtifact(
        generated_at=GENERATED_AT,
        repo=ContextPlanBootstrapRepo(root_name="fixture", revision="test"),
        artifacts=ContextPlanBootstrapArtifacts(
            file_index=".bridger/artifacts/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
        ),
        artifact_checksums={
            name: "0" * 64
            for name in [
                "file-index.json",
                "repo-context.json",
                "symbol-index.json",
            ]
        },
        compact_context=ContextPlanBootstrapCompactContext(
            file_count=len(files),
            skipped_file_count=1,
            manifest_files=["pyproject.toml"],
            config_files=["ruff.toml"],
            instruction_files=["AGENTS.md"],
            docs_files=["README.md"],
            ci_files=[".github/workflows/test.yml"],
        ),
        available_tools=AVAILABLE_TOOLS,
        budgets=budgets,
    )
    artifacts = {
        "file-index.json": file_index,
        "repo-context.json": repo_context,
        "symbol-index.json": symbols,
        "context-plan-bootstrap.json": discovery,
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
    assert store.load_context_plan_bootstrap().repo.root_name == "fixture"


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
    assert error.value.payload.error == "path_outside_repository"


def test_path_safety_accepts_safe_path_and_rejects_skipped_unknown_and_prefix(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    assert context.path_safety.validate_file("src/app.py") == "src/app.py"
    assert context.path_safety.validate_prefix("src") == "src"
    with pytest.raises(BridgerToolError) as skipped:
        context.path_safety.validate_file(".env")
    assert skipped.value.payload.error == "path_excluded"
    with pytest.raises(BridgerToolError) as unknown:
        context.path_safety.validate_file("missing.py")
    assert unknown.value.payload.error == "path_not_found"
    with pytest.raises(BridgerToolError):
        context.path_safety.validate_prefix("missing")


def test_file_navigation_search_and_range_reads_are_bounded(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    listed = context.file_index.list_files(
        prefix="src",
        extension="py",
        recursive=True,
        max_depth=8,
        limit=1,
    )
    searched = context.search.search_with_context(
        "return",
        path_prefix="src",
        limit=1,
    )
    read = context.file_read.read_ranges(
        "src/app.py",
        [{"line_start": 2, "line_end": 4}],
    )
    validated = context.file_index.validate_paths(["src/app.py", ".env", "none.py"])

    assert [item["path"] for item in listed["files"]] == ["src/app.py"]
    assert listed["truncated"] is True
    assert searched["total_available"] == 2
    assert searched["returned_count"] == 1
    assert searched["truncated"] is True
    assert read["ranges"][0]["content"] == "\ndef main():\n    return helper()"
    assert [item["status"] for item in validated["results"]] == [
        "valid_file",
        "sensitive",
        "missing",
    ]


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
        context.file_read.read_ranges(
            "src/app.py",
            [{"line_start": 1, "line_end": 1}],
        )

    assert error.value.payload.error == "path_outside_repository"


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
    excerpt = context.file_read.read_ranges(
        symbol.path,
        [
            {
                "line_start": symbol.declaration_range.start_line,
                "line_end": symbol.declaration_range.end_line,
            }
        ],
    )

    assert searched["total_matches"] == 2
    assert len(searched["symbols"]) == 1
    assert listed["symbols"][0]["id"] == symbol.id
    assert excerpt["ranges"][0]["content"] == "def main():\n    return helper()"
    with pytest.raises(BridgerToolError) as error:
        context.symbols.get("missing")
    assert error.value.payload.error == "symbol_not_found"


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
    invalid = invoke_tool(
        context,
        "read_file_ranges",
        {
            "path": "/etc/passwd",
            "ranges": [{"line_start": 1, "line_end": 1}],
        },
    )

    assert symbol_result["ok"] is True
    assert symbol_result["symbol"]["id"] == "sym:src/app.py:3:main"
    assert symbol_result["excerpt"]["path"] == "src/app.py"
    assert symbol_result["excerpt"]["ranges"] == [
        {
            "line_start": 2,
            "line_end": 4,
            "content": "\ndef main():\n    return helper()",
        }
    ]
    assert invalid == {
        "ok": False,
        "error": "path_outside_repository",
        "message": "Path must be repository-relative and stay in the repo",
    }


def test_registry_and_bootstrap_declaration_are_stable_and_consistent() -> None:
    tools = get_discovery_tools()
    assert {tool.name for tool in tools} == set(AVAILABLE_TOOLS)
    assert all(
        tool.params_json_schema["additionalProperties"] is False for tool in tools
    )


def test_path_safety_can_be_constructed_from_file_index(
    tool_repo: tuple[Path, BridgerToolContext],
) -> None:
    _, context = tool_repo
    service = PathSafetyService(
        context.artifact_store.load_file_index(), context.repo_root
    )
    assert service.safe_paths == context.path_safety.safe_paths
