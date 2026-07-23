from datetime import UTC, datetime

from bridger.deterministic.context_plan.discovery_tools import FileExcerptOutput
from bridger.deterministic.context_plan.prompts import (
    FinalSynthesisPromptInput,
    InvestigationPromptInput,
    OrientationPromptInput,
    build_final_synthesis_prompt,
    build_investigation_prompt,
    build_orientation_prompt,
)
from bridger.llm.models import LLMMessage, LLMToolDefinition
from bridger.models.context_plan import (
    ContextPlan,
    ContextPlanExclusion,
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanRunInspection,
    ToolBudgetCost,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    GraphSummaryArtifact,
    GraphSummaryCounts,
)
from bridger.models.repo_context import (
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

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def tool(name: str, description: str) -> LLMToolDefinition:
    return LLMToolDefinition(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
    )


def bootstrap() -> RepoDiscoveryArtifact:
    return RepoDiscoveryArtifact(
        generated_at=NOW,
        repo=RepoDiscoveryRepo(root_name="demo", revision="abc123"),
        artifacts=RepoDiscoveryArtifacts(
            file_index=".bridger/file-index.json",
            repo_context=".bridger/repo-context.json",
            symbol_index=".bridger/symbol-index.json",
            repo_graph=".bridger/repo-graph.json",
            graph_summary=".bridger/graph-summary.json",
        ),
        artifact_checksums={
            "file-index.json": "a" * 64,
            "repo-context.json": "b" * 64,
            "symbol-index.json": "c" * 64,
            "repo-graph.json": "d" * 64,
            "graph-summary.json": "e" * 64,
        },
        compact_context=RepoDiscoveryCompactContext(
            file_count=3,
            skipped_file_count=0,
            manifest_files=["pyproject.toml"],
            config_files=[],
            instruction_files=["AGENTS.md"],
            docs_files=["README.md"],
            ci_files=[],
            declared_entrypoints=[
                DeclaredEntrypointSummary(path="src/main.py", source="pyproject")
            ],
            graph_counts=GraphSummaryCounts(file_nodes=3, import_edges=2),
        ),
        available_tools=["read_file_excerpt", "search_paths"],
        budgets=RepoDiscoveryBudgets(max_files_read=12, max_excerpts=24),
    )


def repo_context() -> RepoContextArtifact:
    return RepoContextArtifact(
        generated_at=NOW,
        manifests=[
            ManifestFile(
                path="pyproject.toml",
                kind=ManifestKind.PYTHON_PYPROJECT,
                parsed={"project": {"name": "demo"}},
            )
        ],
        config_files=[],
        ci_files=[],
        instruction_files=[
            InstructionFile(
                path="AGENTS.md", kind=InstructionKind.AGENT_INSTRUCTIONS
            )
        ],
        docs_files=[DocsFile(path="README.md", kind=DocsKind.README)],
        parse_errors=[],
    )


def graph_summary() -> GraphSummaryArtifact:
    return GraphSummaryArtifact(
        generated_at=NOW,
        counts=GraphSummaryCounts(file_nodes=3, import_edges=2),
        declared_entrypoints=[
            DeclaredEntrypointSummary(path="src/main.py", source="pyproject")
        ],
    )


def inspection() -> ContextPlanRunInspection:
    return ContextPlanRunInspection(
        safe_file_count=3,
        inspected_file_count=1,
        remaining_file_count=2,
        inspected_files=["src/main.py"],
        inspected_excerpts=[
            ContextPlanInspectedExcerpt(path="src/main.py", line_start=1, line_end=4)
        ],
        inspected_symbols=[
            ContextPlanInspectedSymbol(identifier="main", path="src/main.py")
        ],
        search_records=[],
        graph_query_records=[],
    )


def tool_result() -> ToolExecutionResult:
    return ToolExecutionResult(
        call_id="call-1",
        tool_name="read_file_excerpt",
        status=ToolExecutionStatus.COMPLETED,
        output={"path": "src/main.py", "content": "def main(): pass"},
        estimated_cost=ToolBudgetCost(file_reads=1, excerpts=1),
        actual_cost=ToolBudgetCost(file_reads=1, excerpts=1),
    )


def text(prompt: object) -> str:
    messages = getattr(prompt, "messages")
    return "\n".join(message.content or "" for message in messages)


def test_orientation_prompt_orients_with_facts_budgets_and_tools() -> None:
    prompt = build_orientation_prompt(
        OrientationPromptInput(
            repository_bootstrap=bootstrap(),
            repository_context=repo_context(),
            graph_summary=graph_summary(),
            available_tools=[
                tool("search_paths", "Search indexed paths."),
                tool("read_file_excerpt", "Read a validated excerpt."),
            ],
            initial_warnings=["Generated files were skipped."],
        )
    )
    rendered = text(prompt)

    assert "neutral catalog of\nreusable packages" in rendered
    assert '"root_name":"demo"' in rendered
    assert "Configured budgets" in rendered
    assert [item.name for item in prompt.tools] == [
        "read_file_excerpt",
        "search_paths",
    ]
    assert "responding with repository tool calls" in rendered
    assert "canonical memory files" in rendered
    assert "target_memory_kind" not in rendered
    assert "memory_targets" not in rendered
    assert prompt.output_type is None


def test_investigation_prompt_includes_progress_and_structured_finalization() -> None:
    prompt = build_investigation_prompt(
        InvestigationPromptInput(
            interaction_history=[LLMMessage.assistant("I inspected the entrypoint.")],
            latest_tool_results=[tool_result()],
            inspection=inspection(),
            discovered_paths=["README.md", "src/main.py"],
            evidence_paths=["src/main.py"],
            remaining_budgets={"excerpts": 19, "tool_calls": 7},
            warnings=["Repeated read_file_excerpt call."],
            open_questions=["How is the CLI invoked?"],
            investigation_notes=["Inspect the manifest next."],
            available_tools=[
                tool(
                    "request_context_plan_finalization",
                    "Submit finalization evidence.",
                ),
                tool("read_file_excerpt", "Read a validated excerpt."),
            ],
        )
    )
    rendered = text(prompt)

    assert "def main(): pass" in rendered
    assert "Inspection progress" in rendered
    assert '"excerpts":19' in rendered
    assert "Repeated read_file_excerpt call." in rendered
    assert "additional repository tool" in rendered
    assert "request_context_plan_finalization" in rendered
    assert "never return a prose final answer" in rendered
    assert "completion requirement" in rendered
    assert "target_memory_kind" not in rendered
    assert prompt.output_type is None


def test_final_synthesis_prompt_is_tool_free_and_uses_context_plan_schema() -> None:
    prompt = build_final_synthesis_prompt(
        FinalSynthesisPromptInput(
            repository_bootstrap=bootstrap(),
            validated_evidence_paths=["src/main.py", "pyproject.toml"],
            inspected_excerpts=[
                FileExcerptOutput(
                    source_artifact="file-index.json",
                    path="src/main.py",
                    line_start=1,
                    line_end=2,
                    content="def main(): pass",
                    truncated=False,
                )
            ],
            inspected_symbols=[
                ContextPlanInspectedSymbol(identifier="main", path="src/main.py")
            ],
            manifest_evidence=repo_context().manifests,
            graph_evidence=graph_summary(),
            collected_findings=["main is the declared entrypoint"],
            confirmed_entrypoints=[
                DeclaredEntrypointSummary(path="src/main.py", source="pyproject")
            ],
            warnings=["Only the entrypoint was inspected."],
            unknowns=["Runtime arguments are unknown."],
            intentionally_excluded=[
                ContextPlanExclusion(
                    path_or_pattern="tests/**", reason="Not inspected yet."
                )
            ],
        )
    )
    rendered = text(prompt)

    assert prompt.tools == ()
    assert prompt.output_type is ContextPlan
    assert "ContextPlan output schema" in rendered
    assert '"schema_version"' in rendered
    assert "No repository or control tools are available" in rendered
    assert "Never invent repository\npaths" in rendered
    assert "canonical memory files" in rendered
    assert "Do not add memory_targets or target_memory_kind" in rendered
    assert "neutral, reusable packages" in rendered
    assert "Only the entrypoint was inspected." in rendered
    assert "Runtime arguments are unknown." in rendered
    assert "request_context_plan_finalization" not in rendered


def test_prompt_rendering_is_deterministic_and_bounds_large_collections() -> None:
    first = build_orientation_prompt(
        OrientationPromptInput(
            repository_bootstrap=bootstrap(),
            available_tools=[
                tool("search_paths", "Search indexed paths."),
                tool("read_file_excerpt", "Read a validated excerpt."),
            ],
            initial_warnings=[f"warning-{index:03d}" for index in range(41)],
        )
    )
    second = build_orientation_prompt(
        OrientationPromptInput(
            repository_bootstrap=bootstrap(),
            available_tools=[
                tool("read_file_excerpt", "Read a validated excerpt."),
                tool("search_paths", "Search indexed paths."),
            ],
            initial_warnings=[f"warning-{index:03d}" for index in reversed(range(41))],
        )
    )

    assert first == second
    assert "[BRIDGER TRUNCATED" not in text(first)
    assert "1 list entries omitted" in text(first)


def test_prompt_input_mutable_defaults_are_not_shared() -> None:
    first = InvestigationPromptInput(inspection=inspection())
    second = InvestigationPromptInput(inspection=inspection())

    first.warnings.append("first only")
    first.discovered_paths.append("src/main.py")

    assert second.warnings == []
    assert second.discovered_paths == []
