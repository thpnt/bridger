"""Deterministic Stage 10 local target-acceptance boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

import orjson
from pydantic import ValidationError

from memory.durability import FleetRuntimeStore, _model_bytes, _replace_model
from memory.errors import PersistenceRecoveryError, TargetAcceptanceError
from memory.recovery import validate_checkpoint
from memory.review import resolve_review_verdict
from memory.validation import resolve_validation_report
from models.acceptance import AcceptedTargetResult
from models.memory import (
    FindingOrigin,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from models.persistence import TargetFinalizationRequest, TaskCheckpoint
from models.review import ReviewVerdict, TargetReviewVerdict
from models.validation import TargetValidationReport, ValidationVerdict
from models.worker_cycle import EvidenceReference

_LOCAL_FINDING_ORIGINS = {
    FindingOrigin.HARD_VALIDATION,
    FindingOrigin.TARGET_REVIEW,
}


def accept_target(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> AcceptedTargetResult:
    """Freeze and commit the exact candidate that passed both local gates."""
    try:
        with store.target_lock(target_spec.target_task_id):
            current = _load_current_target_state(store, target_spec, target_state)
            if current.phase is TargetPhase.ACCEPTED:
                result = _resolve_current_accepted_result(
                    store,
                    target_spec,
                    current,
                )
                _replace_acceptance_state(target_state, current)
                return result
            if current.phase is not TargetPhase.REVIEWING:
                raise TargetAcceptanceError(
                    "target acceptance requires REVIEWING phase"
                )

            request, checkpoint, report, verdict = _resolve_successful_chain(
                store,
                target_spec,
                current,
            )
            completion_state = TargetCompletionState.model_validate_json(
                store.paths.completion_state(target_spec).read_bytes()
            )
            _validate_current_candidate(
                store,
                target_spec,
                current,
                completion_state,
                checkpoint,
            )
            result = _build_accepted_result(
                target_spec,
                checkpoint,
                request,
                report,
                verdict,
            )
            result_path = store.paths.accepted_target_result(
                target_spec,
                result.accepted_target_result_id,
            )
            if result_path.exists():
                existing = resolve_accepted_target_result(
                    store,
                    target_spec,
                    result.accepted_target_result_id,
                )
                if existing != result:
                    raise ValueError(
                        "accepted result identity resolves to different provenance"
                    )
                result = existing

            after_state = current.model_copy(
                deep=True,
                update={
                    "phase": TargetPhase.ACCEPTED,
                    "last_accepted_result_ref": result.accepted_target_result_id,
                    "pending_finalization_request_ref": None,
                },
            )
            store.commit_operation(
                operation_id=_acceptance_operation_id(result.accepted_target_result_id),
                writes={
                    result_path: _model_bytes(result),
                    store.paths.target_state(target_spec): _model_bytes(after_state),
                },
                event_type="target_accepted",
                payload={
                    "accepted_target_result_id": (result.accepted_target_result_id),
                    "finalization_request_id": request.finalization_request_id,
                    "validation_report_id": report.validation_report_id,
                    "review_verdict_id": verdict.review_verdict_id,
                    "from_phase": TargetPhase.REVIEWING.value,
                    "to_phase": TargetPhase.ACCEPTED.value,
                },
                target_task_id=target_spec.target_task_id,
            )
            _replace_acceptance_state(target_state, after_state)
            return result
    except TargetAcceptanceError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise TargetAcceptanceError(
            "could not establish or persist coherent target acceptance"
        ) from error


def resolve_accepted_target_result(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    accepted_target_result_id: str,
) -> AcceptedTargetResult:
    """Load and verify one immutable historical accepted-target result."""
    try:
        result = AcceptedTargetResult.model_validate_json(
            store.paths.accepted_target_result(
                target_spec,
                accepted_target_result_id,
            ).read_bytes()
        )
        if (
            result.accepted_target_result_id != accepted_target_result_id
            or result.target_task_id != target_spec.target_task_id
            or result.fleet_run_id != target_spec.fleet_run_id
            or result.fleet_run_id != store.fleet_spec.fleet_run_id
            or result.target_id != target_spec.target_id
            or result.target_contract_version != target_spec.target_contract_version
            or result.source != target_spec.source
            or result.source != store.fleet_spec.source
        ):
            raise ValueError("accepted result identities do not match target")

        request = _load_finalization_request(
            store,
            target_spec,
            result.finalization_request_ref,
        )
        checkpoint = validate_checkpoint(
            store,
            target_spec,
            request.candidate_checkpoint_ref,
        )
        report = resolve_validation_report(
            store,
            target_spec,
            request.finalization_request_id,
        )
        verdict = resolve_review_verdict(
            store,
            target_spec,
            request.finalization_request_id,
        )
        if report is None or verdict is None:
            raise ValueError("accepted result evaluation provenance is missing")
        _validate_successful_chain(request, checkpoint, report, verdict)
        expected = _build_accepted_result(
            target_spec,
            checkpoint,
            request,
            report,
            verdict,
        )
        if result != expected:
            raise ValueError("accepted result provenance does not match candidate")
        _validate_accepted_evidence(store, target_spec, checkpoint)
        return result
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "accepted target result failed integrity validation"
        ) from error


def _load_current_target_state(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> TargetTaskState:
    current = TargetTaskState.model_validate_json(
        store.paths.target_state(target_spec).read_bytes()
    )
    if (
        target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
        or target_spec.source != store.fleet_spec.source
        or current.fleet_run_id != target_spec.fleet_run_id
        or current.target_task_id != target_spec.target_task_id
        or target_state.fleet_run_id != target_spec.fleet_run_id
        or target_state.target_task_id != target_spec.target_task_id
    ):
        raise ValueError("acceptance authorities do not identify the same target")
    return current


def _resolve_current_accepted_result(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> AcceptedTargetResult:
    result_id = target_state.last_accepted_result_ref
    if result_id is None or target_state.pending_finalization_request_ref is not None:
        raise ValueError("accepted target state is incomplete")
    return resolve_accepted_target_result(store, target_spec, result_id)


def _replace_acceptance_state(
    current: TargetTaskState,
    replacement: TargetTaskState,
) -> None:
    current.last_accepted_result_ref = replacement.last_accepted_result_ref
    current.pending_finalization_request_ref = (
        replacement.pending_finalization_request_ref
    )
    _replace_model(current, replacement)


def _resolve_successful_chain(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> tuple[
    TargetFinalizationRequest,
    TaskCheckpoint,
    TargetValidationReport,
    TargetReviewVerdict,
]:
    request_id = target_state.pending_finalization_request_ref
    if request_id is None:
        raise ValueError("REVIEWING target has no pending finalization request")
    request = _load_finalization_request(store, target_spec, request_id)
    checkpoint = validate_checkpoint(
        store,
        target_spec,
        request.candidate_checkpoint_ref,
    )
    report = resolve_validation_report(store, target_spec, request_id)
    verdict = resolve_review_verdict(store, target_spec, request_id)
    if report is None or verdict is None:
        raise ValueError("target acceptance requires validation and review results")
    _validate_successful_chain(request, checkpoint, report, verdict)
    if any(
        reference.origin in _LOCAL_FINDING_ORIGINS
        for reference in target_state.open_finding_refs
    ):
        raise ValueError("unresolved local findings block target acceptance")
    return request, checkpoint, report, verdict


def _load_finalization_request(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    request_id: str,
) -> TargetFinalizationRequest:
    request = TargetFinalizationRequest.model_validate_json(
        store.paths.finalization_request(target_spec, request_id).read_bytes()
    )
    if (
        request.finalization_request_id != request_id
        or request.fleet_run_id != store.fleet_spec.fleet_run_id
        or request.target_task_id != target_spec.target_task_id
    ):
        raise ValueError("finalization request identities do not match target")
    return request


def _validate_successful_chain(
    request: TargetFinalizationRequest,
    checkpoint: TaskCheckpoint,
    report: TargetValidationReport,
    verdict: TargetReviewVerdict,
) -> None:
    if (
        report.verdict is not ValidationVerdict.PASS
        or report.finding_refs
        or verdict.verdict is not ReviewVerdict.PASS
        or verdict.finding_refs
        or report.fleet_run_id != request.fleet_run_id
        or report.target_task_id != request.target_task_id
        or report.finalization_request_id != request.finalization_request_id
        or report.candidate_checkpoint_ref != checkpoint.checkpoint_id
        or verdict.fleet_run_id != request.fleet_run_id
        or verdict.target_task_id != request.target_task_id
        or verdict.finalization_request_id != request.finalization_request_id
        or verdict.candidate_checkpoint_ref != checkpoint.checkpoint_id
        or verdict.validation_report_id != report.validation_report_id
    ):
        raise ValueError("acceptance evaluation chain is not one exact PASS candidate")


def _validate_current_candidate(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    checkpoint: TaskCheckpoint,
) -> None:
    checkpoint_state = checkpoint.task_state
    if (
        target_state.last_checkpoint_ref != checkpoint.checkpoint_id
        or target_state.artifact_refs != checkpoint_state.artifact_refs
        or target_state.evidence_refs != checkpoint_state.evidence_refs
        or completion_state != checkpoint.completion_state
    ):
        raise ValueError("current candidate no longer matches evaluated candidate")
    _validate_current_artifacts(target_spec, target_state)
    _validate_accepted_evidence(store, target_spec, checkpoint)


def _validate_current_artifacts(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    workspace = Path(target_spec.target_workspace).resolve()
    expected_paths: set[Path] = set()
    artifact_ids: set[str] = set()
    for reference in target_state.artifact_refs:
        path = (workspace / reference.relative_path).resolve()
        if reference.artifact_id in artifact_ids:
            raise ValueError("current candidate has duplicate artifact identities")
        artifact_ids.add(reference.artifact_id)
        if (
            not path.is_relative_to(workspace)
            or not path.is_file()
            or path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != reference.digest
        ):
            raise ValueError("current candidate artifact failed integrity validation")
        expected_paths.add(path)
    actual_paths = {path.resolve() for path in workspace.rglob("*") if path.is_file()}
    if actual_paths != expected_paths:
        raise ValueError("current candidate artifact inventory has drifted")


def _validate_accepted_evidence(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    checkpoint: TaskCheckpoint,
) -> None:
    checkpoint_evidence = {
        evidence.evidence_id: evidence for evidence in checkpoint.evidence_records
    }
    if len(checkpoint_evidence) != len(checkpoint.evidence_records):
        raise ValueError("accepted candidate has duplicate evidence identities")
    for evidence_id in checkpoint.task_state.evidence_refs:
        evidence = EvidenceReference.model_validate_json(
            store.paths.evidence(target_spec, evidence_id).read_bytes()
        )
        if (
            evidence.evidence_id != evidence_id
            or evidence.target_task_id != target_spec.target_task_id
            or evidence.source != target_spec.source
            or evidence != checkpoint_evidence.get(evidence_id)
        ):
            raise ValueError("accepted candidate evidence failed integrity validation")


def _build_accepted_result(
    target_spec: TargetTaskSpec,
    checkpoint: TaskCheckpoint,
    request: TargetFinalizationRequest,
    report: TargetValidationReport,
    verdict: TargetReviewVerdict,
) -> AcceptedTargetResult:
    result = AcceptedTargetResult(
        accepted_target_result_id="pending",
        target_task_id=target_spec.target_task_id,
        fleet_run_id=target_spec.fleet_run_id,
        target_id=target_spec.target_id,
        target_contract_version=target_spec.target_contract_version,
        source=target_spec.source,
        artifact_refs=checkpoint.task_state.artifact_refs,
        completion_items=checkpoint.completion_state.items,
        evidence_refs=checkpoint.task_state.evidence_refs,
        finalization_request_ref=request.finalization_request_id,
        validation_report_ref=report.validation_report_id,
        review_verdict_ref=verdict.review_verdict_id,
    )
    identity = orjson.dumps(
        result.model_dump(mode="json", exclude={"accepted_target_result_id"}),
        option=orjson.OPT_SORT_KEYS,
    )
    result_id = f"accepted-target-result-{hashlib.sha256(identity).hexdigest()}"
    return result.model_copy(
        update={"accepted_target_result_id": result_id},
    )


def _acceptance_operation_id(accepted_target_result_id: str) -> str:
    digest = hashlib.sha256(accepted_target_result_id.encode()).hexdigest()
    return f"target-acceptance-{digest}"


__all__ = ["accept_target", "resolve_accepted_target_result"]
