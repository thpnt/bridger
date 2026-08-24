"""Fresh read-only Stage 8 review of one exact validated target candidate."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import NoReturn

import orjson
from pydantic import ValidationError

from bridger.contracts.memory.core import (
    FindingOrigin,
    FindingRef,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.hydration import WorkerProfile
from bridger.contracts.memory.persistence import TargetFinalizationRequest
from bridger.contracts.memory.review import (
    ReviewArtifact,
    ReviewerInstructions,
    ReviewFinding,
    ReviewFindingDraft,
    ReviewVerdict,
    TargetReviewContext,
    TargetReviewModelResult,
    TargetReviewVerdict,
)
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMError, LLMStructuredOutputError
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMReasoningConfig,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from bridger.memory.errors import (
    PersistenceRecoveryError,
    TargetReviewBudgetError,
    TargetReviewError,
    TargetReviewInvocationError,
)
from bridger.memory.evaluation.validation import (
    resolve_validation_report,
    resolve_validation_subject,
)
from bridger.memory.persistence.durability import (
    FleetRuntimeStore,
    _model_bytes,
    _replace_model,
)
from bridger.memory.persistence.recovery import validate_checkpoint
from bridger.memory.runtime.context_window import ContextWindowManager
from bridger.memory.runtime.provider_recovery import run_provider_with_retry
from bridger.memory.runtime.trace import (
    model_error_trace_payload,
    model_request_trace_context,
    model_response_trace_payload,
)
from bridger.memory.runtime.worker_cycle import (
    FleetExecutionCoordinator,
    _BudgetScope,
    _BudgetStop,
)


def compile_target_review_context(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition,
    reviewer_profile: WorkerProfile,
    reviewer_instructions: ReviewerInstructions,
) -> TargetReviewContext:
    """Compile one exact checkpoint-backed reviewer context without mutation."""
    _validate_review_authorities(
        store,
        target_spec,
        target_state,
        catalog,
        target_definition,
        reviewer_profile,
        reviewer_instructions,
    )
    try:
        request, checkpoint = resolve_validation_subject(
            store,
            target_spec,
            target_state,
        )
        report = resolve_validation_report(
            store,
            target_spec,
            request.finalization_request_id,
        )
        if (
            report is None
            or report.verdict is not ValidationVerdict.PASS
            or report.candidate_checkpoint_ref != checkpoint.checkpoint_id
            or report.finding_refs
        ):
            raise ValueError("target review requires the exact Stage 7 PASS report")
        artifacts = _load_checkpoint_artifacts(store, target_spec, checkpoint)
        return TargetReviewContext(
            target_task_id=target_spec.target_task_id,
            target_id=target_spec.target_id,
            target_contract_version=target_spec.target_contract_version,
            finalization_request_id=request.finalization_request_id,
            candidate_checkpoint_ref=checkpoint.checkpoint_id,
            validation_report_ref=report.validation_report_id,
            source_binding=target_spec.source,
            reviewer_profile_id=reviewer_profile.profile_id,
            shared_reviewer_instructions=reviewer_instructions.shared,
            target_reviewer_rubric=reviewer_instructions.target_specific,
            cross_target_ownership_rules=list(catalog.cross_target_ownership_rules),
            target_definition=target_definition,
            completion_state=checkpoint.completion_state,
            open_questions=checkpoint.open_questions,
            candidate_artifacts=artifacts,
            hard_validation_report=report,
        )
    except TargetReviewError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise TargetReviewError(
            "could not compile an exact Stage 8 review context"
        ) from error


async def review_target(
    *,
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition,
    reviewer_profile: WorkerProfile,
    reviewer_instructions: ReviewerInstructions,
    context_window_manager: ContextWindowManager,
    llm_client: LLMClient,
    coordinator: FleetExecutionCoordinator,
    persistence: FleetRuntimeStore,
    finalization_request_id: str | None = None,
) -> TargetReviewVerdict:
    """Run and durably commit one idempotent Stage 8 target review."""
    request_id = (
        finalization_request_id or target_state.pending_finalization_request_ref
    )
    if request_id is None:
        raise TargetReviewInvocationError(
            "target review requires a finalization request identity"
        )
    existing = resolve_review_verdict(persistence, target_spec, request_id)
    if existing is not None:
        if (
            target_state.pending_finalization_request_ref is not None
            and target_state.pending_finalization_request_ref != request_id
        ):
            raise TargetReviewInvocationError(
                "historical review is not the current target candidate"
            )
        persisted_state = TargetTaskState.model_validate_json(
            persistence.paths.target_state(target_spec).read_bytes()
        )
        _replace_review_state(target_state, persisted_state)
        return existing
    if target_state.pending_finalization_request_ref != request_id:
        raise TargetReviewInvocationError(
            "target review request is not the current pending request"
        )
    if fleet_spec != persistence.fleet_spec:
        raise TargetReviewInvocationError(
            "target review fleet authority does not match persistence"
        )
    if fleet_state.fleet_run_id != fleet_spec.fleet_run_id:
        raise TargetReviewInvocationError("fleet state belongs to another run")
    if context_window_manager.profile != reviewer_profile:
        raise TargetReviewInvocationError(
            "review context-window profile does not match reviewer profile"
        )

    context = compile_target_review_context(
        persistence,
        target_spec,
        target_state,
        catalog,
        target_definition,
        reviewer_profile,
        reviewer_instructions,
    )
    request, input_tokens, output_tokens = _build_review_request(
        fleet_spec,
        fleet_state,
        target_spec,
        target_state,
        context,
        reviewer_profile,
        context_window_manager,
    )
    coordinator.bind_persistence(persistence, fleet_state)
    try:
        reservation = await coordinator.reserve_model_call(
            fleet_spec.fleet_budget,
            fleet_state.usage,
            target_spec.budget,
            target_state.usage,
            input_tokens=input_tokens,
            requested_output_tokens=output_tokens,
            target_state=target_state,
            target_spec=target_spec,
            trace_context=model_request_trace_context(
                request,
                local_request_input_tokens=input_tokens,
                count_tokens=context_window_manager.count_text,
            ),
        )
    except _BudgetStop as stop:
        _raise_review_budget_error(
            persistence,
            target_spec,
            target_state,
            request_id,
            stop,
        )

    request = request.model_copy(
        update={"max_output_tokens": reservation.output_tokens}
    )
    response: LLMResponse[TargetReviewModelResult]
    durable_retry_loop = reservation.attempt_id is not None
    try:
        await coordinator.mark_model_invoked(reservation)
        if durable_retry_loop:
            response = await _generate_with_retries(
                llm_client,
                request,
                coordinator,
                target_spec,
                target_state,
                fleet_state,
                reservation.attempt_id or "",
                context,
            )
        else:
            response = await llm_client.generate(
                request,
                output_type=TargetReviewModelResult,
            )
    except _BudgetStop as stop:
        await coordinator.finish_model_call(
            reservation,
            target_state.usage,
            fleet_state.usage,
            None,
        )
        _raise_review_budget_error(
            persistence,
            target_spec,
            target_state,
            request_id,
            stop,
        )
    except Exception as error:
        failed_usage = getattr(error, "usage", None)
        await coordinator.finish_model_call(
            reservation,
            target_state.usage,
            fleet_state.usage,
            failed_usage if isinstance(failed_usage, LLMUsage) else None,
            trace_payload=model_error_trace_payload(error),
            failed=True,
        )
        if not durable_retry_loop:
            await _charge_client_retries(
                coordinator,
                target_spec,
                target_state,
                fleet_state,
                getattr(error, "attempt_count", 1),
            )
        raise

    await coordinator.finish_model_call(
        reservation,
        target_state.usage,
        fleet_state.usage,
        response.usage,
        trace_payload=model_response_trace_payload(response),
    )
    if response.retry_count and not durable_retry_loop:
        await _charge_client_retries(
            coordinator,
            target_spec,
            target_state,
            fleet_state,
            response.retry_count + 1,
        )
    if response.structured_output is None:
        raise TargetReviewError("reviewer returned no structured result")
    return _complete_review(
        persistence,
        target_spec,
        target_state,
        context,
        response,
    )


def resolve_review_verdict(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    finalization_request_id: str,
) -> TargetReviewVerdict | None:
    """Load and verify the one authoritative review for a finalization request."""
    verdict_id = _review_verdict_id(finalization_request_id)
    path = store.paths.review_verdict(target_spec, verdict_id)
    if not path.exists():
        return None
    try:
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(
                target_spec,
                finalization_request_id,
            ).read_bytes()
        )
        checkpoint = validate_checkpoint(
            store,
            target_spec,
            request.candidate_checkpoint_ref,
        )
        report = resolve_validation_report(
            store,
            target_spec,
            finalization_request_id,
        )
        verdict = TargetReviewVerdict.model_validate_json(path.read_bytes())
        if (
            report is None
            or report.verdict is not ValidationVerdict.PASS
            or verdict.review_verdict_id != verdict_id
            or verdict.fleet_run_id != store.fleet_spec.fleet_run_id
            or verdict.target_task_id != target_spec.target_task_id
            or verdict.finalization_request_id != finalization_request_id
            or verdict.candidate_checkpoint_ref != checkpoint.checkpoint_id
            or verdict.validation_report_id != report.validation_report_id
            or verdict.reviewer_profile_id != target_spec.reviewer_profile_id
            or request.target_task_id != target_spec.target_task_id
        ):
            raise ValueError("review verdict identities do not match")
        findings = [
            resolve_review_finding(store, target_spec, reference.finding_id)
            for reference in verdict.finding_refs
        ]
        if any(
            finding.review_verdict_id != verdict.review_verdict_id
            or finding.target_task_id != verdict.target_task_id
            for finding in findings
        ):
            raise ValueError("review finding identities do not match")
        return verdict
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "committed review verdict failed integrity validation"
        ) from error


def resolve_review_finding(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    finding_id: str,
) -> ReviewFinding:
    """Load and verify one immutable target-review finding."""
    try:
        finding = ReviewFinding.model_validate_json(
            store.paths.review_finding(target_spec, finding_id).read_bytes()
        )
        if (
            finding.finding_id != finding_id
            or finding.target_task_id != target_spec.target_task_id
            or target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
        ):
            raise ValueError("review finding identities do not match")
        return finding
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "review finding failed integrity validation"
        ) from error


def _validate_review_authorities(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition,
    reviewer_profile: WorkerProfile,
    reviewer_instructions: ReviewerInstructions,
) -> None:
    if target_state.phase is not TargetPhase.REVIEWING:
        raise TargetReviewInvocationError("target review requires REVIEWING phase")
    if (
        target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
        or target_state.fleet_run_id != store.fleet_spec.fleet_run_id
        or target_state.target_task_id != target_spec.target_task_id
        or target_spec.source != store.fleet_spec.source
        or catalog.catalog_id != store.fleet_spec.target_catalog_id
        or catalog.catalog_version != store.fleet_spec.target_catalog_version
        or target_spec.target_id not in store.fleet_spec.target_ids
        or sum(
            entry.target_id == target_spec.target_id
            and entry.target_contract_version == target_spec.target_contract_version
            for entry in catalog.targets
        )
        != 1
        or target_definition.target_id != target_spec.target_id
        or target_definition.target_contract_version
        != target_spec.target_contract_version
        or reviewer_profile.profile_id != target_spec.reviewer_profile_id
        or reviewer_instructions.reviewer_profile_id != reviewer_profile.profile_id
        or reviewer_instructions.target_id != target_spec.target_id
        or reviewer_instructions.target_contract_version
        != target_spec.target_contract_version
    ):
        raise TargetReviewInvocationError(
            "target review authorities do not identify the same contract"
        )


def _load_checkpoint_artifacts(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    checkpoint: object,
) -> list[ReviewArtifact]:
    from bridger.contracts.memory.persistence import TaskCheckpoint

    if not isinstance(checkpoint, TaskCheckpoint):
        raise ValueError("review checkpoint is malformed")
    root = (
        store.paths.checkpoint_root(target_spec, checkpoint.checkpoint_id) / "artifacts"
    ).resolve()
    artifacts: list[ReviewArtifact] = []
    for reference in sorted(
        checkpoint.task_state.artifact_refs,
        key=lambda item: (item.relative_path, item.artifact_id),
    ):
        path = (root / reference.relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise ValueError("review artifact is outside the submitted checkpoint")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != reference.digest:
            raise ValueError("review artifact digest does not match checkpoint")
        artifacts.append(
            ReviewArtifact(reference=reference, content=content.decode("utf-8"))
        )
    return artifacts


def _build_review_request(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    context: TargetReviewContext,
    reviewer_profile: WorkerProfile,
    manager: ContextWindowManager,
) -> tuple[LLMRequest, int, int]:
    if reviewer_profile.reserved_response_tokens < 1:
        raise TargetReviewError("reviewer profile must reserve response capacity")
    user_content = _serialize_review_material(context)
    request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_REVIEW,
        profile=reviewer_profile.profile_id,
        messages=[
            LLMMessage.system(context.shared_reviewer_instructions),
            LLMMessage.user(user_content),
        ],
        max_output_tokens=reviewer_profile.reserved_response_tokens,
        reasoning=(
            LLMReasoningConfig(
                effort=reviewer_profile.reasoning_effort,
                context=reviewer_profile.reasoning_context,
            )
            if reviewer_profile.reasoning_effort is not None
            else None
        ),
        metadata={
            "run_id": fleet_spec.fleet_run_id,
            "workflow_id": target_spec.target_task_id,
        },
    )
    serialized = orjson.dumps(
        request.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    ).decode()
    diagnostics = manager.inspect_request(
        serialized,
        reserved_response_tokens=reviewer_profile.reserved_response_tokens,
    )
    if (
        diagnostics.current_request_input_tokens
        > reviewer_profile.provider_input_hard_cap_tokens
        or not diagnostics.within_context_limit
    ):
        raise TargetReviewError("complete mandatory review request does not fit")
    _validate_usage_authorities(fleet_spec, fleet_state, target_spec, target_state)
    return (
        request,
        diagnostics.current_request_input_tokens,
        reviewer_profile.reserved_response_tokens,
    )


def _serialize_review_material(context: TargetReviewContext) -> str:
    material = context.model_dump(
        mode="json",
        exclude={"shared_reviewer_instructions"},
    )
    return (
        "Review this exact checkpointed candidate. Return only the requested "
        "structured result.\n\n"
        + orjson.dumps(material, option=orjson.OPT_SORT_KEYS).decode()
    )


def _validate_usage_authorities(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    if (
        fleet_state.fleet_run_id != fleet_spec.fleet_run_id
        or target_spec.fleet_run_id != fleet_spec.fleet_run_id
        or target_state.fleet_run_id != fleet_spec.fleet_run_id
        or target_state.target_task_id != target_spec.target_task_id
    ):
        raise TargetReviewInvocationError("review usage authorities do not align")


async def _generate_with_retries(
    client: LLMClient,
    request: LLMRequest,
    coordinator: FleetExecutionCoordinator,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    fleet_state: FleetRunState,
    logical_attempt_id: str,
    context: TargetReviewContext,
) -> LLMResponse[TargetReviewModelResult]:
    async def operation() -> LLMResponse[TargetReviewModelResult]:
        generate_once = getattr(client, "generate_once", None)
        if callable(generate_once):
            response = await generate_once(
                request,
                output_type=TargetReviewModelResult,
            )
        else:
            response = await client.generate(
                request,
                output_type=TargetReviewModelResult,
            )
        _validate_review_model_result(context, response)
        return response

    async def before_attempt(attempt: int) -> None:
        if attempt == 1:
            return
        await coordinator.charge_additional_model_attempts(
            target_state.usage,
            fleet_state.usage,
            1,
            target_state=target_state,
            target_spec=target_spec,
        )
        coordinator.record_retry_attempt_boundary(
            target_spec.target_task_id,
            logical_attempt_id,
            attempt,
            failed=False,
        )

    async def on_retry(
        next_attempt: int,
        delay_seconds: float,
        error: LLMError,
    ) -> None:
        coordinator.record_retry_attempt_boundary(
            target_spec.target_task_id,
            logical_attempt_id,
            next_attempt - 1,
            failed=True,
            usage=(error.usage if isinstance(error.usage, LLMUsage) else None),
            error=error,
        )
        failed_usage = getattr(error, "usage", None)
        if isinstance(failed_usage, LLMUsage):
            await coordinator.charge_reported_tokens(
                target_state,
                fleet_state,
                failed_usage,
            )
        coordinator.record_retry(
            target_spec.target_task_id,
            next_attempt,
            delay_seconds,
        )

    return await run_provider_with_retry(
        operation,
        before_attempt=before_attempt,
        on_retry=on_retry,
    )


async def _charge_client_retries(
    coordinator: FleetExecutionCoordinator,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    fleet_state: FleetRunState,
    attempt_count: object,
) -> None:
    if isinstance(attempt_count, int) and attempt_count > 1:
        await coordinator.charge_additional_model_attempts(
            target_state.usage,
            fleet_state.usage,
            attempt_count - 1,
            target_state=target_state,
            target_spec=target_spec,
        )


def _complete_review(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    context: TargetReviewContext,
    response: LLMResponse[TargetReviewModelResult],
) -> TargetReviewVerdict:
    result = response.structured_output
    if result is None:
        raise TargetReviewError("reviewer returned no structured result")
    try:
        with store.target_lock(target_spec.target_task_id):
            existing = resolve_review_verdict(
                store,
                target_spec,
                context.finalization_request_id,
            )
            if existing is not None:
                persisted = TargetTaskState.model_validate_json(
                    store.paths.target_state(target_spec).read_bytes()
                )
                _replace_review_state(target_state, persisted)
                return existing
            if (
                target_state.phase is not TargetPhase.REVIEWING
                or target_state.pending_finalization_request_ref
                != context.finalization_request_id
            ):
                raise ValueError("review completion lost its current candidate")

            verdict_id = _review_verdict_id(context.finalization_request_id)
            artifact_ids_by_path = {
                artifact.reference.relative_path: artifact.reference.artifact_id
                for artifact in context.candidate_artifacts
            }
            findings = _materialize_findings(
                verdict_id,
                target_spec,
                result.findings,
                artifact_ids_by_path,
            )
            finding_refs = [_finding_ref(finding) for finding in findings]
            verdict = TargetReviewVerdict(
                review_verdict_id=verdict_id,
                fleet_run_id=store.fleet_spec.fleet_run_id,
                target_task_id=target_spec.target_task_id,
                finalization_request_id=context.finalization_request_id,
                candidate_checkpoint_ref=context.candidate_checkpoint_ref,
                validation_report_id=(
                    context.hard_validation_report.validation_report_id
                ),
                reviewer_profile_id=context.reviewer_profile_id,
                provider=response.provider,
                model=response.model,
                provider_response_id=(
                    response.response_id or response.provider_request_id
                ),
                verdict=result.outcome,
                summary=result.summary,
                finding_refs=finding_refs,
                created_at=datetime.now(UTC),
            )
            preserved = [
                reference
                for reference in target_state.open_finding_refs
                if reference.origin is not FindingOrigin.TARGET_REVIEW
            ]
            next_phase = (
                TargetPhase.REPAIR
                if verdict.verdict is ReviewVerdict.NEEDS_WORK
                else TargetPhase.REVIEWING
            )
            after_state = target_state.model_copy(
                deep=True,
                update={
                    "phase": next_phase,
                    "open_finding_refs": [*preserved, *finding_refs],
                    "pending_finalization_request_ref": (
                        None
                        if verdict.verdict is ReviewVerdict.NEEDS_WORK
                        else context.finalization_request_id
                    ),
                },
            )
            writes = {
                store.paths.review_finding(target_spec, finding.finding_id): (
                    _model_bytes(finding)
                )
                for finding in findings
            }
            writes[store.paths.review_verdict(target_spec, verdict_id)] = _model_bytes(
                verdict
            )
            writes[store.paths.target_state(target_spec)] = _model_bytes(after_state)
            store.commit_operation(
                operation_id=_operation_id(
                    "review-complete",
                    context.finalization_request_id,
                ),
                writes=writes,
                event_type="review_completed",
                payload={
                    "review_verdict_id": verdict.review_verdict_id,
                    "finalization_request_id": context.finalization_request_id,
                    "candidate_checkpoint_ref": context.candidate_checkpoint_ref,
                    "verdict": verdict.verdict.value,
                    "from_phase": TargetPhase.REVIEWING.value,
                    "to_phase": next_phase.value,
                },
                target_task_id=target_spec.target_task_id,
            )
            _replace_review_state(target_state, after_state)
            return verdict
    except TargetReviewError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise TargetReviewError("could not persist target review verdict") from error


def _materialize_findings(
    verdict_id: str,
    target_spec: TargetTaskSpec,
    drafts: Sequence[ReviewFindingDraft],
    artifact_ids_by_path: dict[str, str],
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for index, draft in enumerate(drafts):
        finding_id = _finding_id(verdict_id, index, draft)
        findings.append(
            ReviewFinding(
                finding_id=finding_id,
                review_verdict_id=verdict_id,
                target_task_id=target_spec.target_task_id,
                criterion_id=draft.criterion_id,
                affected_artifact_refs=[
                    artifact_ids_by_path[path] for path in draft.affected_artifact_paths
                ],
                affected_obligation_ids=draft.affected_obligation_ids,
                message=draft.message,
                required_outcome=draft.required_outcome,
            )
        )
    return findings


def _validate_review_model_result(
    context: TargetReviewContext,
    response: LLMResponse[TargetReviewModelResult],
) -> None:
    result = response.structured_output
    if result is None:
        return
    if not result.findings:
        return
    artifact_paths = {
        artifact.reference.relative_path for artifact in context.candidate_artifacts
    }
    obligation_ids = {
        obligation.obligation_id
        for obligation in context.target_definition.completion_obligations
    }
    for finding in result.findings:
        if not set(finding.affected_artifact_paths).issubset(artifact_paths):
            _raise_malformed_review_output(
                "review finding names an unknown candidate artifact path",
                response,
            )
        if not set(finding.affected_obligation_ids).issubset(obligation_ids):
            _raise_malformed_review_output(
                "review finding names an unknown target obligation",
                response,
            )


def _raise_malformed_review_output(
    message: str,
    response: LLMResponse[TargetReviewModelResult],
) -> NoReturn:
    structured_output = response.structured_output
    if structured_output is None:
        raise AssertionError("malformed review output requires structured output")
    raise LLMStructuredOutputError(
        message,
        invalid_output=structured_output.model_dump(mode="json"),
        usage=response.usage,
        latency_ms=response.latency_ms,
        provider=response.provider,
        model=response.model,
        operation=LLMOperation.MEMORY_AGENT_REVIEW,
        retryable=True,
    )


def _replace_review_state(
    current: TargetTaskState,
    replacement: TargetTaskState,
) -> None:
    if replacement.phase is TargetPhase.REPAIR:
        current.open_finding_refs = replacement.open_finding_refs
        current.pending_finalization_request_ref = None
        current.phase = TargetPhase.REPAIR
    _replace_model(current, replacement)


def _finding_ref(finding: ReviewFinding) -> FindingRef:
    return FindingRef(
        finding_id=finding.finding_id,
        origin=FindingOrigin.TARGET_REVIEW,
    )


def _mark_target_exhausted(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    finalization_request_id: str,
) -> None:
    after_state = target_state.model_copy(
        deep=True,
        update={"phase": TargetPhase.EXHAUSTED},
    )
    store.commit_operation(
        operation_id=_operation_id("review-exhausted", finalization_request_id),
        writes={store.paths.target_state(target_spec): _model_bytes(after_state)},
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.REVIEWING.value,
            "to_phase": TargetPhase.EXHAUSTED.value,
        },
        target_task_id=target_spec.target_task_id,
    )
    _replace_model(target_state, after_state)


def _raise_review_budget_error(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    finalization_request_id: str,
    stop: _BudgetStop,
) -> NoReturn:
    if stop.scope is _BudgetScope.TARGET:
        _mark_target_exhausted(
            store,
            target_spec,
            target_state,
            finalization_request_id,
        )
    raise TargetReviewBudgetError(stop.scope.value) from stop


def _review_verdict_id(finalization_request_id: str) -> str:
    digest = hashlib.sha256(finalization_request_id.encode()).hexdigest()
    return f"review-verdict-{digest}"


def _finding_id(
    verdict_id: str,
    index: int,
    draft: ReviewFindingDraft,
) -> str:
    identity = orjson.dumps(
        {
            "verdict_id": verdict_id,
            "index": index,
            "draft": draft.model_dump(mode="json"),
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return f"review-finding-{hashlib.sha256(identity).hexdigest()}"


def _operation_id(prefix: str, finalization_request_id: str) -> str:
    digest = hashlib.sha256(finalization_request_id.encode()).hexdigest()
    return f"{prefix}-{digest}"


__all__ = [
    "compile_target_review_context",
    "resolve_review_finding",
    "resolve_review_verdict",
    "review_target",
]
