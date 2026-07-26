"""Explicit orchestration for building a Context Plan from deterministic evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from pydantic import JsonValue, ValidationError

from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.deterministic.context_plan.control_tools import (
    CONTROL_TOOL_NAMES,
    WorkingStateOperationExecutor,
    control_tool_definitions,
)
from bridger.deterministic.context_plan.discovery_tools import (
    DiscoveryToolExecutor,
    FileExcerptOutput,
    tool_call_request_from_llm_call,
    tool_result_to_llm_message,
)
from bridger.deterministic.context_plan.prompts import (
    ContextPlanPrompt,
    ContextPlanRepairPromptInput,
    FinalSynthesisPromptInput,
    InvestigationPromptInput,
    OrientationPromptInput,
    build_context_plan_repair_prompt,
    build_final_synthesis_prompt,
    build_investigation_prompt,
    build_orientation_prompt,
)
from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    ContextPlanRunState,
    DiscoveryBudgetPolicy,
    ToolCallFingerprinter,
)
from bridger.deterministic.context_plan.synthesis_projector import (
    SynthesisProjector,
)
from bridger.deterministic.context_plan.validation import (
    ContextPlanValidationError,
    ContextPlanWriteResult,
    validate_context_plan,
    validate_context_plan_inspection,
    write_context_plan,
)
from bridger.deterministic.context_plan.working_state import (
    WorkingStateMutationService,
    WorkingStateStore,
)
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMStructuredOutputError
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMReasoningConfig,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    LLMUsage,
)
from bridger.models.context_plan import (
    ContextPlan,
    ContextPlanFinalizationRequest,
    ContextPlanInspectedSymbol,
    ContextPlanRepository,
    ContextPlanRun,
    ContextPlanRunOutput,
    ContextPlanRunPhase,
    ContextPlanRunStatus,
    ContextPlanValidationIssue,
    FinalizationDecision,
    FinalizationDecisionCode,
    ToolBudgetCost,
    ToolCallRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from bridger.models.context_plan_bootstrap import ContextPlanBootstrapArtifact
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import ManifestFile, RepoContextArtifact
from bridger.models.symbol_index import SymbolIndexArtifact
from bridger.models.working_state import (
    ContextPlanWorkingState,
    ContextPlanWorkingStateSummary,
    EvidenceKind,
    EvidenceRecord,
)
from bridger.tools.services.artifact_store import ArtifactStore

FINALIZATION_TOOL_NAME = "request_context_plan_finalization"

OrientationPromptBuilder = Callable[[OrientationPromptInput], ContextPlanPrompt]
InvestigationPromptBuilder = Callable[[InvestigationPromptInput], ContextPlanPrompt]
SynthesisPromptBuilder = Callable[[FinalSynthesisPromptInput], ContextPlanPrompt]
RepairPromptBuilder = Callable[[ContextPlanRepairPromptInput], ContextPlanPrompt]
ContextPlanValidator = Callable[
    [ContextPlan | dict[str, object], FileIndexArtifact], ContextPlan
]
ContextPlanWriter = Callable[
    [Path, ContextPlan | dict[str, object], FileIndexArtifact],
    ContextPlanWriteResult,
]
ContextPlanRunStateFactory = Callable[..., ContextPlanRunState]
ToolCallFingerprint = Callable[[ToolCallRequest], str]


class ContextPlanBuilder:
    """Coordinate one bounded, provider-independent Context Plan run."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        artifact_store: ArtifactStore,
        tool_executor: DiscoveryToolExecutor,
        budget_policy: DiscoveryBudgetPolicy,
        completion_policy: ContextPlanCompletionPolicy,
        run_recorder: ContextPlanRunRecorder,
        context_plan_destination: Path,
        model_profile: str = "balanced",
        model_name: str | None = None,
        run_state_factory: ContextPlanRunStateFactory = ContextPlanRunState,
        tool_call_fingerprint: ToolCallFingerprint = (
            ToolCallFingerprinter.fingerprint
        ),
        orientation_prompt_builder: OrientationPromptBuilder = (
            build_orientation_prompt
        ),
        investigation_prompt_builder: InvestigationPromptBuilder = (
            build_investigation_prompt
        ),
        synthesis_prompt_builder: SynthesisPromptBuilder = (
            build_final_synthesis_prompt
        ),
        repair_prompt_builder: RepairPromptBuilder = build_context_plan_repair_prompt,
        context_plan_validator: ContextPlanValidator = validate_context_plan,
        context_plan_writer: ContextPlanWriter = write_context_plan,
        working_state_destination: Path | None = None,
        synthesis_projector: SynthesisProjector | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._artifact_store = artifact_store
        self._tool_executor = tool_executor
        self._budget_policy = budget_policy
        self._completion_policy = completion_policy
        self._run_recorder = run_recorder
        self._context_plan_destination = context_plan_destination
        self._model_profile = model_profile
        self._model_name = model_name
        self._run_state_factory = run_state_factory
        self._fingerprint = tool_call_fingerprint
        self._build_orientation_prompt = orientation_prompt_builder
        self._build_investigation_prompt = investigation_prompt_builder
        self._build_synthesis_prompt = synthesis_prompt_builder
        self._build_repair_prompt = repair_prompt_builder
        self._validate_context_plan = context_plan_validator
        self._write_context_plan = context_plan_writer
        self._working_state_destination = (
            working_state_destination
            or run_recorder.destination.with_name("context-plan-working-state.json")
        )
        self._synthesis_projector = synthesis_projector or SynthesisProjector()
        self._control_executor: WorkingStateOperationExecutor | None = None

    async def build(
        self,
        *,
        run_id: str,
        initial_warnings: Sequence[str] = (),
        open_questions: Sequence[str] = (),
    ) -> ContextPlanRun:
        """Run discovery through validated, atomic Context Plan persistence."""

        state: ContextPlanRunState | None = None
        try:
            (
                file_index,
                repo_context,
                symbol_index,
                context_plan_bootstrap,
            ) = self._load_required_artifacts()
            state = self._initialize_state(run_id, context_plan_bootstrap, file_index)
            self._run_recorder.persist(state)
            state.start()
            self._run_recorder.persist(state)

            finalization, warnings, questions = await self._run_investigation(
                state=state,
                context_plan_bootstrap=context_plan_bootstrap,
                file_index=file_index,
                symbol_index=symbol_index,
                repo_context=repo_context,
                initial_warnings=list(initial_warnings),
                open_questions=list(open_questions),
            )
            if finalization is None:
                return self._run_recorder.persist(state)

            return await self._run_synthesis(
                state=state,
                finalization=finalization,
                warnings=warnings,
                open_questions=questions,
                file_index=file_index,
                context_plan_bootstrap=context_plan_bootstrap,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            if state is not None:
                state.interrupt()
                self._run_recorder.persist(state)
            raise
        except Exception as error:
            if state is not None and state.status not in {
                ContextPlanRunStatus.COMPLETED,
                ContextPlanRunStatus.FAILED,
                ContextPlanRunStatus.INTERRUPTED,
            }:
                state.fail(self._error_message(error))
                self._run_recorder.persist(state)
            raise

    def _load_required_artifacts(
        self,
    ) -> tuple[
        FileIndexArtifact,
        RepoContextArtifact,
        SymbolIndexArtifact,
        ContextPlanBootstrapArtifact,
    ]:
        file_index = self._artifact_store.load_file_index()
        repo_context = self._artifact_store.load_repo_context()
        symbol_index = self._artifact_store.load_symbol_index()
        context_plan_bootstrap = self._artifact_store.load_context_plan_bootstrap()
        return file_index, repo_context, symbol_index, context_plan_bootstrap

    def _initialize_state(
        self,
        run_id: str,
        context_plan_bootstrap: ContextPlanBootstrapArtifact,
        file_index: FileIndexArtifact,
    ) -> ContextPlanRunState:
        state = self._run_state_factory(
            run_id=run_id,
            repo=ContextPlanRepository(
                root_name=context_plan_bootstrap.repo.root_name,
                revision=context_plan_bootstrap.repo.revision,
            ),
            safe_file_count=len(file_index.files),
            model_profile=self._model_profile,
            model_name=self._model_name,
        )
        working_state = ContextPlanWorkingState(
            run_id=run_id,
            repository_revision=context_plan_bootstrap.repo.revision,
            updated_at=state.updated_at,
        )
        service = WorkingStateMutationService(
            working_state,
            WorkingStateStore(self._working_state_destination),
            total_lines_by_path={
                item.path: item.line_count for item in file_index.files
            },
        )
        state.configure_working_state(
            service,
            self._artifact_relative_path(self._working_state_destination),
        )
        self._control_executor = WorkingStateOperationExecutor(service)
        return state

    async def _run_investigation(
        self,
        *,
        state: ContextPlanRunState,
        context_plan_bootstrap: ContextPlanBootstrapArtifact,
        file_index: FileIndexArtifact,
        symbol_index: SymbolIndexArtifact,
        repo_context: RepoContextArtifact,
        initial_warnings: list[str],
        open_questions: list[str],
    ) -> tuple[
        ContextPlanFinalizationRequest | None,
        list[str],
        list[str],
    ]:
        history: list[LLMMessage] = []
        latest_results: list[ToolExecutionResult] = []
        warnings = list(initial_warnings)
        questions = list(open_questions)
        findings: list[str] = []
        orientation = True

        while state.status is ContextPlanRunStatus.RUNNING:
            if self._terminate_for_runtime_state(state):
                break

            if orientation:
                prompt = self._build_orientation_prompt(
                    OrientationPromptInput(
                        context_plan_bootstrap=context_plan_bootstrap,
                        file_index=file_index,
                        symbol_index=symbol_index,
                        repository_context=repo_context,
                        available_tools=self._available_tools(),
                        run_budget_limits=self._budget_policy.limits,
                        initial_warnings=warnings,
                    )
                )
            else:
                state.set_phase(ContextPlanRunPhase.INVESTIGATION)
                prompt = self._build_investigation_prompt(
                    InvestigationPromptInput(
                        interaction_history=history,
                        latest_tool_results=latest_results,
                        inspection=state.coverage.snapshot(),
                        discovered_paths=sorted(state.coverage.discovered_paths),
                        evidence_paths=sorted(state.coverage.evidence_paths),
                        remaining_budgets=(
                            self._budget_policy.remaining_budget_summary(state)
                        ),
                        warnings=warnings,
                        open_questions=questions,
                        investigation_notes=findings,
                        working_state_summary=self._working_state_summary(state),
                        working_state_entities=self._working_state_entities(state),
                        available_tools=self._available_tools(),
                    )
                )

            response = await self._generate(
                state,
                prompt,
                phase=state.phase,
                reserve_synthesis=True,
            )
            if response is None:
                break

            history.append(prompt.messages[-1])
            history.append(self._assistant_message(response))
            warnings.extend(response.warnings)
            if response.text:
                findings.append(response.text)

            if not response.tool_calls:
                latest_results = []
                state.record_no_progress_turn()
                warnings.append(
                    "Assistant response made no structured tool call; prose does "
                    "not complete Context Plan investigation."
                )
                self._run_recorder.persist(state)
                orientation = False
                continue

            if self._is_mixed_finalization_response(response.tool_calls):
                latest_results = self._reject_mixed_tool_calls(
                    state, response.tool_calls
                )
                history.extend(
                    tool_result_to_llm_message(item) for item in latest_results
                )
                warnings.append(
                    "Mixed repository and finalization tool calls were rejected; "
                    "finalization must be the only tool call in a response."
                )
                self._run_recorder.persist(state)
                orientation = False
                continue

            latest_results = []
            finalization_call = (
                response.tool_calls[0]
                if response.tool_calls[0].name == FINALIZATION_TOOL_NAME
                else None
            )
            if finalization_call is not None:
                request, result, decision = self._process_finalization_call(
                    state, finalization_call
                )
                latest_results.append(result)
                history.append(tool_result_to_llm_message(result))
                self._run_recorder.persist(state)
                if decision.accepted and request is not None:
                    return request, warnings, questions
                warnings.extend(
                    f"{issue.code}: {issue.message}" for issue in decision.issues
                )
                if request is not None:
                    questions.extend(request.unresolved_areas)
                orientation = False
                continue

            for tool_call in response.tool_calls:
                result, duplicate_warning = self._process_repository_tool_call(
                    state, tool_call
                )
                latest_results.append(result)
                history.append(tool_result_to_llm_message(result))
                if duplicate_warning is not None:
                    warnings.append(duplicate_warning)
                if result.status is not ToolExecutionStatus.COMPLETED:
                    warnings.extend(
                        f"{issue.code}: {issue.message}" for issue in result.issues
                    )
                self._run_recorder.persist(state)
                if state.status is not ContextPlanRunStatus.RUNNING:
                    break

            orientation = False

        return None, warnings, questions

    def _process_repository_tool_call(
        self,
        state: ContextPlanRunState,
        tool_call: LLMToolCall,
    ) -> tuple[ToolExecutionResult, str | None]:
        request = tool_call_request_from_llm_call(tool_call)
        definition = self._tool_executor.registry.get(request.name)
        estimated_cost = (
            definition.estimated_cost if definition is not None else ToolBudgetCost()
        )
        fingerprint = self._fingerprint(request)
        duplicate = state.fingerprint_counts.get(fingerprint, 0) > 0
        preflight = self._budget_policy.preflight_tool_call(
            state, estimated_cost, fingerprint
        )
        recorded_fingerprint = state.record_tool_request(request, estimated_cost)
        if recorded_fingerprint != fingerprint:
            raise ValueError("injected tool fingerprint does not match run state")

        if not preflight.allowed:
            result = self._preflight_rejection(
                request, estimated_cost, preflight.reasons
            )
        elif request.name in CONTROL_TOOL_NAMES:
            result = self._execute_control_tool(request, estimated_cost)
        else:
            result = self._tool_executor.execute(request)
        state.record_tool_result(result, fingerprint)
        if result.status is ToolExecutionStatus.FAILED:
            issue_codes = ", ".join(issue.code for issue in result.issues)
            state.record_error(
                f"Tool {request.name} failed"
                + (f": {issue_codes}" if issue_codes else "")
            )

        if preflight.hard_budget_exhausted:
            state.mark_budget_exhausted()
        elif state.is_stalled(self._budget_policy):
            state.mark_stalled()
        elif self._budget_policy.hard_budget_exhausted(state):
            state.mark_budget_exhausted()

        warning = (
            f"Duplicate tool call detected for {request.name}." if duplicate else None
        )
        return result, warning

    def _process_finalization_call(
        self,
        state: ContextPlanRunState,
        tool_call: LLMToolCall,
    ) -> tuple[
        ContextPlanFinalizationRequest | None,
        ToolExecutionResult,
        FinalizationDecision,
    ]:
        request = tool_call_request_from_llm_call(tool_call)
        definition = self._tool_executor.registry.get(request.name)
        assert definition is not None
        fingerprint = self._fingerprint(request)
        preflight = self._budget_policy.preflight_tool_call(
            state, definition.estimated_cost, fingerprint
        )
        recorded_fingerprint = state.record_tool_request(
            request, definition.estimated_cost
        )
        if recorded_fingerprint != fingerprint:
            raise ValueError("injected tool fingerprint does not match run state")

        if not preflight.allowed:
            result = self._preflight_rejection(
                request, definition.estimated_cost, preflight.reasons
            )
            state.record_tool_result(result, fingerprint)
            if preflight.hard_budget_exhausted:
                state.mark_budget_exhausted()
            decision = FinalizationDecision(
                accepted=False,
                code=(
                    FinalizationDecisionCode.BUDGET_EXHAUSTED
                    if preflight.hard_budget_exhausted
                    else FinalizationDecisionCode.INVALID_REQUEST
                ),
                issues=result.issues,
            )
            return None, result, decision

        state.set_phase(ContextPlanRunPhase.FINALIZATION)
        try:
            validated_request = ContextPlanFinalizationRequest.model_validate(
                request.arguments
            )
        except ValidationError:
            validated_request = None
            decision = self._completion_policy.evaluate(
                request.arguments,
                state.finalization_context(self._budget_policy),
            )
        else:
            assert validated_request is not None
            state.record_finalization_request(validated_request)
            decision = self._completion_policy.evaluate(
                validated_request,
                state.finalization_context(self._budget_policy),
            )

        result = ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.COMPLETED,
            output=cast(
                dict[str, JsonValue],
                {"decision": decision.model_dump(mode="json")},
            ),
            issues=[],
            estimated_cost=definition.estimated_cost,
            actual_cost=ToolBudgetCost(),
        )
        state.record_tool_result(result, fingerprint)
        if not decision.accepted:
            state.record_finalization_rejected()
            state.set_phase(ContextPlanRunPhase.INVESTIGATION)
            if state.is_stalled(self._budget_policy):
                state.mark_stalled()
        return validated_request, result, decision

    def _reject_mixed_tool_calls(
        self,
        state: ContextPlanRunState,
        tool_calls: list[LLMToolCall],
    ) -> list[ToolExecutionResult]:
        results: list[ToolExecutionResult] = []
        for tool_call in tool_calls:
            request = tool_call_request_from_llm_call(tool_call)
            definition = self._tool_executor.registry.get(request.name)
            estimated_cost = (
                definition.estimated_cost
                if definition is not None
                else ToolBudgetCost()
            )
            fingerprint = state.record_tool_request(request, estimated_cost)
            result = ToolExecutionResult(
                call_id=request.call_id,
                tool_name=request.name,
                status=ToolExecutionStatus.REJECTED,
                issues=[
                    self._issue(
                        "mixed_finalization_response",
                        "Finalization must be the only tool call in the response",
                        ["tool_calls"],
                    )
                ],
                estimated_cost=estimated_cost,
                actual_cost=ToolBudgetCost(tool_calls=0),
            )
            state.record_tool_result(result, fingerprint)
            results.append(result)
        if state.is_stalled(self._budget_policy):
            state.mark_stalled()
        return results

    async def _run_synthesis(
        self,
        *,
        state: ContextPlanRunState,
        finalization: ContextPlanFinalizationRequest,
        warnings: list[str],
        open_questions: list[str],
        file_index: FileIndexArtifact,
        context_plan_bootstrap: ContextPlanBootstrapArtifact,
    ) -> ContextPlanRun:
        if state.working_state_service is None:
            raise ValueError("working state is not configured")
        projection = self._synthesis_projector.project(
            state.working_state_service.state,
            priority_paths=finalization.key_evidence_paths,
        )
        state.record_synthesis_manifest(projection.manifest)
        self._run_recorder.persist(state)
        selected_paths = {
            item.path for item in projection.evidence if item.path is not None
        }
        excerpts = [
            FileExcerptOutput(
                source_artifact=str(
                    item.structured_payload.get(
                        "source_artifact", "context-plan-working-state"
                    )
                ),
                path=item.path,
                line_start=item.line_ranges[0].line_start,
                line_end=item.line_ranges[0].line_end,
                content=item.content or "",
                truncated=item.truncated,
            )
            for item in projection.evidence
            if (
                item.kind is EvidenceKind.FILE_EXCERPT
                and item.path is not None
                and item.line_ranges
            )
        ]
        manifests = [
            ManifestFile.model_validate(item.structured_payload)
            for item in projection.evidence
            if item.kind is EvidenceKind.MANIFEST_FACT
        ]
        omitted_warning = (
            [
                "Synthesis projection omitted "
                f"{projection.manifest.omitted_record_count} evidence records; "
                "see synthesis_input_manifest for explicit reasons."
            ]
            if projection.manifest.omitted_record_count
            else []
        )
        synthesis_input = FinalSynthesisPromptInput(
            context_plan_bootstrap=context_plan_bootstrap,
            validated_evidence_paths=sorted(selected_paths),
            inspected_excerpts=excerpts,
            inspected_symbols=[
                self._inspected_symbol(item)
                for item in projection.evidence
                if item.kind is EvidenceKind.SYMBOL_METADATA
                and item.symbol_id is not None
            ],
            manifest_evidence=manifests,
            collected_findings=[item.statement for item in projection.findings],
            warnings=[*warnings, *omitted_warning],
            unknowns=[
                *open_questions,
                *finalization.unresolved_areas,
                *(item.question for item in projection.questions),
            ],
            synthesis_manifest=projection.manifest,
            selected_candidates=list(projection.candidates),
            selected_findings=list(projection.findings),
            selected_relationships=list(projection.relationships),
            selected_questions=list(projection.questions),
            selected_evidence=list(projection.evidence),
        )
        prompt = self._build_synthesis_prompt(synthesis_input)

        state.record_synthesis_started()
        self._run_recorder.persist(state)
        try:
            response = await self._generate(
                state,
                prompt,
                phase=ContextPlanRunPhase.SYNTHESIS,
                reserve_synthesis=False,
            )
        except LLMStructuredOutputError as error:
            invalid_output, issues = self._structured_output_failure(
                error,
                file_index,
                location=["synthesis"],
            )
            state.record_validation_attempt(False, issues)
            self._run_recorder.persist(state)
            return await self._run_repair(
                state=state,
                synthesis_input=synthesis_input,
                invalid_output=invalid_output,
                validation_issues=issues,
                validation_file_index=file_index,
                write_file_index=file_index,
            )

        if response is None:
            return self._run_recorder.persist(state)
        if response.structured_output is None:
            issue = self._issue(
                "structured_output_missing",
                "Synthesis did not return a structured ContextPlan",
                ["synthesis"],
            )
            state.record_validation_attempt(False, [issue])
            self._run_recorder.persist(state)
            return await self._run_repair(
                state=state,
                synthesis_input=synthesis_input,
                invalid_output={
                    "_bridger_invalid_output": (
                        response.text
                        or response.refusal
                        or "Structured output was not returned"
                    )
                },
                validation_issues=[issue],
                validation_file_index=file_index,
                write_file_index=file_index,
            )

        try:
            plan = self._validate_synthesized_plan(
                state, response.structured_output, file_index
            )
        except ContextPlanValidationError as error:
            state.record_validation_attempt(False, error.issues)
            self._run_recorder.persist(state)
            return await self._run_repair(
                state=state,
                synthesis_input=synthesis_input,
                invalid_output=response.structured_output.model_dump(mode="json"),
                validation_issues=error.issues,
                validation_file_index=file_index,
                write_file_index=file_index,
            )

        state.record_validation_attempt(True, [])
        self._run_recorder.persist(state)
        return self._write_completed_plan(state, plan, file_index)

    async def _run_repair(
        self,
        *,
        state: ContextPlanRunState,
        synthesis_input: FinalSynthesisPromptInput,
        invalid_output: JsonValue,
        validation_issues: list[ContextPlanValidationIssue],
        validation_file_index: FileIndexArtifact,
        write_file_index: FileIndexArtifact,
    ) -> ContextPlanRun:
        prompt = self._build_repair_prompt(
            ContextPlanRepairPromptInput(
                invalid_output=invalid_output,
                validation_issues=validation_issues,
                synthesis_evidence=synthesis_input,
            )
        )
        state.record_repair_started()
        self._run_recorder.persist(state)
        try:
            response = await self._generate(
                state,
                prompt,
                phase=ContextPlanRunPhase.SYNTHESIS,
                reserve_synthesis=False,
                attempt="repair",
            )
        except LLMStructuredOutputError as error:
            _, issues = self._structured_output_failure(
                error,
                validation_file_index,
                location=["repair"],
            )
            state.record_validation_attempt(False, issues)
            state.record_repair_completed(False)
            self._run_recorder.persist(state)
            raise ContextPlanValidationError(issues) from error

        if response is None:
            state.record_error(
                "Validation repair was not attempted because the model or time "
                "budget was unavailable"
            )
            self._run_recorder.persist(state)
            raise ContextPlanValidationError(validation_issues)
        if response.structured_output is None:
            issue = self._issue(
                "structured_output_missing",
                "Repair did not return a structured ContextPlan",
                ["repair"],
            )
            state.record_validation_attempt(False, [issue])
            state.record_repair_completed(False)
            self._run_recorder.persist(state)
            raise ContextPlanValidationError([issue])

        try:
            plan = self._validate_synthesized_plan(
                state,
                response.structured_output,
                validation_file_index,
            )
        except ContextPlanValidationError as error:
            state.record_validation_attempt(False, error.issues)
            state.record_repair_completed(False)
            self._run_recorder.persist(state)
            raise

        state.record_validation_attempt(True, [])
        state.record_repair_completed(True)
        self._run_recorder.persist(state)
        return self._write_completed_plan(state, plan, write_file_index)

    def _write_completed_plan(
        self,
        state: ContextPlanRunState,
        plan: ContextPlan,
        file_index: FileIndexArtifact,
    ) -> ContextPlanRun:
        state.set_phase(ContextPlanRunPhase.WRITING)
        self._run_recorder.persist(state)
        write_result = self._write_context_plan(
            self._context_plan_destination,
            plan,
            file_index,
        )
        state.record_artifact_written(
            ContextPlanRunOutput(
                artifact_path=self._artifact_relative_path(write_result.path),
                sha256=write_result.sha256,
            )
        )
        self._run_recorder.persist(state)
        state.complete()
        return self._run_recorder.persist(state)

    async def _generate(
        self,
        state: ContextPlanRunState,
        prompt: ContextPlanPrompt,
        *,
        phase: ContextPlanRunPhase,
        reserve_synthesis: bool,
        attempt: str | None = None,
    ) -> LLMResponse[ContextPlan] | None:
        token_limit = self._budget_policy.limits.token_usage
        if token_limit is not None and state.token_usage >= token_limit:
            if attempt == "repair":
                state.record_repair_budget_rejected(("token_usage",))
            state.mark_budget_exhausted()
            self._run_recorder.persist(state)
            return None

        preflight = self._budget_policy.preflight_model_turn(
            state,
            reserved_turns=1 if reserve_synthesis else 0,
        )
        if not preflight.allowed:
            if attempt == "repair":
                state.record_repair_budget_rejected(preflight.reasons)
            state.mark_budget_exhausted()
            self._run_recorder.persist(state)
            return None

        metadata = {"context_plan_phase": phase.value}
        if attempt is not None:
            metadata["context_plan_attempt"] = attempt
        request = LLMRequest(
            operation=LLMOperation.CONTEXT_PLAN_GENERATION,
            profile=self._model_profile,
            messages=list(prompt.messages),
            tools=list(prompt.tools),
            reasoning=LLMReasoningConfig(effort="high"),
            metadata=metadata,
        )
        state.record_model_call_started()
        try:
            response = await self._llm_client.generate(
                request,
                output_type=prompt.output_type,
            )
        except Exception as error:
            usage = (
                error.usage
                if isinstance(error, LLMStructuredOutputError)
                else LLMUsage()
            )
            latency_ms = (
                error.latency_ms
                if isinstance(error, LLMStructuredOutputError)
                else None
            )
            if isinstance(error, LLMStructuredOutputError) and error.model:
                state.model_name = error.model
            self._record_model_usage(state, usage, latency_ms)
            self._run_recorder.persist(state)
            raise
        state.model_name = response.model
        self._record_model_usage(state, response.usage, response.latency_ms)
        self._run_recorder.persist(state)
        return cast(LLMResponse[ContextPlan], response)

    def _terminate_for_runtime_state(self, state: ContextPlanRunState) -> bool:
        if state.is_stalled(self._budget_policy):
            state.mark_stalled()
            self._run_recorder.persist(state)
            return True
        if self._budget_policy.hard_budget_exhausted(state):
            state.mark_budget_exhausted()
            self._run_recorder.persist(state)
            return True
        return False

    def _available_tools(self) -> list[LLMToolDefinition]:
        return [
            *self._tool_executor.registry.llm_definitions(),
            *control_tool_definitions(),
        ]

    def _execute_control_tool(
        self,
        request: ToolCallRequest,
        estimated_cost: ToolBudgetCost,
    ) -> ToolExecutionResult:
        if self._control_executor is None:
            raise ValueError("working-state operation executor is not configured")
        operation_result = self._control_executor.execute(
            request.name,
            request.arguments,
        )
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=(
                ToolExecutionStatus.COMPLETED
                if operation_result.status == "completed"
                else ToolExecutionStatus.REJECTED
            ),
            output=cast(
                dict[str, JsonValue],
                operation_result.model_dump(mode="json"),
            ),
            issues=operation_result.issues,
            estimated_cost=estimated_cost,
            actual_cost=ToolBudgetCost(),
        )

    @staticmethod
    def _working_state_summary(
        state: ContextPlanRunState,
    ) -> ContextPlanWorkingStateSummary | None:
        if state.working_state_service is None:
            return None
        return state.working_state_service.state.summary()

    @staticmethod
    def _working_state_entities(
        state: ContextPlanRunState,
    ) -> dict[str, JsonValue]:
        if state.working_state_service is None:
            return {}
        working_state = state.working_state_service.state
        recent_evidence = sorted(
            working_state.evidence,
            key=lambda item: (item.sequence_number, item.evidence_id),
            reverse=True,
        )[:25]
        return cast(
            dict[str, JsonValue],
            {
                "recent_evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "kind": item.kind.value,
                        "path": item.path,
                        "line_ranges": [
                            value.model_dump(mode="json") for value in item.line_ranges
                        ],
                        "symbol_id": item.symbol_id,
                        "inspection_level": item.inspection_level.value,
                        "area_key": item.area_key,
                    }
                    for item in recent_evidence
                ],
                "findings": [
                    item.model_dump(mode="json") for item in working_state.findings
                ],
                "relationships": [
                    item.model_dump(mode="json") for item in working_state.relationships
                ],
                "open_questions": [
                    item.model_dump(mode="json")
                    for item in working_state.open_questions
                ],
                "package_candidates": [
                    item.model_dump(mode="json")
                    for item in working_state.package_candidates
                ],
            },
        )

    @staticmethod
    def _inspected_symbol(record: EvidenceRecord) -> ContextPlanInspectedSymbol:
        assert record.symbol_id is not None
        return ContextPlanInspectedSymbol(
            identifier=record.symbol_id,
            path=record.path,
        )

    def _validate_synthesized_plan(
        self,
        state: ContextPlanRunState,
        payload: ContextPlan | dict[str, object],
        file_index: FileIndexArtifact,
    ) -> ContextPlan:
        plan = self._validate_context_plan(payload, file_index)
        if state.working_state_service is None:
            raise ValueError("working state is not configured")
        return validate_context_plan_inspection(
            plan,
            state.working_state_service.state,
        )

    def _preflight_rejection(
        self,
        request: ToolCallRequest,
        estimated_cost: ToolBudgetCost,
        reasons: tuple[str, ...],
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.REJECTED,
            issues=[
                self._issue(
                    "tool_budget_rejected",
                    "Tool call was rejected by budget preflight",
                    ["budget"],
                    {"reasons": list(reasons)},
                )
            ],
            estimated_cost=estimated_cost,
            actual_cost=ToolBudgetCost(tool_calls=0),
        )

    @staticmethod
    def _assistant_message(response: LLMResponse[ContextPlan]) -> LLMMessage:
        if response.tool_calls:
            return LLMMessage.assistant_tool_calls(response.tool_calls)
        if response.text:
            return LLMMessage.assistant(response.text)
        if response.refusal:
            return LLMMessage.assistant(f"Model refusal: {response.refusal}")
        return LLMMessage.assistant(
            "Structured output was not accepted during investigation."
        )

    @staticmethod
    def _is_mixed_finalization_response(tool_calls: list[LLMToolCall]) -> bool:
        has_finalization = any(
            call.name == FINALIZATION_TOOL_NAME for call in tool_calls
        )
        return has_finalization and len(tool_calls) != 1

    def _artifact_relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self._artifact_store.repo_root).as_posix()

    def _record_model_usage(
        self,
        state: ContextPlanRunState,
        usage: LLMUsage,
        latency_ms: int | None,
    ) -> None:
        token_usage = usage.total_tokens
        if token_usage is None:
            token_usage = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        state.record_model_call_completed(
            token_usage,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cached_input_tokens=usage.cached_input_tokens or 0,
            reasoning_tokens=usage.reasoning_tokens or 0,
            latency_ms=latency_ms or 0,
        )

    def _structured_output_failure(
        self,
        error: LLMStructuredOutputError,
        file_index: FileIndexArtifact,
        *,
        location: list[str | int],
    ) -> tuple[JsonValue, list[ContextPlanValidationIssue]]:
        if isinstance(error.invalid_output, dict):
            try:
                self._validate_context_plan(
                    cast(dict[str, object], error.invalid_output),
                    file_index,
                )
            except ContextPlanValidationError as validation_error:
                return error.invalid_output, validation_error.issues

        invalid_output: JsonValue = (
            error.invalid_output
            if error.invalid_output is not None
            else {"_bridger_invalid_output_unavailable": error.safe_message}
        )
        issue = self._issue(
            "structured_output_error",
            error.safe_message,
            location,
        )
        return invalid_output, [issue]

    @staticmethod
    def _issue(
        code: str,
        message: str,
        location: list[str | int],
        context: dict[str, JsonValue] | None = None,
    ) -> ContextPlanValidationIssue:
        return ContextPlanValidationIssue(
            code=code,
            location=location,
            message=message,
            context=context or {},
        )

    @staticmethod
    def _error_message(error: Exception) -> str:
        message = str(error).strip()
        return f"{type(error).__name__}: {message or 'operation failed'}"
