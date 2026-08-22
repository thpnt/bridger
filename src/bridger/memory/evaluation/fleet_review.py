"""Fresh read-only Stage 12 reconciliation of one exact accepted fleet."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import orjson
from pydantic import ValidationError

from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import (
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.fleet_review import (
    FleetReviewArtifact,
    FleetReviewContext,
    FleetReviewFinding,
    FleetReviewFindingDraft,
    FleetReviewModelResult,
    FleetReviewVerdict,
)
from bridger.contracts.memory.fleet_validation import FleetValidationReport
from bridger.contracts.memory.hydration import WorkerProfile
from bridger.contracts.memory.persistence import TargetFinalizationRequest
from bridger.contracts.memory.review import ReviewVerdict
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMError
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMReasoningConfig,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from bridger.memory.errors import (
    FleetReviewBudgetError,
    FleetReviewError,
    FleetReviewInvocationError,
    PersistenceRecoveryError,
)
from bridger.memory.evaluation.acceptance import resolve_accepted_target_result
from bridger.memory.evaluation.fleet_validation import resolve_fleet_validation_report
from bridger.memory.persistence.durability import (
    FleetRuntimeStore,
    _model_bytes,
    _replace_model,
)
from bridger.memory.persistence.recovery import validate_checkpoint
from bridger.memory.runtime.context_window import ContextWindowManager
from bridger.memory.runtime.provider_recovery import run_provider_with_retry
from bridger.memory.runtime.worker_cycle import FleetExecutionCoordinator, _BudgetStop


def compile_fleet_review_context(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    catalog: MemoryTargetCatalog,
    target_definitions: Sequence[TargetDefinition],
    reviewer_profile: WorkerProfile,
    reviewer_instructions: str,
    reconciliation_rubric: str,
) -> FleetReviewContext:
    """Compile the complete immutable corpus authorized by Stage 11."""
    try:
        current, target_specs, target_states, results, report = (
            _resolve_review_authorities(
                store,
                fleet_state,
                catalog,
                target_definitions,
                reviewer_profile,
            )
        )
        if current.phase is not FleetPhase.REVIEWING:
            raise FleetReviewInvocationError(
                "fleet reconciliation requires REVIEWING phase"
            )
        artifacts = _load_accepted_artifacts(store, target_specs, results)
        return FleetReviewContext(
            fleet_review_id=_fleet_review_id(report.fleet_validation_report_id),
            fleet_run_id=store.fleet_spec.fleet_run_id,
            source=store.fleet_spec.source,
            target_catalog_id=catalog.catalog_id,
            target_catalog_version=catalog.catalog_version,
            fleet_validation_report_ref=report.fleet_validation_report_id,
            reviewer_profile_id=reviewer_profile.profile_id,
            fleet_reviewer_instructions=reviewer_instructions,
            fleet_reconciliation_rubric=reconciliation_rubric,
            cross_target_ownership_rules=list(catalog.cross_target_ownership_rules),
            target_definitions=list(target_definitions),
            accepted_target_results=results,
            accepted_artifacts=artifacts,
            fleet_validation_report=report,
        )
    except FleetReviewError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise FleetReviewError(
            "could not compile an exact Stage 12 fleet review context"
        ) from error


async def reconcile_fleet(
    *,
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    catalog: MemoryTargetCatalog,
    target_definitions: Sequence[TargetDefinition],
    reviewer_profile: WorkerProfile,
    reviewer_instructions: str,
    reconciliation_rubric: str,
    context_window_manager: ContextWindowManager,
    llm_client: LLMClient,
    coordinator: FleetExecutionCoordinator,
    persistence: FleetRuntimeStore,
) -> FleetReviewVerdict:
    """Run and durably commit one idempotent full-corpus fleet review."""
    if fleet_spec != persistence.fleet_spec:
        raise FleetReviewInvocationError(
            "fleet review authority does not match persistence"
        )
    if context_window_manager.profile != reviewer_profile:
        raise FleetReviewInvocationError(
            "fleet review context-window profile does not match reviewer profile"
        )
    context = compile_fleet_review_context(
        persistence,
        fleet_state,
        catalog,
        target_definitions,
        reviewer_profile,
        reviewer_instructions,
        reconciliation_rubric,
    )
    existing = resolve_fleet_review_verdict(
        persistence,
        context.fleet_validation_report_ref,
    )
    if existing is not None:
        persisted = FleetRunState.model_validate_json(
            persistence.paths.fleet_state.read_bytes()
        )
        _replace_model(fleet_state, persisted)
        return existing

    request, input_tokens, output_tokens = _build_review_request(
        fleet_spec,
        context,
        reviewer_profile,
        context_window_manager,
    )
    coordinator.bind_persistence(persistence, fleet_state)
    try:
        reservation = await coordinator.reserve_fleet_model_call(
            fleet_spec.fleet_budget,
            fleet_state,
            input_tokens=input_tokens,
            requested_output_tokens=output_tokens,
        )
    except _BudgetStop as stop:
        raise FleetReviewBudgetError(stop.scope.value) from stop

    request = request.model_copy(
        update={"max_output_tokens": reservation.output_tokens}
    )
    response: LLMResponse[FleetReviewModelResult]
    durable_retry_loop = reservation.attempt_id is not None
    try:
        await coordinator.mark_model_invoked(reservation)
        if durable_retry_loop:
            response = await _generate_with_retries(
                llm_client,
                request,
                coordinator,
                fleet_state,
                reservation.attempt_id or "",
            )
        else:
            response = await llm_client.generate(
                request,
                output_type=FleetReviewModelResult,
            )
    except Exception as error:
        failed_usage = getattr(error, "usage", None)
        await coordinator.finish_fleet_model_call(
            reservation,
            fleet_state,
            failed_usage if isinstance(failed_usage, LLMUsage) else None,
        )
        if not durable_retry_loop:
            await _charge_client_retries(
                coordinator,
                fleet_state,
                getattr(error, "attempt_count", 1),
            )
        raise

    await coordinator.finish_fleet_model_call(
        reservation,
        fleet_state,
        response.usage,
    )
    if response.retry_count and not durable_retry_loop:
        await _charge_client_retries(
            coordinator,
            fleet_state,
            response.retry_count + 1,
        )
    if response.structured_output is None:
        raise FleetReviewError("fleet reviewer returned no structured result")
    verdict = _complete_review(persistence, fleet_state, context, response)
    if verdict.verdict is ReviewVerdict.NEEDS_WORK:
        resume_fleet_review_routing(persistence, fleet_state)
    return verdict


def resolve_fleet_review_verdict(
    store: FleetRuntimeStore,
    fleet_validation_report_ref: str,
) -> FleetReviewVerdict | None:
    """Load and verify the one review bound to a Stage 11 PASS report."""
    fleet_review_id = _fleet_review_id(fleet_validation_report_ref)
    path = store.paths.fleet_review_verdict(fleet_review_id)
    if not path.exists():
        return None
    try:
        verdict = FleetReviewVerdict.model_validate_json(path.read_bytes())
        report = _resolve_report_by_ref(store, fleet_validation_report_ref)
        if (
            report.verdict is not ValidationVerdict.PASS
            or report.finding_refs
            or verdict.fleet_review_id != fleet_review_id
            or verdict.fleet_run_id != store.fleet_spec.fleet_run_id
            or verdict.fleet_validation_report_ref != report.fleet_validation_report_id
            or verdict.reviewer_profile_id
            != store.fleet_spec.default_reviewer_profile_id
        ):
            raise ValueError("fleet review verdict identities do not match")
        for reference in verdict.finding_refs:
            finding = resolve_fleet_review_finding(store, reference.finding_id)
            if finding.fleet_review_id != verdict.fleet_review_id:
                raise ValueError("fleet review finding identities do not match")
        return verdict
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "committed fleet review verdict failed integrity validation"
        ) from error


def resolve_fleet_review_finding(
    store: FleetRuntimeStore,
    finding_id: str,
) -> FleetReviewFinding:
    """Load and verify one immutable Stage 12 fleet finding."""
    try:
        finding = FleetReviewFinding.model_validate_json(
            store.paths.fleet_review_finding(finding_id).read_bytes()
        )
        task_ids = {spec.target_task_id for spec in store.load_target_specs()}
        if (
            finding.finding_id != finding_id
            or finding.fleet_run_id != store.fleet_spec.fleet_run_id
            or not set(finding.affected_target_task_ids).issubset(task_ids)
        ):
            raise ValueError("fleet review finding identities do not match")
        return finding
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "fleet review finding failed integrity validation"
        ) from error


def resume_fleet_review_routing(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> FleetReviewVerdict:
    """Complete deterministic routing for a committed NEEDS_WORK verdict."""
    with store.state_locks():
        current = FleetRunState.model_validate_json(
            store.paths.fleet_state.read_bytes()
        )
        target_specs = store.load_target_specs()
        target_states = _load_target_states(store, target_specs)
        if current.phase is FleetPhase.RUNNING:
            review_refs = [
                ref
                for ref in current.open_finding_refs
                if ref.origin is FindingOrigin.FLEET_REVIEW
            ]
            if not review_refs:
                raise PersistenceRecoveryError(
                    "running fleet lacks routed fleet-review findings"
                )
            finding = resolve_fleet_review_finding(store, review_refs[0].finding_id)
            verdict = FleetReviewVerdict.model_validate_json(
                store.paths.fleet_review_verdict(finding.fleet_review_id).read_bytes()
            )
            _replace_model(fleet_state, current)
            return verdict
        if current.phase is not FleetPhase.REPAIRING:
            raise FleetReviewInvocationError(
                "fleet review routing requires REPAIRING phase"
            )
        review_refs = [
            ref
            for ref in current.open_finding_refs
            if ref.origin is FindingOrigin.FLEET_REVIEW
        ]
        if not review_refs:
            raise PersistenceRecoveryError(
                "repairing fleet lacks committed fleet-review findings"
            )
        first = resolve_fleet_review_finding(store, review_refs[0].finding_id)
        verdict = FleetReviewVerdict.model_validate_json(
            store.paths.fleet_review_verdict(first.fleet_review_id).read_bytes()
        )
        if (
            verdict.verdict is not ReviewVerdict.NEEDS_WORK
            or verdict.finding_refs != review_refs
        ):
            raise PersistenceRecoveryError(
                "fleet review repair projection does not match its verdict"
            )
        _route_failed_review(
            store,
            fleet_state,
            current,
            target_specs,
            target_states,
            verdict,
        )
        return verdict


def _resolve_review_authorities(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    catalog: MemoryTargetCatalog,
    target_definitions: Sequence[TargetDefinition],
    reviewer_profile: WorkerProfile,
) -> tuple[
    FleetRunState,
    list[TargetTaskSpec],
    list[TargetTaskState],
    list[AcceptedTargetResult],
    FleetValidationReport,
]:
    current = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    target_specs = store.load_target_specs()
    target_states = _load_target_states(store, target_specs)
    definitions = list(target_definitions)
    if (
        fleet_state.fleet_run_id != store.fleet_spec.fleet_run_id
        or current.fleet_run_id != store.fleet_spec.fleet_run_id
        or current.target_task_ids
        != [target_spec.target_task_id for target_spec in target_specs]
        or catalog.catalog_id != store.fleet_spec.target_catalog_id
        or catalog.catalog_version != store.fleet_spec.target_catalog_version
        or reviewer_profile.profile_id != store.fleet_spec.default_reviewer_profile_id
        or [definition.target_id for definition in definitions]
        != store.fleet_spec.target_ids
        or any(
            sum(
                entry.target_id == definition.target_id
                and entry.target_contract_version == definition.target_contract_version
                for entry in catalog.targets
            )
            != 1
            for definition in definitions
        )
    ):
        raise FleetReviewInvocationError(
            "fleet review authorities do not identify the same fleet contract"
        )
    results: list[AcceptedTargetResult] = []
    for target_id, target_spec, target_state, definition in zip(
        store.fleet_spec.target_ids,
        target_specs,
        target_states,
        definitions,
        strict=True,
    ):
        if (
            target_state.phase is not TargetPhase.ACCEPTED
            or target_state.target_task_id != target_spec.target_task_id
            or target_spec.target_id != target_id
            or definition.target_id != target_id
            or definition.target_contract_version != target_spec.target_contract_version
        ):
            raise FleetReviewInvocationError(
                "fleet reconciliation requires the exact accepted target fleet"
            )
        result_id = target_state.last_accepted_result_ref
        if result_id is None:
            raise PersistenceRecoveryError(
                "accepted target has no accepted-result reference"
            )
        results.append(resolve_accepted_target_result(store, target_spec, result_id))
    accepted_refs = [result.accepted_target_result_id for result in results]
    report = resolve_fleet_validation_report(store, accepted_refs)
    if (
        report is None
        or not isinstance(report, FleetValidationReport)
        or report.verdict is not ValidationVerdict.PASS
        or report.finding_refs
    ):
        raise FleetReviewInvocationError(
            "fleet reconciliation requires the exact Stage 11 PASS report"
        )
    return current, target_specs, target_states, results, report


def _load_target_states(
    store: FleetRuntimeStore,
    target_specs: Sequence[TargetTaskSpec],
) -> list[TargetTaskState]:
    return [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target_spec).read_bytes()
        )
        for target_spec in target_specs
    ]


def _load_accepted_artifacts(
    store: FleetRuntimeStore,
    target_specs: Sequence[TargetTaskSpec],
    results: Sequence[AcceptedTargetResult],
) -> list[FleetReviewArtifact]:
    artifacts: list[FleetReviewArtifact] = []
    for target_spec, result in zip(target_specs, results, strict=True):
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(
                target_spec,
                result.finalization_request_ref,
            ).read_bytes()
        )
        checkpoint = validate_checkpoint(
            store,
            target_spec,
            request.candidate_checkpoint_ref,
        )
        if checkpoint.task_state.artifact_refs != result.artifact_refs:
            raise ValueError("accepted artifact set differs from its checkpoint")
        root = (
            store.paths.checkpoint_root(target_spec, checkpoint.checkpoint_id)
            / "artifacts"
        ).resolve()
        for reference in result.artifact_refs:
            path = (root / reference.relative_path).resolve()
            content = path.read_bytes()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or path.is_symlink()
                or hashlib.sha256(content).hexdigest() != reference.digest
            ):
                raise ValueError("accepted artifact failed integrity validation")
            artifacts.append(
                FleetReviewArtifact(
                    target_task_id=target_spec.target_task_id,
                    fleet_relative_path=(
                        f"{target_spec.target_id}/{reference.relative_path}"
                    ),
                    reference=reference,
                    content=content.decode("utf-8"),
                )
            )
    return artifacts


def _build_review_request(
    fleet_spec: MemoryFleetSpec,
    context: FleetReviewContext,
    reviewer_profile: WorkerProfile,
    manager: ContextWindowManager,
) -> tuple[LLMRequest, int, int]:
    if reviewer_profile.reserved_response_tokens < 1:
        raise FleetReviewError("reviewer profile must reserve response capacity")
    material = context.model_dump(
        mode="json",
        exclude={"fleet_reviewer_instructions"},
    )
    request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_RECONCILIATION,
        profile=reviewer_profile.profile_id,
        messages=[
            LLMMessage.system(context.fleet_reviewer_instructions),
            LLMMessage.user(
                "Reconcile this exact complete accepted fleet. Return only the "
                "requested structured result.\n\n"
                + orjson.dumps(material, option=orjson.OPT_SORT_KEYS).decode()
            ),
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
        metadata={"run_id": fleet_spec.fleet_run_id},
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
        raise FleetReviewError("complete mandatory fleet review request does not fit")
    return (
        request,
        diagnostics.current_request_input_tokens,
        reviewer_profile.reserved_response_tokens,
    )


async def _generate_with_retries(
    client: LLMClient,
    request: LLMRequest,
    coordinator: FleetExecutionCoordinator,
    fleet_state: FleetRunState,
    logical_attempt_id: str,
) -> LLMResponse[FleetReviewModelResult]:
    async def operation() -> LLMResponse[FleetReviewModelResult]:
        generate_once = getattr(client, "generate_once", None)
        if callable(generate_once):
            return await generate_once(request, output_type=FleetReviewModelResult)
        return await client.generate(request, output_type=FleetReviewModelResult)

    async def before_attempt(attempt: int) -> None:
        if attempt == 1:
            return
        await coordinator.charge_additional_fleet_model_attempts(fleet_state, 1)
        coordinator.record_retry_attempt_boundary(
            None,
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
            None,
            logical_attempt_id,
            next_attempt - 1,
            failed=True,
        )
        failed_usage = getattr(error, "usage", None)
        if isinstance(failed_usage, LLMUsage):
            await coordinator.charge_fleet_reported_tokens(
                fleet_state,
                failed_usage,
            )
        coordinator.record_retry(None, next_attempt, delay_seconds)

    return await run_provider_with_retry(
        operation,
        before_attempt=before_attempt,
        on_retry=on_retry,
    )


async def _charge_client_retries(
    coordinator: FleetExecutionCoordinator,
    fleet_state: FleetRunState,
    attempt_count: object,
) -> None:
    if isinstance(attempt_count, int) and attempt_count > 1:
        await coordinator.charge_additional_fleet_model_attempts(
            fleet_state,
            attempt_count - 1,
        )


def _complete_review(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    context: FleetReviewContext,
    response: LLMResponse[FleetReviewModelResult],
) -> FleetReviewVerdict:
    result = response.structured_output
    if result is None:
        raise FleetReviewError("fleet reviewer returned no structured result")
    try:
        with store.state_locks():
            existing = resolve_fleet_review_verdict(
                store,
                context.fleet_validation_report_ref,
            )
            if existing is not None:
                persisted = FleetRunState.model_validate_json(
                    store.paths.fleet_state.read_bytes()
                )
                _replace_model(fleet_state, persisted)
                return existing
            current = FleetRunState.model_validate_json(
                store.paths.fleet_state.read_bytes()
            )
            target_specs = store.load_target_specs()
            target_states = _load_target_states(store, target_specs)
            accepted_refs = [state.last_accepted_result_ref for state in target_states]
            if (
                current.phase is not FleetPhase.REVIEWING
                or any(
                    state.phase is not TargetPhase.ACCEPTED for state in target_states
                )
                or accepted_refs
                != context.fleet_validation_report.accepted_target_result_refs
            ):
                raise ValueError("fleet review completion lost its exact fleet")
            findings = _materialize_findings(context, result.findings)
            finding_refs = [
                FindingRef(
                    finding_id=finding.finding_id,
                    origin=FindingOrigin.FLEET_REVIEW,
                )
                for finding in findings
            ]
            verdict = FleetReviewVerdict(
                fleet_review_id=context.fleet_review_id,
                fleet_run_id=context.fleet_run_id,
                fleet_validation_report_ref=context.fleet_validation_report_ref,
                verdict=result.outcome,
                finding_refs=finding_refs,
                reviewer_profile_id=context.reviewer_profile_id,
            )
            next_phase = (
                FleetPhase.REPAIRING
                if verdict.verdict is ReviewVerdict.NEEDS_WORK
                else FleetPhase.REVIEWING
            )
            preserved = _without_fleet_review(current.open_finding_refs)
            after_fleet = current.model_copy(
                deep=True,
                update={
                    "phase": next_phase,
                    "open_finding_refs": [*preserved, *finding_refs],
                },
            )
            writes = {
                store.paths.fleet_review_verdict(verdict.fleet_review_id): (
                    _model_bytes(verdict)
                ),
                store.paths.fleet_state: _model_bytes(after_fleet),
            }
            for finding in findings:
                writes[store.paths.fleet_review_finding(finding.finding_id)] = (
                    _model_bytes(finding)
                )
            if verdict.verdict is ReviewVerdict.PASS:
                for target_spec, target_state in zip(
                    target_specs,
                    target_states,
                    strict=True,
                ):
                    after_target = target_state.model_copy(
                        deep=True,
                        update={
                            "open_finding_refs": _without_fleet_review(
                                target_state.open_finding_refs
                            )
                        },
                    )
                    writes[store.paths.target_state(target_spec)] = _model_bytes(
                        after_target
                    )
            store.commit_operation(
                operation_id=_operation_id(
                    "fleet-review-complete",
                    verdict.fleet_review_id,
                ),
                writes=writes,
                event_type="fleet_review_completed",
                payload={
                    "fleet_review_id": verdict.fleet_review_id,
                    "fleet_validation_report_ref": (
                        verdict.fleet_validation_report_ref
                    ),
                    "verdict": verdict.verdict.value,
                    "from_phase": FleetPhase.REVIEWING.value,
                    "to_phase": next_phase.value,
                },
            )
            _replace_model(fleet_state, after_fleet)
            return verdict
    except FleetReviewError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise FleetReviewError("could not persist fleet review verdict") from error


def _materialize_findings(
    context: FleetReviewContext,
    drafts: Sequence[FleetReviewFindingDraft],
) -> list[FleetReviewFinding]:
    task_ids = {result.target_task_id for result in context.accepted_target_results}
    artifact_paths = {
        artifact.fleet_relative_path for artifact in context.accepted_artifacts
    }
    findings: list[FleetReviewFinding] = []
    for index, draft in enumerate(drafts):
        if not set(draft.affected_target_task_ids).issubset(task_ids):
            raise ValueError("fleet review finding names an unknown target")
        if not set(draft.affected_artifact_paths).issubset(artifact_paths):
            raise ValueError("fleet review finding names an unknown artifact path")
        finding_id = _finding_id(context.fleet_review_id, index, draft)
        findings.append(
            FleetReviewFinding(
                finding_id=finding_id,
                fleet_review_id=context.fleet_review_id,
                fleet_run_id=context.fleet_run_id,
                criterion_id=draft.criterion_id,
                affected_target_task_ids=draft.affected_target_task_ids,
                affected_artifact_paths=draft.affected_artifact_paths,
                message=draft.message,
                required_outcome=draft.required_outcome,
            )
        )
    return findings


def _route_failed_review(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    current: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    verdict: FleetReviewVerdict,
) -> None:
    findings = [
        resolve_fleet_review_finding(store, reference.finding_id)
        for reference in verdict.finding_refs
    ]
    refs_by_target: dict[str, list[FindingRef]] = {}
    for reference, finding in zip(verdict.finding_refs, findings, strict=True):
        for task_id in finding.affected_target_task_ids:
            refs_by_target.setdefault(task_id, []).append(reference)
    if not refs_by_target:
        raise PersistenceRecoveryError("fleet review findings cannot be routed")
    writes = {}
    for target_spec, target_state in zip(
        target_specs,
        target_states,
        strict=True,
    ):
        if target_state.phase is not TargetPhase.ACCEPTED:
            raise PersistenceRecoveryError(
                "fleet review repair routing requires accepted targets"
            )
        routed = refs_by_target.get(target_spec.target_task_id, [])
        after_target = target_state.model_copy(
            deep=True,
            update={
                "phase": TargetPhase.REPAIR if routed else TargetPhase.ACCEPTED,
                "open_finding_refs": [
                    *_without_fleet_review(target_state.open_finding_refs),
                    *routed,
                ],
            },
        )
        writes[store.paths.target_state(target_spec)] = _model_bytes(after_target)
    after_fleet = current.model_copy(update={"phase": FleetPhase.RUNNING})
    writes[store.paths.fleet_state] = _model_bytes(after_fleet)
    store.commit_operation(
        operation_id=_operation_id("fleet-review-route", verdict.fleet_review_id),
        writes=writes,
        event_type="fleet_review_repair_routed",
        payload={
            "fleet_review_id": verdict.fleet_review_id,
            "affected_target_task_ids": [
                spec.target_task_id
                for spec in target_specs
                if spec.target_task_id in refs_by_target
            ],
            "from_phase": FleetPhase.REPAIRING.value,
            "to_phase": FleetPhase.RUNNING.value,
        },
    )
    _replace_model(fleet_state, after_fleet)


def _resolve_report_by_ref(
    store: FleetRuntimeStore,
    report_id: str,
) -> FleetValidationReport:
    report = FleetValidationReport.model_validate_json(
        store.paths.fleet_validation_report(report_id).read_bytes()
    )
    resolved = resolve_fleet_validation_report(
        store,
        report.accepted_target_result_refs,
    )
    if resolved is None or resolved.fleet_validation_report_id != report_id:
        raise ValueError("fleet review references an unknown validation report")
    return resolved


def _without_fleet_review(references: Sequence[FindingRef]) -> list[FindingRef]:
    return [
        reference
        for reference in references
        if reference.origin is not FindingOrigin.FLEET_REVIEW
    ]


def _fleet_review_id(fleet_validation_report_ref: str) -> str:
    digest = hashlib.sha256(fleet_validation_report_ref.encode()).hexdigest()
    return f"fleet-review-{digest}"


def _finding_id(
    fleet_review_id: str,
    index: int,
    draft: FleetReviewFindingDraft,
) -> str:
    identity = orjson.dumps(
        {
            "fleet_review_id": fleet_review_id,
            "index": index,
            "draft": draft.model_dump(mode="json"),
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return f"fleet-review-finding-{hashlib.sha256(identity).hexdigest()}"


def _operation_id(prefix: str, fleet_review_id: str) -> str:
    digest = hashlib.sha256(fleet_review_id.encode()).hexdigest()
    return f"{prefix}-{digest}"


__all__ = [
    "compile_fleet_review_context",
    "reconcile_fleet",
    "resolve_fleet_review_finding",
    "resolve_fleet_review_verdict",
    "resume_fleet_review_routing",
]
