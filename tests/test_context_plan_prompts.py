from datetime import UTC, datetime

from bridger.deterministic.context_plan.discovery_tools import FileExcerptOutput
from bridger.deterministic.context_plan.prompts import (
    ContextPlanRepairPromptInput,
    FinalSynthesisPromptInput,
    InvestigationPromptInput,
    OrientationPromptInput,
    build_context_plan_repair_prompt,
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
    ContextPlanValidationIssue,
    ToolBudgetCost,
    ToolExecutionResult,
    ToolExecutionStatus,
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

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def tool(name: str, description: str) -> LLMToolDefinition:
    return LLMToolDefinition(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
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
            InstructionFile(path="AGENTS.md", kind=InstructionKind.AGENT_INSTRUCTIONS)
        ],
        docs_files=[DocsFile(path="README.md", kind=DocsKind.README)],
        parse_errors=[],
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
    )


def tool_result() -> ToolExecutionResult:
    return ToolExecutionResult(
        call_id="call-1",
        tool_name="read_file_ranges",
        status=ToolExecutionStatus.COMPLETED,
        output={
            "path": "src/main.py",
            "ranges": [
                {
                    "line_start": 1,
                    "line_end": 1,
                    "content": "def main(): pass",
                }
            ],
        },
        estimated_cost=ToolBudgetCost(file_reads=1, excerpts=1),
        actual_cost=ToolBudgetCost(file_reads=1, excerpts=1),
    )


def text(prompt: object) -> str:
    messages = getattr(prompt, "messages")
    return "\n".join(message.content or "" for message in messages)


def test_orientation_prompt_orients_with_facts_budgets_and_tools() -> None:
    prompt = build_orientation_prompt(
        OrientationPromptInput(
            repository_context=repo_context(),
            available_tools=[
                tool("list_files", "Navigate indexed paths."),
                tool("read_file_ranges", "Read validated ranges."),
            ],
            initial_warnings=["Generated files were skipped."],
        )
    )
    rendered = text(prompt)

    assert "neutral catalog of reusable packages" in rendered
    assert "Repository discovery and inventory health" in rendered
    assert "Manifest and repository-context facts" in rendered
    assert "Repository instructions and documentation anchors" in rendered
    assert "Configured budgets" in rendered
    assert [item.name for item in prompt.tools] == [
        "list_files",
        "read_file_ranges",
    ]
    assert "Begin investigating through repository tool calls" in rendered
    assert "symbol-only evidence" in rendered
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
            warnings=["Repeated read_file_ranges call."],
            open_questions=["How is the CLI invoked?"],
            investigation_notes=["Inspect the manifest next."],
            working_state_entities={
                "recent_evidence": [
                    {
                        "evidence_id": "evidence.symbol",
                        "inspection_level": "symbol_only",
                    }
                ],
                "findings": [{"finding_id": "finding.entrypoint"}],
                "relationships": [{"relationship_id": "relationship.constructs"}],
                "open_questions": [{"question_id": "question.cli"}],
                "package_candidates": [{"candidate_id": "candidate.runtime"}],
            },
            available_tools=[
                tool(
                    "request_context_plan_finalization",
                    "Submit finalization evidence.",
                ),
                tool("read_file_ranges", "Read validated ranges."),
            ],
        )
    )
    rendered = text(prompt)

    assert "def main(): pass" in rendered
    assert "Semantic coverage summary" in rendered
    assert "Major workflow stage coverage" in rendered
    assert "Central files and inspection depth" in rendered
    assert "Symbol-only and partially inspected central evidence" in rendered
    assert "Evidence ledger summary" in rendered
    assert "Established findings" in rendered
    assert "Package candidates and evidence strength" in rendered
    assert "finding.entrypoint" in rendered
    assert "relationship.constructs" in rendered
    assert "question.cli" in rendered
    assert "candidate.runtime" in rendered
    assert "evidence.symbol" in rendered
    assert '"excerpts":19' in rendered
    assert "Repeated read_file_ranges call." in rendered
    assert "Choose repository tool calls" in rendered
    assert "request_context_plan_finalization" in rendered
    assert "never return a prose final answer" in rendered
    assert "A high-priority question blocks finalization" in rendered
    assert "target_memory_kind" not in rendered
    assert prompt.output_type is None


