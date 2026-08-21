"""Durable Stage 6 handoff from worker execution to evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from bridger.contracts.memory.core import (
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.persistence import TargetFinalizationRequest
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.memory.errors import FinalizationRequestError, PersistenceRecoveryError
from bridger.memory.persistence.durability import (
    FleetRuntimeStore,
    _model_bytes,
    _replace_model,
)
from bridger.memory.persistence.recovery import _prepare_checkpoint, validate_checkpoint


def handle_finalization_request(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> TargetFinalizationRequest:
    """Checkpoint and durably submit the current WORKING candidate."""
    try:
        with store.target_lock(target_spec.target_task_id):
            _validate_target_authorities(store, target_spec, target_state)
            if target_state.phase is TargetPhase.FINALIZING:
                return resolve_finalization_request(
                    store,
                    target_spec,
                    target_state,
                )
            if target_state.phase is not TargetPhase.WORKING:
                raise FinalizationRequestError(
                    "finalization request requires a WORKING target"
                )
            if target_state.pending_finalization_request_ref is not None:
                raise FinalizationRequestError(
                    "WORKING target already has a pending finalization request"
                )
            if any(
                item.target_task_id == target_spec.target_task_id
                for item in store.provider_reservations()
            ):
                raise FinalizationRequestError(
                    "finalization requires all provider reservations to be settled"
                )

            checkpoint, checkpoint_state, writes = _prepare_checkpoint(
                store,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
            )
            request = TargetFinalizationRequest(
                finalization_request_id=f"finalization-{uuid4().hex}",
                fleet_run_id=store.fleet_spec.fleet_run_id,
                target_task_id=target_spec.target_task_id,
                candidate_checkpoint_ref=checkpoint.checkpoint_id,
                created_at=datetime.now(UTC),
            )
            after_state = checkpoint_state.model_copy(
                update={
                    "phase": TargetPhase.FINALIZING,
                    "pending_finalization_request_ref": (
                        request.finalization_request_id
                    ),
                }
            )
            state_path = store.paths.target_state(target_spec)
            writes.pop(state_path)
            writes[
                store.paths.finalization_request(
                    target_spec,
                    request.finalization_request_id,
                )
            ] = _model_bytes(request)
            writes[state_path] = _model_bytes(after_state)
            store.commit_operation(
                operation_id=request.finalization_request_id,
                writes=writes,
                event_type="finalization_requested",
                payload={
                    "finalization_request_id": request.finalization_request_id,
                    "candidate_checkpoint_ref": checkpoint.checkpoint_id,
                    "from_phase": TargetPhase.WORKING.value,
                    "to_phase": TargetPhase.FINALIZING.value,
                },
                target_task_id=target_spec.target_task_id,
            )
            target_state.pending_finalization_request_ref = (
                request.finalization_request_id
            )
            _replace_model(target_state, after_state)
            return request
    except FinalizationRequestError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise FinalizationRequestError(
            "could not persist target finalization request"
        ) from error


def resolve_finalization_request(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> TargetFinalizationRequest:
    """Resolve and verify the immutable request for a FINALIZING target."""
    _validate_target_authorities(store, target_spec, target_state)
    if target_state.phase is not TargetPhase.FINALIZING:
        raise FinalizationRequestError("target is not FINALIZING")
    request_id = target_state.pending_finalization_request_ref
    if request_id is None:
        raise FinalizationRequestError("FINALIZING target has no pending request")
    try:
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(target_spec, request_id).read_bytes()
        )
        if (
            request.finalization_request_id != request_id
            or request.fleet_run_id != store.fleet_spec.fleet_run_id
            or request.target_task_id != target_spec.target_task_id
            or target_state.last_checkpoint_ref != request.candidate_checkpoint_ref
        ):
            raise ValueError("finalization request identities do not match target")
        checkpoint = validate_checkpoint(
            store,
            target_spec,
            request.candidate_checkpoint_ref,
        )
        if (
            checkpoint.task_state.phase is not TargetPhase.WORKING
            or checkpoint.task_state.pending_finalization_request_ref is not None
        ):
            raise ValueError("submitted checkpoint is not a WORKING candidate")
        return request
    except FinalizationRequestError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise FinalizationRequestError(
            "pending finalization request failed integrity validation"
        ) from error


def _validate_target_authorities(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    if (
        target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
        or target_state.fleet_run_id != store.fleet_spec.fleet_run_id
        or target_state.target_task_id != target_spec.target_task_id
        or target_spec.source != store.fleet_spec.source
    ):
        raise FinalizationRequestError(
            "finalization authorities do not belong to the same target"
        )


__all__ = ["handle_finalization_request", "resolve_finalization_request"]
