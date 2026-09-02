"""Stage 3 context-hydration contract tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import tiktoken
from pydantic import ValidationError

from bridger.contracts.memory.core import (
    ActivationMode,
    CandidateArtifactRef,
    CompletionItemState,
    CompletionObligationDefinition,
    CompletionStatus,
    ExecutionBudget,
    ExecutionUsage,
    FindingOrigin,
    FindingRef,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    ObligationApplicability,
    SourceBinding,
    TargetActivation,
    TargetCatalogEntry,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.hydration import (
    GraphOverview,
    PermissionProfile,
    WorkerContext,
    WorkerContextMode,
    WorkerCycleFocus,
    WorkerCycleFocusKind,
    WorkerInstructions,
    WorkerProfile,
)
from bridger.llm.profiles import LLMProfile
from bridger.memory import (
    CandidateArtifactRecord,
    ContextWindowConfigurationError,
    ContextWindowManager,
    EvidenceRecord,
    FindingRecord,
    OpenQuestionRecord,
    WorkerContextDebugWriter,
    WorkerContextHydrationError,
    WorkerContextInvocationError,
    compile_worker_context,
    load_target_artifacts,
    serialize_worker_context,
    serialize_worker_context_sections,
)
from bridger.repository_brain.harness import _profiles

_SOURCE = SourceBinding(
    repository_id="repository-1",
    repository_revision="a" * 40,
    graph_snapshot_id="snapshot-1",
)
_BUDGET = ExecutionBudget(
    max_cycles=10,
    max_model_calls=20,
    max_tool_calls=30,
    max_repair_cycles=4,
    max_input_tokens=50_000,
    max_output_tokens=None,
)
_DEFAULT_TARGETS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bridger"
    / "memory"
    / "default-targets"
)
_GRAPH_OVERVIEW = GraphOverview(
    graph_snapshot_id="snapshot-1",
    graph_contract_version="bridger.graph.v1",
    build_mode="full",
    node_count=12,
    edge_count=18,
    hyperedge_count=2,
    community_count=3,
    central_nodes=(),
    central_nodes_truncated=False,
    surprising_connections=(),
    surprising_connections_truncated=False,
    suggested_questions=(),
    suggested_questions_truncated=False,
)


class FakeHydrationStateReader:
    """In-memory fake for the narrow Stage 3 authoritative read boundary."""

    def __init__(self) -> None:
        self.artifacts: dict[str, CandidateArtifactRecord] = {}
        self.evidence: dict[str, EvidenceRecord] = {}
        self.questions: dict[str, OpenQuestionRecord] = {}
        self.findings: dict[str, FindingRecord] = {}

    def get_candidate_artifact(
        self,
        artifact_id: str,
    ) -> CandidateArtifactRecord | None:
        return self.artifacts.get(artifact_id)

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self.evidence.get(evidence_id)

    def get_open_question(self, question_id: str) -> OpenQuestionRecord | None:
        return self.questions.get(question_id)

    def get_open_finding(self, finding_id: str) -> FindingRecord | None:
        return self.findings.get(finding_id)


@dataclass
class HydrationFixture:
    fleet_spec: MemoryFleetSpec
    target_spec: TargetTaskSpec
    target_state: TargetTaskState
    completion_state: TargetCompletionState
    catalog: MemoryTargetCatalog
    definition: TargetDefinition
    worker_profile: WorkerProfile
    permission_profile: PermissionProfile
    worker_instructions: WorkerInstructions
    state_reader: FakeHydrationStateReader

    def compile(self, **kwargs: object) -> WorkerContext:
        return compile_worker_context(
            self.fleet_spec,
            self.target_spec,
            self.target_state,
            self.completion_state,
            self.catalog,
            self.definition,
            self.worker_profile,
            self.permission_profile,
            self.worker_instructions,
            self.state_reader,
            graph_overview=_GRAPH_OVERVIEW,
            **kwargs,
        )


def test_initial_hydration_projects_only_complete_authoritative_execution_view() -> (
    None
):
    fixture = _fixture()
    fixture.target_state.working_summary = "Full durable summary.\nNothing omitted."
    fixture.target_state.open_question_refs = ["question-2", "question-1"]
    fixture.state_reader.questions = {
        "question-1": _question("question-1", "Where is A?"),
        "question-2": _question("question-2", "Why does B happen?"),
    }
    _add_artifact(fixture, "artifact-z", "z-last.md", revision=2)
    _add_artifact(fixture, "artifact-a", "a-first.md")
    fixture.completion_state.items[0].evidence_refs = ["evidence-completion"]
    fixture.target_state.evidence_refs = ["evidence-state-only"]
    fixture.state_reader.evidence = {
        evidence_id: EvidenceRecord(evidence_id=evidence_id, source=_SOURCE)
        for evidence_id in ("evidence-completion", "evidence-state-only")
    }
    usage_before = fixture.target_state.usage.model_copy(deep=True)

    context = fixture.compile()

    assert fixture.target_state.phase is TargetPhase.HYDRATING
    assert fixture.target_state.usage == usage_before
    assert context.mode is WorkerContextMode.INITIAL
    assert context.working_summary == "Full durable summary.\nNothing omitted."
    assert [item.obligation_id for item in context.completion_obligations] == [
        "second-contract-item",
        "first-contract-item",
    ]
    assert [question.question_id for question in context.open_questions] == [
        "question-2",
        "question-1",
    ]
    assert [artifact.relative_path for artifact in context.candidate_artifacts] == [
        "a-first.md",
        "z-last.md",
    ]
    assert context.remaining_target_budget.cycles == 8
    assert context.remaining_target_budget.model_calls == 17
    assert context.remaining_target_budget.tool_calls == 25
    assert context.remaining_target_budget.input_tokens == 49_000
    assert context.remaining_target_budget.output_tokens is None
    assert context.allowed_tool_ids == ("repository_search", "workspace_read")
    assert context.graph_overview == _GRAPH_OVERVIEW

    fields = type(context).model_fields
    assert "evidence_refs" not in fields
    assert "phase" not in fields
    assert "last_checkpoint_ref" not in fields
    assert "stall_count" not in fields
    assert "transcript" not in fields
    serialized = serialize_worker_context(context)
    stable_context, _target_context, cycle_context = serialize_worker_context_sections(
        context
    )
    assert "Repository graph overview" in stable_context
    assert '"node_count":12' in stable_context
    assert "Repository graph overview" not in cycle_context
    assert "evidence-completion" in serialized
    assert "evidence-state-only" not in serialized
    assert "artifact contents" not in serialized.lower()

    with pytest.raises(ValidationError, match="frozen"):
        context.target_task_id = "changed"


def test_repair_hydration_uses_same_context_architecture_and_all_findings() -> None:
    fixture = _fixture()
    fixture.target_state.working_summary = "Continue from the accepted structure."
    fixture.target_state.open_finding_refs = [
        FindingRef(
            finding_id="finding-review",
            origin=FindingOrigin.TARGET_REVIEW,
        ),
        FindingRef(
            finding_id="finding-fleet",
            origin=FindingOrigin.FLEET_VALIDATION,
        ),
    ]
    fixture.state_reader.findings = {
        "finding-review": FindingRecord(
            finding_id="finding-review",
            target_task_id=fixture.target_spec.target_task_id,
            origin=FindingOrigin.TARGET_REVIEW,
            content="Explain the failure path.",
            affected_artifact_id="artifact-a",
            evidence_refs=("evidence-finding",),
        ),
        "finding-fleet": FindingRecord(
            finding_id="finding-fleet",
            target_task_id=fixture.target_spec.target_task_id,
            origin=FindingOrigin.FLEET_VALIDATION,
            content="Remove ownership overlap.",
            affected_scope="boundary guidance",
        ),
    }
    fixture.state_reader.evidence["evidence-finding"] = EvidenceRecord(
        evidence_id="evidence-finding",
        source=_SOURCE,
    )

    context = fixture.compile()

    assert context.mode is WorkerContextMode.REPAIR
    assert context.cycle_focus.kind is WorkerCycleFocusKind.REPAIR_FINDINGS
    assert context.cycle_focus.finding_ids == ("finding-review", "finding-fleet")
    assert [finding.finding_id for finding in context.repair_findings] == [
        "finding-review",
        "finding-fleet",
    ]
    assert context.repair_findings[0].evidence_refs == ("evidence-finding",)
    assert context.working_summary == "Continue from the accepted structure."
    assert context.target_task_id == fixture.target_spec.target_task_id
    assert fixture.target_state.phase is TargetPhase.HYDRATING


def test_cycle_focus_is_deterministic_across_fresh_hydration() -> None:
    fixture = _fixture()
    fixture.completion_state.items[0].status = CompletionStatus.UNINVESTIGATED
    fixture.completion_state.items[0].resolution_note = None

    first = fixture.compile()

    assert first.cycle_focus.kind is WorkerCycleFocusKind.OBLIGATION
    assert first.cycle_focus.obligation_id == "second-contract-item"
    assert len(first.completion_obligations) == 2

    fixture.completion_state.items[1] = fixture.completion_state.items[1].model_copy(
        update={
            "status": CompletionStatus.COVERED,
            "resolution_note": "Investigated in cycle one.",
        }
    )
    fixture.target_state.phase = TargetPhase.SCHEDULED
    second = fixture.compile()

    assert second.cycle_focus.kind is WorkerCycleFocusKind.OBLIGATION
    assert second.cycle_focus.obligation_id == "first-contract-item"

    fixture.completion_state.items[0] = fixture.completion_state.items[0].model_copy(
        update={
            "status": CompletionStatus.UNKNOWN,
            "resolution_note": "Evidence remained ambiguous.",
        }
    )
    fixture.target_state.phase = TargetPhase.SCHEDULED
    final = fixture.compile()

    assert final.cycle_focus.kind is WorkerCycleFocusKind.FINALIZATION_READINESS
    serialized = serialize_worker_context(final)
    assert serialized.index("# Current cycle objective") < serialized.index(
        "# Completion obligations and current states"
    )
    assert "use yield_cycle" in serialized


def test_hydration_projects_only_unresolved_configured_related_obligations() -> None:
    fixture = _fixture()
    fixture.completion_state.items[0] = fixture.completion_state.items[0].model_copy(
        update={
            "status": CompletionStatus.UNINVESTIGATED,
            "resolution_note": None,
        }
    )
    fixture.definition.completion_obligations[0] = (
        fixture.definition.completion_obligations[0].model_copy(
            update={
                "related_obligation_ids": [
                    "first-contract-item",
                    "covered-item",
                    "unknown-item",
                ]
            }
        )
    )
    fixture.definition = fixture.definition.model_copy(
        update={
            "completion_obligations": [
                *fixture.definition.completion_obligations,
                CompletionObligationDefinition(
                    obligation_id="covered-item",
                    description="Covered item.",
                    investigation_requirements=["Inspect source."],
                    applicability=ObligationApplicability.ALWAYS,
                ),
                CompletionObligationDefinition(
                    obligation_id="unknown-item",
                    description="Unknown item.",
                    investigation_requirements=["Inspect source."],
                    applicability=ObligationApplicability.ALWAYS,
                ),
                CompletionObligationDefinition(
                    obligation_id="unrelated-item",
                    description="Unrelated item.",
                    investigation_requirements=["Inspect source."],
                    applicability=ObligationApplicability.ALWAYS,
                ),
            ]
        }
    )
    fixture.completion_state.items.extend(
        (
            CompletionItemState(
                obligation_id="covered-item",
                status=CompletionStatus.COVERED,
                resolution_note="Covered.",
            ),
            CompletionItemState(
                obligation_id="unknown-item",
                status=CompletionStatus.UNKNOWN,
                resolution_note="Unknown.",
            ),
            CompletionItemState(obligation_id="unrelated-item"),
        )
    )

    context = fixture.compile()

    assert context.cycle_focus.obligation_id == "second-contract-item"
    assert context.cycle_focus.related_obligation_ids == ("first-contract-item",)
    serialized = serialize_worker_context(context)
    assert "related_unresolved_obligation_ids:\n- first-contract-item" in serialized
    assert "investigation-reuse candidates" in serialized
    assert "Do not launch additional repository exploration" in serialized

    fixture.completion_state.items[1] = fixture.completion_state.items[1].model_copy(
        update={
            "status": CompletionStatus.COVERED,
            "resolution_note": "Resolved with the primary investigation.",
        }
    )
    fixture.completion_state.items[0] = fixture.completion_state.items[0].model_copy(
        update={
            "status": CompletionStatus.COVERED,
            "resolution_note": "Resolved.",
        }
    )
    fixture.target_state.phase = TargetPhase.SCHEDULED

    next_context = fixture.compile()

    assert next_context.cycle_focus.obligation_id == "unrelated-item"


def test_worker_cycle_focus_rejects_invalid_related_obligations() -> None:
    assert WorkerCycleFocus(
        kind=WorkerCycleFocusKind.OBLIGATION,
        obligation_id="a",
        related_obligation_ids=("b", "c"),
    ).related_obligation_ids == ("b", "c")

    with pytest.raises(ValidationError, match="related_obligation_ids must be unique"):
        WorkerCycleFocus(
            kind=WorkerCycleFocusKind.OBLIGATION,
            obligation_id="a",
            related_obligation_ids=("b", "b"),
        )
    with pytest.raises(ValidationError, match="repair focus"):
        WorkerCycleFocus(
            kind=WorkerCycleFocusKind.REPAIR_FINDINGS,
            finding_ids=("finding",),
            related_obligation_ids=("b",),
        )
    with pytest.raises(ValidationError, match="finalization-readiness"):
        WorkerCycleFocus(
            kind=WorkerCycleFocusKind.FINALIZATION_READINESS,
            related_obligation_ids=("b",),
        )


def test_worker_context_rejects_resolved_or_primary_related_obligations() -> None:
    context = _fixture().compile()
    context_data = context.model_dump()

    context_data["cycle_focus"]["related_obligation_ids"] = ["first-contract-item"]
    with pytest.raises(ValidationError, match="must be unresolved"):
        WorkerContext.model_validate(context_data)

    context_data["cycle_focus"]["related_obligation_ids"] = ["second-contract-item"]
    with pytest.raises(ValidationError, match="cannot relate to its primary"):
        WorkerContext.model_validate(context_data)


def test_target_definition_validates_related_obligation_ids() -> None:
    fixture = _fixture()
    definition_data = fixture.definition.model_dump()
    obligations = definition_data["completion_obligations"]
    obligations[0]["related_obligation_ids"] = ["first-contract-item"]

    validated = TargetDefinition.model_validate(definition_data)

    assert validated.completion_obligations[1].related_obligation_ids == []
    assert validated.completion_obligations[0].related_obligation_ids == [
        "first-contract-item"
    ]

    for related_ids, message in (
        (["missing-item"], "must belong"),
        (["second-contract-item"], "cannot relate to itself"),
        (["first-contract-item", "first-contract-item"], "must be unique"),
    ):
        definition_data["completion_obligations"][0]["related_obligation_ids"] = (
            related_ids
        )
        with pytest.raises(ValidationError, match=message):
            TargetDefinition.model_validate(definition_data)


def test_shipped_architecture_contract_prevents_early_finalization() -> None:
    fixture = _fixture_with_shipped_architecture()

    first = fixture.compile()
    assert first.cycle_focus.kind is WorkerCycleFocusKind.OBLIGATION
    assert first.cycle_focus.obligation_id == "runtime-entrypoints"

    fixture.completion_state.items[0] = fixture.completion_state.items[0].model_copy(
        update={
            "status": CompletionStatus.COVERED,
            "resolution_note": "Runtime entrypoints were investigated.",
        }
    )
    fixture.target_state.phase = TargetPhase.SCHEDULED
    second = fixture.compile()
    assert second.cycle_focus.kind is WorkerCycleFocusKind.OBLIGATION
    assert second.cycle_focus.obligation_id == "runtime-components"
    assert len(second.completion_obligations) == 10

    fixture.completion_state.items = [
        item.model_copy(
            update={
                "status": (
                    CompletionStatus.COVERED
                    if index % 2 == 0
                    else CompletionStatus.NOT_APPLICABLE
                ),
                "resolution_note": "Obligation was explicitly resolved.",
            }
        )
        for index, item in enumerate(fixture.completion_state.items)
    ]
    fixture.target_state.phase = TargetPhase.SCHEDULED
    final = fixture.compile()
    assert final.cycle_focus.kind is WorkerCycleFocusKind.FINALIZATION_READINESS


@pytest.mark.parametrize("test_budgets", [False, True])
def test_init_profiles_preflight_a_real_shipped_worker_context(
    test_budgets: bool,
) -> None:
    worker_profile, reviewer_profile = _profiles(
        LLMProfile(
            name="balanced",
            provider="openai",
            model="gpt-5.6-terra",
        ),
        test_budgets,
    )
    fixture = _fixture_with_shipped_architecture()
    fixture.worker_profile = worker_profile
    fixture.worker_instructions = fixture.worker_instructions.model_copy(
        update={"worker_profile_id": worker_profile.profile_id}
    )
    fixture.target_spec = fixture.target_spec.model_copy(
        update={"worker_profile_id": worker_profile.profile_id}
    )
    fixture.fleet_spec = fixture.fleet_spec.model_copy(
        update={"default_worker_profile_id": worker_profile.profile_id}
    )

    context = fixture.compile()
    diagnostics = ContextWindowManager(worker_profile).inspect_initial_worker_context(
        serialize_worker_context(context)
    )

    assert diagnostics.within_provider_input_limit is True
    assert worker_profile.provider_input_hard_cap_tokens <= 32_000
    assert reviewer_profile.provider_input_hard_cap_tokens == (
        reviewer_profile.model_context_window_tokens
        - reviewer_profile.reserved_response_tokens
    )
    assert worker_profile.model_context_window_tokens == 1_050_000
    assert worker_profile.provider_input_hard_cap_tokens == 32_000
    assert (
        worker_profile.model_context_window_tokens
        != worker_profile.provider_input_hard_cap_tokens
    )


def test_illegal_invocation_is_rejected_without_lifecycle_mutation() -> None:
    fixture = _fixture()
    fixture.target_state.phase = TargetPhase.INITIALIZED

    with pytest.raises(WorkerContextInvocationError, match="SCHEDULED"):
        fixture.compile()

    assert fixture.target_state.phase is TargetPhase.INITIALIZED
    assert fixture.target_state.last_error_ref is None


def test_duplicate_invocation_does_not_advance_beyond_hydrating() -> None:
    fixture = _fixture()
    fixture.compile()

    with pytest.raises(WorkerContextInvocationError, match="SCHEDULED"):
        fixture.compile()

    assert fixture.target_state.phase is TargetPhase.HYDRATING


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("completion", "completion state"),
        ("artifact", "candidate artifact"),
        ("question", "open question"),
        ("evidence", "referenced evidence"),
        ("finding", "open finding"),
    ],
)
def test_missing_referenced_authoritative_state_fails_hydration(
    corruption: str,
    message: str,
) -> None:
    fixture = _fixture()
    if corruption == "completion":
        fixture.completion_state.items.pop()
    elif corruption == "artifact":
        fixture.target_state.artifact_refs.append(
            CandidateArtifactRef(
                artifact_id="missing-artifact",
                relative_path="missing.md",
                revision=1,
                digest="missing-digest",
            )
        )
    elif corruption == "question":
        fixture.target_state.open_question_refs.append("missing-question")
    elif corruption == "evidence":
        fixture.completion_state.items[0].evidence_refs.append("missing-evidence")
    else:
        fixture.target_state.open_finding_refs.append(
            FindingRef(
                finding_id="missing-finding",
                origin=FindingOrigin.HARD_VALIDATION,
            )
        )

    with pytest.raises(WorkerContextHydrationError, match=message):
        fixture.compile()

    assert fixture.target_state.phase is TargetPhase.FAILED
    assert fixture.target_state.last_error_ref == "stage-3-context-hydration"
    assert fixture.target_state.open_finding_refs == (
        []
        if corruption != "finding"
        else [
            FindingRef(
                finding_id="missing-finding",
                origin=FindingOrigin.HARD_VALIDATION,
            )
        ]
    )


def test_artifact_revision_or_digest_mismatch_fails_without_reading_content() -> None:
    fixture = _fixture()
    reference = _add_artifact(fixture, "artifact-1", "guide.md", revision=3)
    fixture.state_reader.artifacts[reference.artifact_id] = (
        fixture.state_reader.artifacts[reference.artifact_id].model_copy(
            update={"digest": "different"}
        )
    )

    with pytest.raises(WorkerContextHydrationError, match="authoritative state"):
        fixture.compile()

    assert fixture.target_state.phase is TargetPhase.FAILED
    assert set(CandidateArtifactRecord.model_fields) == {
        "artifact_id",
        "target_task_id",
        "target_workspace",
        "relative_path",
        "revision",
        "digest",
    }


def test_missing_or_mismatched_static_configuration_fails_after_transition() -> None:
    fixture = _fixture()
    fixture.permission_profile = fixture.permission_profile.model_copy(
        update={"profile_id": "other-permissions"}
    )

    with pytest.raises(WorkerContextHydrationError, match="permission profile"):
        fixture.compile()

    assert fixture.target_state.phase is TargetPhase.FAILED
    assert fixture.target_state.open_finding_refs == []


def test_complete_request_hard_cap_includes_fixed_request_overhead() -> None:
    baseline = _fixture()
    baseline_context = baseline.compile()
    serialized = serialize_worker_context(baseline_context)
    base_manager = ContextWindowManager(baseline.worker_profile)
    context_tokens = base_manager.count_text(serialized)
    fixed_input = "fixed tool definitions and structured output schema"
    fixed_tokens = base_manager.count_text(fixed_input) + 7

    exact = _fixture()
    exact.worker_profile = exact.worker_profile.model_copy(
        update={"provider_input_hard_cap_tokens": context_tokens + fixed_tokens}
    )
    exact_context = exact.compile(
        fixed_request_input=fixed_input,
        provider_framing_tokens=7,
    )
    exact_manager = ContextWindowManager(
        exact.worker_profile,
        fixed_request_input=fixed_input,
        provider_framing_tokens=7,
    )
    diagnostics = exact_manager.inspect_initial_worker_context(
        serialize_worker_context(exact_context)
    )
    assert diagnostics.complete_initial_provider_input_tokens == (
        exact.worker_profile.provider_input_hard_cap_tokens
    )
    assert diagnostics.remaining_provider_input_tokens == 0

    over = _fixture()
    over.worker_profile = over.worker_profile.model_copy(
        update={"provider_input_hard_cap_tokens": (context_tokens + fixed_tokens - 1)}
    )
    with pytest.raises(WorkerContextHydrationError, match="exceeds the hard cap"):
        over.compile(
            fixed_request_input=fixed_input,
            provider_framing_tokens=7,
        )
    assert over.target_state.phase is TargetPhase.FAILED


def test_unused_capacity_remains_unused_and_serialization_is_stable_first() -> None:
    first = _fixture()
    first.target_state.working_summary = "Dynamic working summary."
    _add_artifact(first, "artifact-b", "b.md")
    first_context = first.compile()
    first_serialized = serialize_worker_context(first_context)
    diagnostics = ContextWindowManager(
        first.worker_profile
    ).inspect_initial_worker_context(first_serialized)

    second = _fixture()
    second.target_state.working_summary = "Dynamic working summary."
    _add_artifact(second, "artifact-b", "b.md")
    second_serialized = serialize_worker_context(second.compile())

    assert first_serialized == second_serialized
    assert diagnostics.complete_initial_provider_input_tokens < 32_000
    assert diagnostics.remaining_provider_input_tokens > 0
    assert not first_serialized.endswith(" " * 100)
    headings = [
        "# Shared worker instructions",
        "# Worker profile and tool surface",
        "# Target instructions and semantic contract",
        "# Execution mode",
        "# Current cycle objective",
        "# Completion obligations and current states",
        "# Working summary",
        "# Open questions",
        "# Remaining target budget",
        "# Complete candidate-artifact inventory",
    ]
    positions = [first_serialized.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_debug_snapshot_is_optional_and_debug_write_failure_is_non_blocking(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    debug_root = tmp_path / ".bridger" / "debug"
    context = fixture.compile(debug_writer=WorkerContextDebugWriter(str(debug_root)))
    snapshot_path = (
        debug_root
        / fixture.fleet_spec.fleet_run_id
        / "worker-contexts"
        / fixture.target_spec.target_task_id
        / "hydration.json"
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["context"] == context.model_dump(mode="json")
    assert payload["serialized_model_context"] == serialize_worker_context(context)
    assert payload["diagnostics"]["within_provider_input_limit"] is True

    class FailingDebugWriter(WorkerContextDebugWriter):
        def write(self, *_: object) -> None:
            raise OSError("debug filesystem unavailable")

    another = _fixture()
    result = another.compile(debug_writer=FailingDebugWriter(str(debug_root)))
    assert result.mode is WorkerContextMode.INITIAL
    assert another.target_state.phase is TargetPhase.HYDRATING


def test_context_window_manager_uses_openai_tokens_and_observes_active_requests() -> (
    None
):
    fixture = _fixture()
    manager = ContextWindowManager(
        fixture.worker_profile,
        fixed_request_input="tools",
        provider_framing_tokens=3,
    )
    text = "OpenAI-compatible token counting."
    expected = len(
        tiktoken.get_encoding("o200k_base").encode(text, disallowed_special=())
    )

    assert manager.count_text(text) == expected
    assert manager.maximum_worker_context_tokens == (
        32_000 - manager.fixed_request_input_tokens
    )
    request_diagnostics = manager.inspect_request(
        text,
        provider_framing_tokens=2,
    )
    assert request_diagnostics.current_request_input_tokens == expected + 2
    assert request_diagnostics.remaining_context_tokens == (
        fixture.worker_profile.model_context_window_tokens
        - fixture.worker_profile.reserved_response_tokens
        - request_diagnostics.current_request_input_tokens
    )
    assert request_diagnostics.within_context_limit is True

    invalid_profile = fixture.worker_profile.model_copy(
        update={"tokenizer_encoding": "not-an-openai-encoding"}
    )
    with pytest.raises(ContextWindowConfigurationError, match="unknown OpenAI"):
        ContextWindowManager(invalid_profile)


def _fixture() -> HydrationFixture:
    obligations = [
        CompletionObligationDefinition(
            obligation_id="second-contract-item",
            description="Investigate the second contract item.",
            investigation_requirements=["Inspect the second item."],
            applicability=ObligationApplicability.ALWAYS,
        ),
        CompletionObligationDefinition(
            obligation_id="first-contract-item",
            description="Investigate the conditional first item.",
            investigation_requirements=["Inspect the first item."],
            applicability=ObligationApplicability.CONDITIONAL,
            condition_hint="When the feature exists.",
        ),
    ]
    definition = TargetDefinition(
        schema_version=2,
        target_id="architecture",
        target_contract_version="contract-v1",
        activation=TargetActivation(mode=ActivationMode.ALWAYS),
        depends_on=[],
        canonical_question="How is the repository architected?",
        purpose="Explain structural responsibilities.",
        expected_abstraction="System-level architecture.",
        always_relevant_scope=["major components"],
        conditional_scope=["background workers"],
        exclusions=["deployment operations"],
        boundary_guidance=["Keep business rules in their canonical target."],
        investigation_expectations=["Trace central component boundaries."],
        evidence_expectations=["Ground behavioral claims in source."],
        completion_obligations=obligations,
        output_quality_expectations=["Prefer synthesis over inventories."],
    )
    catalog = MemoryTargetCatalog(
        schema_version=2,
        catalog_id="memory-targets",
        catalog_version="catalog-v1",
        targets=[
            TargetCatalogEntry(
                target_id=definition.target_id,
                target_contract_version=definition.target_contract_version,
            )
        ],
        cross_target_ownership_rules=[
            "The target answering the primary question owns the detail."
        ],
    )
    fleet_spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id=catalog.catalog_id,
        target_catalog_version=catalog.catalog_version,
        target_ids=[definition.target_id],
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=_BUDGET,
        default_target_budget=_BUDGET,
        runtime_root="/tmp/bridger-runtime",
        output_root="/tmp/bridger-output",
    )
    target_spec = TargetTaskSpec(
        target_task_id="task-architecture",
        fleet_run_id=fleet_spec.fleet_run_id,
        target_id=definition.target_id,
        target_contract_version=definition.target_contract_version,
        source=_SOURCE,
        worker_profile_id="worker-v1",
        reviewer_profile_id="reviewer-v1",
        permission_profile_id="permissions-v1",
        budget=_BUDGET,
        target_workspace="/tmp/bridger-output/architecture",
    )
    target_state = TargetTaskState(
        target_task_id=target_spec.target_task_id,
        fleet_run_id=fleet_spec.fleet_run_id,
        phase=TargetPhase.SCHEDULED,
        usage=ExecutionUsage(
            cycles=2,
            model_calls=3,
            tool_calls=5,
            repair_cycles=1,
            input_tokens=1_000,
            output_tokens=500,
        ),
        last_checkpoint_ref="checkpoint-private",
        last_progress_signature="progress-private",
        stall_count=2,
    )
    completion_state = TargetCompletionState(
        target_task_id=target_spec.target_task_id,
        items=[
            CompletionItemState(
                obligation_id="first-contract-item",
                status=CompletionStatus.COVERED,
                resolution_note="Covered with source evidence.",
            ),
            CompletionItemState(obligation_id="second-contract-item"),
        ],
    )
    worker_profile = WorkerProfile(
        profile_id="worker-v1",
        model="gpt-5.6-terra",
        tokenizer_encoding="o200k_base",
        model_context_window_tokens=1_050_000,
        reserved_response_tokens=128_000,
    )
    return HydrationFixture(
        fleet_spec=fleet_spec,
        target_spec=target_spec,
        target_state=target_state,
        completion_state=completion_state,
        catalog=catalog,
        definition=definition,
        worker_profile=worker_profile,
        permission_profile=PermissionProfile(
            profile_id="permissions-v1",
            allowed_tool_ids=("repository_search", "workspace_read"),
        ),
        worker_instructions=WorkerInstructions(
            worker_profile_id=worker_profile.profile_id,
            target_id=definition.target_id,
            target_contract_version=definition.target_contract_version,
            shared="Stable shared worker instructions.",
            target_specific="Stable architecture worker instructions.",
        ),
        state_reader=FakeHydrationStateReader(),
    )


def _fixture_with_shipped_architecture() -> HydrationFixture:
    fixture = _fixture()
    catalog, definitions = load_target_artifacts(_DEFAULT_TARGETS_ROOT)
    definition = next(
        definition
        for definition in definitions
        if definition.target_id == "architecture"
    )
    fixture.catalog = catalog
    fixture.definition = definition
    fixture.fleet_spec = fixture.fleet_spec.model_copy(
        update={
            "target_catalog_id": catalog.catalog_id,
            "target_catalog_version": catalog.catalog_version,
        }
    )
    fixture.target_spec = fixture.target_spec.model_copy(
        update={"target_contract_version": definition.target_contract_version}
    )
    fixture.completion_state = TargetCompletionState(
        target_task_id=fixture.target_spec.target_task_id,
        items=[
            CompletionItemState(obligation_id=obligation.obligation_id)
            for obligation in definition.completion_obligations
        ],
    )
    fixture.worker_instructions = fixture.worker_instructions.model_copy(
        update={"target_contract_version": definition.target_contract_version}
    )
    return fixture


def _question(question_id: str, content: str) -> OpenQuestionRecord:
    return OpenQuestionRecord(
        question_id=question_id,
        target_task_id="task-architecture",
        content=content,
    )


def _add_artifact(
    fixture: HydrationFixture,
    artifact_id: str,
    relative_path: str,
    *,
    revision: int = 1,
) -> CandidateArtifactRef:
    reference = CandidateArtifactRef(
        artifact_id=artifact_id,
        relative_path=relative_path,
        revision=revision,
        digest=f"digest-{artifact_id}-{revision}",
    )
    fixture.target_state.artifact_refs.append(reference)
    fixture.state_reader.artifacts[artifact_id] = CandidateArtifactRecord(
        artifact_id=artifact_id,
        target_task_id=fixture.target_spec.target_task_id,
        target_workspace=fixture.target_spec.target_workspace,
        relative_path=relative_path,
        revision=revision,
        digest=reference.digest,
    )
    return reference