def test_final_synthesis_prompt_is_tool_free_and_uses_context_plan_schema() -> None:
    prompt = build_final_synthesis_prompt(
        FinalSynthesisPromptInput(
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
            collected_findings=["main is the declared entrypoint"],
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
    assert "No repository, state-management, or control tools" in rendered
    assert "Never invent\nrepository paths" in rendered
    assert "canonical memory files" in rendered
    assert "Do not add memory_targets or target_memory_kind" in rendered
    assert "neutral reusable packages" in rendered
    assert "Semantic coverage summary" in rendered
    assert "Principal workflow stage coverage" in rendered
    assert "Evidence-selection and omission report" in rendered
    assert "Do not recover missing evidence from conversation memory" in rendered
    assert "Only the entrypoint was inspected." in rendered
    assert "Runtime arguments are unknown." in rendered
    assert "request_context_plan_finalization" not in rendered


def test_investigation_prompt_structures_finalization_rejection_feedback() -> None:
    rejection = ToolExecutionResult(
        call_id="finalize",
        tool_name="request_context_plan_finalization",
        status=ToolExecutionStatus.COMPLETED,
        output={
            "decision": {
                "accepted": False,
                "code": "uninspected_evidence_path",
                "issues": [
                    {
                        "code": "uninspected_evidence_path",
                        "location": ["key_evidence_paths", 0],
                        "message": "evidence path was not substantively inspected",
                        "context": {"path": "src/main.py"},
                    }
                ],
            }
        },
        estimated_cost=ToolBudgetCost(),
        actual_cost=ToolBudgetCost(),
    )

    prompt = build_investigation_prompt(
        InvestigationPromptInput(
            latest_tool_results=[rejection],
            inspection=inspection(),
            open_questions=["How is the CLI invoked?"],
        )
    )
    rendered = text(prompt)

    assert "Finalization was rejected" in rendered
    assert "Structured finalization rejection feedback" in rendered
    assert '"rejected_coverage_areas"' in rendered
    assert '"weak_evidence_reasons"' in rendered
    assert '"blocking_open_questions":["How is the CLI invoked?"]' in rendered
    assert "Update durable state before requesting finalization again" in rendered


def test_repair_prompt_preserves_the_synthesis_evidence_boundary() -> None:
    synthesis_input = FinalSynthesisPromptInput(
        validated_evidence_paths=["src/main.py"],
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
    )
    prompt = build_context_plan_repair_prompt(
        ContextPlanRepairPromptInput(
            invalid_output={"artifact": "context-plan"},
            validation_issues=[
                ContextPlanValidationIssue(
                    code="schema_validation_error",
                    location=["summary"],
                    message="Field required",
                    context={},
                )
            ],
            synthesis_evidence=synthesis_input,
        )
    )
    rendered = text(prompt)

    assert prompt.tools == ()
    assert prompt.output_type is ContextPlan
    assert "Correct only the reported structural or validation defects" in rendered
    assert "Do not use the repair pass to compensate for missing investigation" in (
        rendered
    )
    assert "Invalid ContextPlan candidate" in rendered
    assert "Exact ContextPlan validation issues" in rendered
    assert "def main(): pass" in rendered
    assert "ContextPlan output schema" in rendered
    assert "Return only the corrected structured ContextPlan" in rendered


def test_prompt_rendering_is_deterministic_and_bounds_large_collections() -> None:
    first = build_orientation_prompt(
        OrientationPromptInput(
            available_tools=[
                tool("list_files", "Navigate indexed paths."),
                tool("read_file_ranges", "Read validated ranges."),
            ],
            initial_warnings=[f"warning-{index:03d}" for index in range(41)],
        )
    )
    second = build_orientation_prompt(
        OrientationPromptInput(
            available_tools=[
                tool("read_file_ranges", "Read validated ranges."),
                tool("list_files", "Navigate indexed paths."),
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
