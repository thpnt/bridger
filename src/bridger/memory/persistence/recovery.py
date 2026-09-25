"""Checkpoint, validation, and restart behavior for memory Stage 5."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self, TypeVar
from uuid import uuid4

import orjson
from pydantic import BaseModel, ValidationError

from bridger.contracts.memory.core import (
    ExecutionUsage,
    FindingOrigin,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    SourceBinding,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
    budgeted_input_tokens,
)
from bridger.contracts.memory.persistence import RuntimeErrorRecord, TaskCheckpoint
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.memory.errors import PersistenceRecoveryError
from bridger.memory.persistence.durability import (
    EventObserver,
    FleetRunLock,
    FleetRuntimeStore,
    _atomic_write_bytes,
    _model_bytes,
    _replace_model,
    _timestamp,
)
from bridger.memory.persistence.store import require_path_segment
from bridger.memory.targets import _resolve_catalog_definitions
from bridger.runtime_timing import current_collector

_ACTIVE_PHASES = {
    TargetPhase.SCHEDULED,
    TargetPhase.HYDRATING,
    TargetPhase.WORKING,
    TargetPhase.FINALIZING,
    TargetPhase.VALIDATING,
    TargetPhase.REVIEWING,
}
RecordT = TypeVar("RecordT", bound=BaseModel)


@dataclass
class RecoveredFleet(AbstractContextManager["RecoveredFleet"]):
    """Loaded authorities and direct-resume work from one fleet restart."""

    store: FleetRuntimeStore
    fleet_spec: MemoryFleetSpec
    fleet_state: FleetRunState
    target_specs: dict[str, TargetTaskSpec]
    target_states: dict[str, TargetTaskState]
    completion_states: dict[str, TargetCompletionState]
    evidence: dict[str, dict[str, EvidenceReference]]
    questions: dict[str, dict[str, OpenQuestion]]
    active_target_task_ids: tuple[str, ...]
    unresolved_provider_attempt_ids: tuple[str, ...]
    _run_lock: FleetRunLock

    def close(self) -> None:
        """Release process ownership after the recovered runtime stops."""
        self._run_lock.__exit__(None, None, None)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def create_checkpoint(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> TaskCheckpoint:
    """Publish one immutable exact target snapshot and select it atomically."""
    metrics = current_collector()
    with (
        metrics.span("checkpoint", target_task_id=target_spec.target_task_id)
        if metrics is not None
        else nullcontext()
    ):
        return _create_checkpoint(
            store, target_spec, target_state, completion_state, evidence, questions
        )


def _create_checkpoint(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> TaskCheckpoint:
    try:
        with store.target_lock(target_spec.target_task_id):
            checkpoint, after_state, writes = _prepare_checkpoint(
                store,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
            )
            store.commit_operation(
                operation_id=checkpoint.checkpoint_id,
                writes=writes,
                event_type="checkpoint_created",
                payload={"checkpoint_id": checkpoint.checkpoint_id},
                target_task_id=target_spec.target_task_id,
            )
            _replace_model(target_state, after_state)
            return checkpoint
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError("could not create target checkpoint") from error


def _prepare_checkpoint(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> tuple[TaskCheckpoint, TargetTaskState, dict[Path, bytes]]:
    """Build one checkpoint and its write set without publishing it."""
    checkpoint_id = f"checkpoint-{uuid4().hex}"
    checkpoint_sequence = _next_checkpoint_sequence(store, target_spec)
    after_state = target_state.model_copy(
        deep=True,
        update={"last_checkpoint_ref": checkpoint_id},
    )
    selected_evidence = [
        _require_evidence(evidence, evidence_id, target_spec)
        for evidence_id in after_state.evidence_refs
    ]
    selected_questions = [
        _require_question(questions, question_id, target_spec)
        for question_id in after_state.open_question_refs
    ]
    artifact_snapshots = _current_artifact_snapshots(target_spec, after_state)
    checkpoint = TaskCheckpoint(
        checkpoint_id=checkpoint_id,
        checkpoint_sequence=checkpoint_sequence,
        fleet_run_id=store.fleet_spec.fleet_run_id,
        target_task_id=target_spec.target_task_id,
        source=target_spec.source,
        target_task_spec_digest=_model_digest(target_spec),
        trace_sequence=store.trace_high_water(),
        created_at=_timestamp(),
        task_state=after_state,
        completion_state=completion_state.model_copy(deep=True),
        evidence_records=selected_evidence,
        open_questions=selected_questions,
        checkpoint_digest="0" * 64,
    )
    checkpoint = checkpoint.model_copy(
        update={"checkpoint_digest": _checkpoint_digest(checkpoint, artifact_snapshots)}
    )
    checkpoint_root = store.paths.checkpoint_root(target_spec, checkpoint_id)
    writes = {checkpoint_root / "checkpoint.json": _model_bytes(checkpoint)}
    for relative_path, content in artifact_snapshots.items():
        writes[checkpoint_root / "artifacts" / relative_path] = content
    writes[store.paths.target_state(target_spec)] = _model_bytes(after_state)
    return checkpoint, after_state, writes


def initialize_persistence(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    completion_states: Sequence[TargetCompletionState],
    *,
    event_observer: EventObserver | None = None,
) -> FleetRuntimeStore:
    """Attach Stage 5 trace and baseline checkpoints to Stage 1 products."""
    if not (len(target_specs) == len(target_states) == len(completion_states)):
        raise PersistenceRecoveryError("initial persistence bundle is misaligned")
    store = FleetRuntimeStore(fleet_spec, event_observer=event_observer)
    store.acquire_ownership()
    try:
        existing_events = store.recover_event_tail()
        existing_fleet_events = {event.event_type for event in existing_events}
        if "fleet_bound" not in existing_fleet_events:
            store.append_event("fleet_bound", {})
        if "fleet_initialized" not in existing_fleet_events:
            store.append_event("fleet_initialized", {})
        for target_spec, target_state, completion_state in zip(
            target_specs,
            target_states,
            completion_states,
            strict=True,
        ):
            if not any(
                event.event_type == "target_initialized"
                and event.target_task_id == target_spec.target_task_id
                for event in existing_events
            ):
                store.append_event(
                    "target_initialized",
                    {"target_id": target_spec.target_id},
                    target_task_id=target_spec.target_task_id,
                )
            if target_state.last_checkpoint_ref is None:
                if target_state.phase is not TargetPhase.INITIALIZED:
                    raise PersistenceRecoveryError(
                        "baseline checkpoint requires initialized target state"
                    )
                create_checkpoint(
                    store,
                    target_spec,
                    target_state,
                    completion_state,
                    {},
                    {},
                )
            else:
                validate_checkpoint(
                    store,
                    target_spec,
                    target_state.last_checkpoint_ref,
                )
        persisted_fleet = FleetRunState.model_validate_json(
            store.paths.fleet_state.read_bytes()
        )
        if persisted_fleet != fleet_state:
            raise PersistenceRecoveryError(
                "fleet state changed during baseline checkpointing"
            )
        return store
    except BaseException:
        store.close()
        raise


def validate_checkpoint(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    checkpoint_id: str,
) -> TaskCheckpoint:
    """Load and verify checkpoint identities, digest, and exact artifact bytes."""
    try:
        root = store.paths.checkpoint_root(target_spec, checkpoint_id)
        checkpoint = TaskCheckpoint.model_validate_json(
            (root / "checkpoint.json").read_bytes()
        )
        if (
            checkpoint.checkpoint_id != checkpoint_id
            or checkpoint.fleet_run_id != store.fleet_spec.fleet_run_id
            or checkpoint.target_task_id != target_spec.target_task_id
            or checkpoint.source != target_spec.source
            or checkpoint.target_task_spec_digest != _model_digest(target_spec)
            or checkpoint.task_state.last_checkpoint_ref != checkpoint_id
            or checkpoint.task_state.fleet_run_id != target_spec.fleet_run_id
            or checkpoint.task_state.target_task_id != target_spec.target_task_id
            or checkpoint.completion_state.target_task_id != target_spec.target_task_id
            or checkpoint.trace_sequence > store.trace_high_water()
        ):
            raise ValueError("checkpoint identities do not match current task")
        if [item.evidence_id for item in checkpoint.evidence_records] != list(
            checkpoint.task_state.evidence_refs
        ):
            raise ValueError("checkpoint evidence inventory is inconsistent")
        if any(
            item.target_task_id != target_spec.target_task_id
            or item.source != target_spec.source
            for item in checkpoint.evidence_records
        ):
            raise ValueError("checkpoint evidence identity is inconsistent")
        if [item.question_id for item in checkpoint.open_questions] != list(
            checkpoint.task_state.open_question_refs
        ) or any(
            item.target_task_id != target_spec.target_task_id
            for item in checkpoint.open_questions
        ):
            raise ValueError("checkpoint question inventory is inconsistent")
        snapshots: dict[str, bytes] = {}
        resolved_artifacts_root = (root / "artifacts").resolve()
        for reference in checkpoint.task_state.artifact_refs:
            snapshot_path = (
                resolved_artifacts_root / reference.relative_path
            ).resolve()
            if not snapshot_path.is_relative_to(resolved_artifacts_root):
                raise ValueError("checkpoint artifact path escapes snapshot root")
            content = snapshot_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != reference.digest:
                raise ValueError("checkpoint artifact digest mismatch")
            snapshots[reference.relative_path] = content
        expected_files = {
            (root / "artifacts" / reference.relative_path).resolve()
            for reference in checkpoint.task_state.artifact_refs
        }
        artifacts_root = root / "artifacts"
        if artifacts_root.exists():
            actual_files = {
                path.resolve() for path in artifacts_root.rglob("*") if path.is_file()
            }
            if actual_files != expected_files:
                raise ValueError("checkpoint artifact inventory is inconsistent")
        if _checkpoint_digest(checkpoint, snapshots) != checkpoint.checkpoint_digest:
            raise ValueError("checkpoint digest mismatch")
        return checkpoint
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "checkpoint integrity validation failed"
        ) from error


def record_runtime_error(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState | None,
    *,
    category: str,
    operation: str,
    message: str,
    retryable: bool,
    target_spec: TargetTaskSpec | None = None,
    target_state: TargetTaskState | None = None,
    phase: str | None = None,
    operation_id: str | None = None,
    cause_ref: str | None = None,
    debug_ref: str | None = None,
) -> RuntimeErrorRecord:
    """Persist an immutable error record and its current authority reference."""
    error_id = f"error-{uuid4().hex}"
    record = RuntimeErrorRecord(
        error_id=error_id,
        fleet_run_id=store.fleet_spec.fleet_run_id,
        target_task_id=target_spec.target_task_id if target_spec else None,
        phase=phase,
        category=category,
        operation=operation,
        message=message,
        retryable=retryable,
        operation_id=operation_id,
        cause_ref=cause_ref,
        debug_ref=debug_ref,
        timestamp=_timestamp(),
    )
    writes = {store.paths.errors / f"{error_id}.json": _model_bytes(record)}
    target_task_id: str | None = None
    if target_spec is not None:
        if target_state is None:
            raise ValueError("target error requires target state")
        after_target = target_state.model_copy(
            deep=True, update={"last_error_ref": error_id}
        )
        writes[store.paths.target_state(target_spec)] = _model_bytes(after_target)
        target_task_id = target_spec.target_task_id
    else:
        if fleet_state is None:
            raise ValueError("fleet error requires fleet state")
        after_fleet = fleet_state.model_copy(
            deep=True, update={"last_error_ref": error_id}
        )
        writes[store.paths.fleet_state] = _model_bytes(after_fleet)
    with store.state_locks(target_task_id):
        store.commit_operation(
            operation_id=f"runtime-error-{uuid4().hex}",
            writes=writes,
            event_type="runtime_error_recorded",
            payload={"error_id": error_id, "category": category},
            target_task_id=target_task_id,
        )
        if target_spec is not None and target_state is not None:
            _replace_model(target_state, after_target)
        else:
            assert fleet_state is not None
            _replace_model(fleet_state, after_fleet)
    return record


def recover_target(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
    *,
    error_category: str = "runtime",
    error_operation: str = "target-recovery",
    error_message: str = "active worker trajectory was interrupted",
    error_retryable: bool = True,
) -> bool:
    """Reset an interrupted admitted target for direct Stage 3 re-entry."""
    if target_state.phase is TargetPhase.SCHEDULED:
        return True
    if target_state.phase is TargetPhase.HYDRATING:
        before = target_state.phase
        after = target_state.model_copy(update={"phase": TargetPhase.SCHEDULED})
        store.persist_target_state(
            target_spec,
            after,
            event_type="recovery_reset",
            payload={
                "from_phase": before.value,
                "to_phase": TargetPhase.SCHEDULED.value,
            },
        )
        _replace_model(target_state, after)
        return True
    if target_state.phase is TargetPhase.WORKING:
        error = record_runtime_error(
            store,
            None,
            category=error_category,
            operation=error_operation,
            message=error_message,
            retryable=error_retryable,
            target_spec=target_spec,
            target_state=target_state,
            phase=TargetPhase.WORKING.value,
        )
        store.append_event(
            "execution_interrupted",
            {
                "reason": error.category,
                "operation": error.operation,
                "retryable": error.retryable,
                "error_id": error.error_id,
            },
            target_task_id=target_spec.target_task_id,
        )
        create_checkpoint(
            store,
            target_spec,
            target_state,
            completion_state,
            evidence,
            questions,
        )
        after = target_state.model_copy(update={"phase": TargetPhase.SCHEDULED})
        store.persist_target_state(
            target_spec,
            after,
            event_type="recovery_reset",
            payload={
                "from_phase": TargetPhase.WORKING.value,
                "to_phase": TargetPhase.SCHEDULED.value,
            },
        )
        _replace_model(target_state, after)
        return True
    return False


def normalize_target_for_fleet_budget_stop(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> bool:
    """Safely return an admitted target to SCHEDULED for fleet exhaustion."""
    if target_state.phase is TargetPhase.SCHEDULED:
        return True
    before: TargetPhase
    if target_state.phase is TargetPhase.HYDRATING:
        before = target_state.phase
    elif target_state.phase is TargetPhase.WORKING:
        create_checkpoint(
            store,
            target_spec,
            target_state,
            completion_state,
            evidence,
            questions,
        )
        before = TargetPhase.WORKING
    else:
        return False
    after = target_state.model_copy(update={"phase": TargetPhase.SCHEDULED})
    store.persist_target_state(
        target_spec,
        after,
        event_type="recovery_reset",
        payload={
            "from_phase": before.value,
            "to_phase": TargetPhase.SCHEDULED.value,
            "reason": "fleet budget exhaustion",
        },
    )
    _replace_model(target_state, after)
    return True


def recover_fleet(
    runtime_root: Path,
    fleet_run_id: str,
    *,
    source: SourceBinding,
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    runtime_profile_id: str,
    worker_profile_ids: set[str],
    reviewer_profile_ids: set[str],
    permission_profile_ids: set[str],
) -> RecoveredFleet:
    """Acquire, reconcile, validate, and reconstruct one persisted fleet run."""
    run_root = Path(runtime_root).resolve() / fleet_run_id
    run_lock = FleetRunLock(run_root)
    try:
        run_lock.acquire()
        fleet_spec = MemoryFleetSpec.model_validate_json(
            (run_root / "fleet-spec.json").read_bytes()
        )
        if (
            Path(fleet_spec.runtime_root).resolve() != Path(runtime_root).resolve()
            or fleet_spec.fleet_run_id != fleet_run_id
        ):
            raise ValueError("fleet spec path identity mismatch")
        if fleet_spec.source != source:
            raise ValueError("available upstream source binding does not match")
        if fleet_spec.runtime_profile_id != runtime_profile_id:
            raise ValueError("runtime profile identity does not match")
        _, definitions_by_target = _resolve_catalog_definitions(
            catalog,
            definitions,
            require_exact=False,
            required_target_ids=set(fleet_spec.target_ids),
        )
        if (
            catalog.catalog_id != fleet_spec.target_catalog_id
            or catalog.catalog_version != fleet_spec.target_catalog_version
        ):
            raise ValueError("target catalog identity does not match")

        store = FleetRuntimeStore(fleet_spec)
        store.recover_transactions()
        store.discard_temporary_files()
        store.recover_event_tail()
        fleet_state = FleetRunState.model_validate_json(
            store.paths.fleet_state.read_bytes()
        )
        target_specs = {spec.target_task_id: spec for spec in store.load_target_specs()}
        _validate_task_spec_bundle(
            fleet_spec,
            target_specs,
            definitions_by_target,
        )
        target_states: dict[str, TargetTaskState] = {}
        completion_states: dict[str, TargetCompletionState] = {}
        evidence_by_target: dict[str, dict[str, EvidenceReference]] = {}
        questions_by_target: dict[str, dict[str, OpenQuestion]] = {}
        for target_spec in target_specs.values():
            _validate_target_spec(
                fleet_spec,
                target_spec,
                definitions_by_target[target_spec.target_id],
                worker_profile_ids,
                reviewer_profile_ids,
                permission_profile_ids,
            )
            target_state = TargetTaskState.model_validate_json(
                store.paths.target_state(target_spec).read_bytes()
            )
            completion_state = TargetCompletionState.model_validate_json(
                store.paths.completion_state(target_spec).read_bytes()
            )
            _validate_target_state(target_spec, target_state, completion_state)
            evidence = _load_records(
                store.paths.target_root(target_spec) / "evidence",
                EvidenceReference,
            )
            questions = _load_records(
                store.paths.target_root(target_spec) / "questions",
                OpenQuestion,
            )
            evidence_by_target[target_spec.target_task_id] = evidence
            questions_by_target[target_spec.target_task_id] = questions
            _validate_data_refs(target_spec, target_state, evidence, questions)
            _validate_checkpoints_and_artifacts(
                store,
                target_spec,
                target_state,
                completion_state,
            )
            _validate_accepted_result_ref(store, target_spec, target_state)
            _validate_completion_definition(
                completion_state,
                definitions_by_target[target_spec.target_id],
            )
            target_states[target_spec.target_task_id] = target_state
            completion_states[target_spec.target_task_id] = completion_state

        _validate_fleet_state(fleet_spec, fleet_state, target_specs, target_states)
        stage12_review = None
        if fleet_state.phase in {FleetPhase.REPAIRING, FleetPhase.REVIEWING}:
            from bridger.contracts.memory.review import ReviewVerdict
            from bridger.contracts.memory.validation import ValidationVerdict
            from bridger.memory.evaluation.fleet_review import (
                resolve_fleet_review_verdict,
            )
            from bridger.memory.evaluation.fleet_validation import (
                resolve_fleet_validation_report,
            )

            accepted_refs = [
                target_states[task_id].last_accepted_result_ref
                for task_id in fleet_state.target_task_ids
            ]
            if fleet_state.phase is FleetPhase.REVIEWING:
                if any(reference is None for reference in accepted_refs):
                    raise ValueError("REVIEWING fleet has an incomplete accepted set")
                fleet_report = resolve_fleet_validation_report(
                    store,
                    [reference for reference in accepted_refs if reference is not None],
                )
                if (
                    fleet_report is None
                    or fleet_report.verdict is not ValidationVerdict.PASS
                    or fleet_report.finding_refs
                ):
                    raise ValueError("REVIEWING fleet lacks its Stage 11 PASS")
                stage12_review = resolve_fleet_review_verdict(
                    store,
                    fleet_report.fleet_validation_report_id,
                )
            elif all(reference is not None for reference in accepted_refs):
                fleet_report = resolve_fleet_validation_report(
                    store,
                    [reference for reference in accepted_refs if reference is not None],
                )
                if (
                    fleet_report is not None
                    and fleet_report.verdict is ValidationVerdict.PASS
                ):
                    stage12_review = resolve_fleet_review_verdict(
                        store,
                        fleet_report.fleet_validation_report_id,
                    )
            if (
                stage12_review is not None
                and fleet_state.phase is FleetPhase.REPAIRING
                and stage12_review.verdict is not ReviewVerdict.NEEDS_WORK
            ):
                raise ValueError("REPAIRING fleet has an incoherent Stage 12 result")
        if stage12_review is None:
            for target_task_id, target_spec in target_specs.items():
                _validate_evaluation_finding_refs(
                    store,
                    target_spec,
                    target_states[target_task_id],
                )
            _validate_fleet_finding_refs(store, fleet_state)
        else:
            for target_task_id, target_spec in target_specs.items():
                _validate_evaluation_finding_refs(
                    store,
                    target_spec,
                    target_states[target_task_id],
                    skip_fleet_review=True,
                )
            _validate_fleet_finding_refs(
                store,
                fleet_state,
                skip_fleet_review=True,
            )

        if fleet_state.phase in {
            FleetPhase.VALIDATING,
            FleetPhase.REPAIRING,
            FleetPhase.REVIEWING,
        }:
            from bridger.memory.evaluation.fleet_validation import validate_fleet

            if fleet_state.phase is FleetPhase.REVIEWING:
                from bridger.contracts.memory.review import ReviewVerdict
                from bridger.memory.evaluation.fleet_review import (
                    resume_fleet_review_pass_projection,
                    resume_fleet_review_routing,
                )

                if stage12_review is None:
                    validate_fleet(store, fleet_state)
                elif stage12_review.verdict is ReviewVerdict.PASS:
                    resume_fleet_review_pass_projection(store, fleet_state)
                else:
                    resume_fleet_review_routing(store, fleet_state)
            elif fleet_state.phase is FleetPhase.REPAIRING:
                from bridger.contracts.memory.review import ReviewVerdict
                from bridger.memory.evaluation.fleet_review import (
                    resume_fleet_review_routing,
                )

                if stage12_review is not None:
                    if stage12_review.verdict is not ReviewVerdict.NEEDS_WORK:
                        raise ValueError(
                            "REPAIRING fleet has an incoherent Stage 12 result"
                        )
                    resume_fleet_review_routing(store, fleet_state)
                else:
                    validate_fleet(store, fleet_state)
            else:
                validate_fleet(store, fleet_state)
            for target_task_id, target_spec in target_specs.items():
                target_state = TargetTaskState.model_validate_json(
                    store.paths.target_state(target_spec).read_bytes()
                )
                _validate_target_state(
                    target_spec,
                    target_state,
                    completion_states[target_task_id],
                )
                target_states[target_task_id] = target_state
            _validate_fleet_state(
                fleet_spec,
                fleet_state,
                target_specs,
                target_states,
            )
            for target_task_id, target_spec in target_specs.items():
                _validate_evaluation_finding_refs(
                    store,
                    target_spec,
                    target_states[target_task_id],
                )
            _validate_fleet_finding_refs(store, fleet_state)
        if fleet_state.phase is FleetPhase.ACCEPTED:
            from bridger.memory.evaluation.fleet_acceptance import (
                resolve_accepted_memory_fleet_result,
            )

            if fleet_state.accepted_result_ref is None:
                raise ValueError("ACCEPTED fleet has no accepted result")
            accepted_fleet = resolve_accepted_memory_fleet_result(
                store,
                fleet_state.accepted_result_ref,
            )
            if (
                any(
                    target_states[task_id].phase is not TargetPhase.ACCEPTED
                    for task_id in fleet_state.target_task_ids
                )
                or [
                    target_states[task_id].last_accepted_result_ref
                    for task_id in fleet_state.target_task_ids
                ]
                != accepted_fleet.accepted_target_result_refs
            ):
                raise ValueError("ACCEPTED fleet no longer matches its final result")
        _validate_error_references(store, fleet_state, target_states)
        unresolved = store.reconcile_provider_reservations()
        _validate_reservation_capacity(
            fleet_spec, fleet_state, target_specs, target_states, store
        )
        active_ids = tuple(
            task_id
            for task_id in fleet_state.target_task_ids
            if target_states[task_id].phase in _ACTIVE_PHASES
        )
        if len(active_ids) > fleet_spec.max_concurrent_targets:
            raise ValueError("recovered occupancy exceeds max_concurrent_targets")
        for target_task_id in active_ids:
            target_state = target_states[target_task_id]
            if target_state.phase is TargetPhase.FINALIZING:
                from bridger.memory.runtime.finalization import (
                    resolve_finalization_request,
                )

                if any(
                    reservation.target_task_id == target_task_id
                    for reservation in store.provider_reservations()
                ):
                    raise ValueError(
                        "FINALIZING target has an unsettled provider reservation"
                    )
                resolve_finalization_request(
                    store,
                    target_specs[target_task_id],
                    target_state,
                )
                continue
            if target_state.phase in {
                TargetPhase.VALIDATING,
                TargetPhase.REVIEWING,
            }:
                from bridger.contracts.memory.validation import ValidationVerdict
                from bridger.memory.evaluation.validation import (
                    resolve_validation_report,
                    resolve_validation_subject,
                )

                if any(
                    reservation.target_task_id == target_task_id
                    for reservation in store.provider_reservations()
                ):
                    raise ValueError(
                        "evaluation target has an unsettled provider reservation"
                    )
                request, _ = resolve_validation_subject(
                    store,
                    target_specs[target_task_id],
                    target_state,
                )
                report = resolve_validation_report(
                    store,
                    target_specs[target_task_id],
                    request.finalization_request_id,
                )
                if target_state.phase is TargetPhase.VALIDATING:
                    if report is not None:
                        raise ValueError(
                            "VALIDATING target already has a committed report"
                        )
                elif (
                    report is None
                    or report.verdict is not ValidationVerdict.PASS
                    or any(
                        reference.origin is FindingOrigin.HARD_VALIDATION
                        for reference in target_state.open_finding_refs
                    )
                ):
                    raise ValueError("REVIEWING target lacks its hard-validation PASS")
                if target_state.phase is TargetPhase.REVIEWING:
                    from bridger.contracts.memory.review import ReviewVerdict
                    from bridger.memory.evaluation.review import resolve_review_verdict

                    review_verdict = resolve_review_verdict(
                        store,
                        target_specs[target_task_id],
                        request.finalization_request_id,
                    )
                    if review_verdict is not None and (
                        review_verdict.verdict is not ReviewVerdict.PASS
                        or any(
                            reference.origin is FindingOrigin.TARGET_REVIEW
                            for reference in target_state.open_finding_refs
                        )
                    ):
                        raise ValueError(
                            "REVIEWING target has an incoherent committed review"
                        )
                continue
            recover_target(
                store,
                target_specs[target_task_id],
                target_states[target_task_id],
                completion_states[target_task_id],
                evidence_by_target[target_task_id],
                questions_by_target[target_task_id],
            )
        return RecoveredFleet(
            store=store,
            fleet_spec=fleet_spec,
            fleet_state=fleet_state,
            target_specs=target_specs,
            target_states=target_states,
            completion_states=completion_states,
            evidence=evidence_by_target,
            questions=questions_by_target,
            active_target_task_ids=active_ids,
            unresolved_provider_attempt_ids=tuple(unresolved),
            _run_lock=run_lock,
        )
    except Exception as error:
        run_lock.__exit__(None, None, None)
        if isinstance(error, PersistenceRecoveryError):
            raise
        raise PersistenceRecoveryError("fleet recovery validation failed") from error


def _next_checkpoint_sequence(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
) -> int:
    root = store.paths.target_root(target_spec) / "checkpoints"
    if not root.exists():
        return 1
    sequences = []
    for checkpoint_root in root.iterdir():
        checkpoint_path = checkpoint_root / "checkpoint.json"
        if checkpoint_path.exists():
            checkpoint = TaskCheckpoint.model_validate_json(
                checkpoint_path.read_bytes()
            )
            sequences.append(checkpoint.checkpoint_sequence)
    return max(sequences, default=0) + 1


def _current_artifact_snapshots(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> dict[str, bytes]:
    workspace = Path(target_spec.target_workspace).resolve()
    snapshots: dict[str, bytes] = {}
    for reference in target_state.artifact_refs:
        path = (workspace / reference.relative_path).resolve()
        if (
            not path.is_relative_to(workspace)
            or not path.is_file()
            or path.is_symlink()
        ):
            raise ValueError("candidate artifact is missing or outside workspace")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != reference.digest:
            raise ValueError("candidate artifact digest mismatch")
        snapshots[reference.relative_path] = content
    return snapshots


def _checkpoint_digest(
    checkpoint: TaskCheckpoint,
    snapshots: Mapping[str, bytes],
) -> str:
    metadata = checkpoint.model_dump(mode="json", exclude={"checkpoint_digest"})
    digest = hashlib.sha256(orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS))
    for relative_path in sorted(snapshots):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(snapshots[relative_path])
    return digest.hexdigest()


def _model_digest(model: BaseModel) -> str:
    serialized = orjson.dumps(
        model.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    )
    return hashlib.sha256(serialized).hexdigest()


def _require_evidence(
    evidence: Mapping[str, EvidenceReference],
    evidence_id: str,
    target_spec: TargetTaskSpec,
) -> EvidenceReference:
    reference = evidence.get(evidence_id)
    if (
        reference is None
        or reference.target_task_id != target_spec.target_task_id
        or reference.source != target_spec.source
    ):
        raise ValueError("checkpoint evidence reference is invalid")
    return reference


def _require_question(
    questions: Mapping[str, OpenQuestion],
    question_id: str,
    target_spec: TargetTaskSpec,
) -> OpenQuestion:
    question = questions.get(question_id)
    if question is None or question.target_task_id != target_spec.target_task_id:
        raise ValueError("checkpoint open-question reference is invalid")
    return question


def _load_records(
    record_root: Path,
    model_type: type[RecordT],
) -> dict[str, RecordT]:
    if not record_root.exists():
        return {}
    records: dict[str, RecordT] = {}
    for path in sorted(record_root.glob("*.json")):
        record = model_type.model_validate_json(path.read_bytes())
        record_id = getattr(record, "evidence_id", None) or getattr(
            record, "question_id", None
        )
        if not isinstance(record_id, str) or record_id in records:
            raise ValueError("immutable target record identity is invalid")
        records[record_id] = record
    return records


def _validate_target_spec(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    definition: TargetDefinition,
    worker_profile_ids: set[str],
    reviewer_profile_ids: set[str],
    permission_profile_ids: set[str],
) -> None:
    if (
        target_spec.fleet_run_id != fleet_spec.fleet_run_id
        or target_spec.source != fleet_spec.source
        or target_spec.target_contract_version != definition.target_contract_version
        or target_spec.target_id != definition.target_id
        or target_spec.worker_profile_id not in worker_profile_ids
        or target_spec.reviewer_profile_id not in reviewer_profile_ids
        or target_spec.permission_profile_id not in permission_profile_ids
        or target_spec.worker_profile_id != fleet_spec.default_worker_profile_id
        or target_spec.reviewer_profile_id != fleet_spec.default_reviewer_profile_id
        or target_spec.permission_profile_id != fleet_spec.default_permission_profile_id
        or target_spec.budget != fleet_spec.default_target_budget
    ):
        raise ValueError("target task identity/profile validation failed")
    workspace = Path(target_spec.target_workspace).resolve()
    output_root = Path(fleet_spec.output_root).resolve()
    if workspace != (output_root / target_spec.target_id).resolve():
        raise ValueError("target workspace escapes output root")


def _validate_task_spec_bundle(
    fleet_spec: MemoryFleetSpec,
    target_specs: Mapping[str, TargetTaskSpec],
    definitions: Mapping[str, TargetDefinition],
) -> None:
    by_target_id = {spec.target_id: spec for spec in target_specs.values()}
    if list(by_target_id) != fleet_spec.target_ids or len(by_target_id) != len(
        target_specs
    ):
        raise ValueError("target task spec inventory does not match fleet spec")
    for target_id in fleet_spec.target_ids:
        spec = by_target_id[target_id]
        expected_task_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"bridger-memory-target:{fleet_spec.fleet_run_id}:{target_id}",
        ).hex
        expected_dependencies = [
            by_target_id[dependency].target_task_id
            for dependency in definitions[target_id].depends_on
        ]
        if (
            spec.target_task_id != expected_task_id
            or spec.depends_on_target_task_ids != expected_dependencies
        ):
            raise ValueError("target task immutable assignment is inconsistent")


def _validate_target_state(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
) -> None:
    if (
        target_state.fleet_run_id != target_spec.fleet_run_id
        or target_state.target_task_id != target_spec.target_task_id
        or completion_state.target_task_id != target_spec.target_task_id
    ):
        raise ValueError("target state identity mismatch")


def _validate_data_refs(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    evidence: Mapping[str, EvidenceReference],
    questions: Mapping[str, OpenQuestion],
) -> None:
    if len(target_state.evidence_refs) != len(set(target_state.evidence_refs)):
        raise ValueError("duplicate target evidence references")
    if len(target_state.open_question_refs) != len(
        set(target_state.open_question_refs)
    ):
        raise ValueError("duplicate target question references")
    for evidence_id in target_state.evidence_refs:
        _require_evidence(evidence, evidence_id, target_spec)
    for question_id in target_state.open_question_refs:
        _require_question(questions, question_id, target_spec)


def _validate_checkpoints_and_artifacts(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
) -> None:
    checkpoints: dict[str, TaskCheckpoint] = {}
    checkpoint_root = store.paths.target_root(target_spec) / "checkpoints"
    if checkpoint_root.exists():
        for path in sorted(checkpoint_root.iterdir()):
            if not path.is_dir():
                raise ValueError("unexpected checkpoint entry")
            checkpoints[path.name] = validate_checkpoint(store, target_spec, path.name)
    sequences = [item.checkpoint_sequence for item in checkpoints.values()]
    if len(sequences) != len(set(sequences)):
        raise ValueError("checkpoint sequence is duplicated")
    if checkpoints and target_state.last_checkpoint_ref is None:
        raise ValueError("checkpoint history has no current checkpoint reference")
    if target_state.last_checkpoint_ref is not None:
        checkpoint = checkpoints.get(target_state.last_checkpoint_ref)
        if checkpoint is None:
            raise ValueError("last_checkpoint_ref does not resolve")
        if checkpoint.checkpoint_sequence != max(
            item.checkpoint_sequence for item in checkpoints.values()
        ):
            raise ValueError("last_checkpoint_ref is not the latest checkpoint")
        if _is_pre_worker_repair(target_state):
            _validate_pre_worker_repair_candidate(
                target_state,
                completion_state,
                checkpoint,
            )
        else:
            _restore_exact_checkpoint_artifacts(
                store, target_spec, target_state, checkpoint
            )
    _validate_current_artifact_inventory(target_spec, target_state)


def _is_pre_worker_repair(target_state: TargetTaskState) -> bool:
    return bool(target_state.open_finding_refs) and target_state.phase in {
        TargetPhase.REPAIR,
        TargetPhase.SCHEDULED,
        TargetPhase.HYDRATING,
    }


def _validate_pre_worker_repair_candidate(
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    checkpoint: TaskCheckpoint,
) -> None:
    checkpoint_state = checkpoint.task_state
    if (
        target_state.artifact_refs != checkpoint_state.artifact_refs
        or target_state.evidence_refs != checkpoint_state.evidence_refs
        or target_state.open_question_refs != checkpoint_state.open_question_refs
        or target_state.working_summary != checkpoint_state.working_summary
        or completion_state != checkpoint.completion_state
    ):
        raise ValueError(
            "pre-worker repair candidate does not match its selected checkpoint"
        )


def _restore_exact_checkpoint_artifacts(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    checkpoint: TaskCheckpoint,
) -> None:
    checkpoint_refs = {
        (item.artifact_id, item.revision, item.digest): item
        for item in checkpoint.task_state.artifact_refs
    }
    workspace = Path(target_spec.target_workspace).resolve()
    checkpoint_root = store.paths.checkpoint_root(target_spec, checkpoint.checkpoint_id)
    for current_ref in target_state.artifact_refs:
        current_path = (workspace / current_ref.relative_path).resolve()
        valid = current_path.is_file() and not current_path.is_symlink()
        if valid:
            digest = hashlib.sha256(current_path.read_bytes()).hexdigest()
            valid = digest == current_ref.digest
        if valid:
            continue
        exact = checkpoint_refs.get(
            (current_ref.artifact_id, current_ref.revision, current_ref.digest)
        )
        if exact is None or exact.relative_path != current_ref.relative_path:
            raise ValueError("artifact cannot be restored without rollback")
        snapshot = checkpoint_root / "artifacts" / exact.relative_path
        content = snapshot.read_bytes()
        if hashlib.sha256(content).hexdigest() != current_ref.digest:
            raise ValueError("checkpoint restore bytes do not match current ref")
        _atomic_write_bytes(current_path, content)


def _validate_current_artifact_inventory(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    workspace = Path(target_spec.target_workspace).resolve()
    expected: set[Path] = set()
    seen_ids: set[str] = set()
    for reference in target_state.artifact_refs:
        if reference.artifact_id in seen_ids:
            raise ValueError("duplicate current artifact identity")
        seen_ids.add(reference.artifact_id)
        path = (workspace / reference.relative_path).resolve()
        if (
            not path.is_relative_to(workspace)
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ValueError("current artifact path is missing or unsafe")
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference.digest:
            raise ValueError("current artifact digest mismatch")
        expected.add(path)
    actual = {path.resolve() for path in workspace.rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("candidate workspace contains unexpected files")


def _validate_completion_definition(
    completion_state: TargetCompletionState,
    definition: TargetDefinition,
) -> None:
    expected = [item.obligation_id for item in definition.completion_obligations]
    actual = [item.obligation_id for item in completion_state.items]
    if actual != expected:
        raise ValueError("completion obligations do not match target definition")


def _validate_evaluation_finding_refs(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    *,
    skip_fleet_review: bool = False,
) -> None:
    from bridger.memory.evaluation.fleet_validation import (
        resolve_fleet_validation_finding,
    )
    from bridger.memory.evaluation.review import resolve_review_finding
    from bridger.memory.evaluation.validation import resolve_validation_finding

    finding_ids = [reference.finding_id for reference in target_state.open_finding_refs]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("duplicate target finding references")
    for reference in target_state.open_finding_refs:
        if reference.origin is FindingOrigin.HARD_VALIDATION:
            resolve_validation_finding(
                store,
                target_spec,
                reference.finding_id,
            )
        elif reference.origin is FindingOrigin.TARGET_REVIEW:
            resolve_review_finding(
                store,
                target_spec,
                reference.finding_id,
            )
        elif reference.origin is FindingOrigin.FLEET_VALIDATION:
            finding = resolve_fleet_validation_finding(
                store,
                reference.finding_id,
            )
            if target_spec.target_task_id not in finding.affected_target_task_ids:
                raise ValueError("fleet finding is routed to an unaffected target")
        elif reference.origin is FindingOrigin.FLEET_REVIEW:
            if skip_fleet_review:
                continue
            from bridger.memory.evaluation.fleet_review import (
                resolve_fleet_review_finding,
            )

            review_finding = resolve_fleet_review_finding(
                store,
                reference.finding_id,
            )
            if (
                target_spec.target_task_id
                not in review_finding.affected_target_task_ids
            ):
                raise ValueError(
                    "fleet review finding is routed to an unaffected target"
                )


def _validate_accepted_result_ref(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    result_id = target_state.last_accepted_result_ref
    if result_id is None:
        if target_state.phase is TargetPhase.ACCEPTED:
            raise ValueError("ACCEPTED target has no accepted result")
        return
    from bridger.memory.evaluation.acceptance import resolve_accepted_target_result

    result = resolve_accepted_target_result(store, target_spec, result_id)
    if (
        target_state.phase is TargetPhase.ACCEPTED
        and target_state.pending_finalization_request_ref is not None
    ):
        raise ValueError("ACCEPTED target still has a pending finalization request")
    if target_state.phase is TargetPhase.ACCEPTED:
        completion_state = TargetCompletionState.model_validate_json(
            store.paths.completion_state(target_spec).read_bytes()
        )
        if (
            target_state.artifact_refs != result.artifact_refs
            or target_state.evidence_refs != result.evidence_refs
            or completion_state.items != result.completion_items
        ):
            raise ValueError("ACCEPTED target no longer matches its accepted result")


def _validate_fleet_state(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Mapping[str, TargetTaskSpec],
    target_states: Mapping[str, TargetTaskState],
) -> None:
    if (
        fleet_state.fleet_run_id != fleet_spec.fleet_run_id
        or fleet_state.target_task_ids != list(target_specs)
        or set(target_states) != set(target_specs)
    ):
        raise ValueError("fleet state target inventory is inconsistent")
    summed = ExecutionUsage()
    for target_state in target_states.values():
        for field_name in ExecutionUsage.model_fields:
            setattr(
                summed,
                field_name,
                getattr(summed, field_name) + getattr(target_state.usage, field_name),
            )
    exact_fields = {"cycles", "tool_calls", "repair_cycles"}
    for field_name in ExecutionUsage.model_fields:
        fleet_amount = getattr(fleet_state.usage, field_name)
        target_amount = getattr(summed, field_name)
        if (
            field_name in exact_fields
            and fleet_amount != target_amount
            or field_name not in exact_fields
            and fleet_amount < target_amount
        ):
            raise ValueError("target and fleet usage authorities have drifted")


def _validate_fleet_finding_refs(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    *,
    skip_fleet_review: bool = False,
) -> None:
    from bridger.memory.evaluation.fleet_review import resolve_fleet_review_finding
    from bridger.memory.evaluation.fleet_validation import (
        resolve_fleet_validation_finding,
    )

    finding_ids = [reference.finding_id for reference in fleet_state.open_finding_refs]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("duplicate fleet finding references")
    for reference in fleet_state.open_finding_refs:
        if reference.origin is FindingOrigin.FLEET_VALIDATION:
            resolve_fleet_validation_finding(store, reference.finding_id)
        elif reference.origin is FindingOrigin.FLEET_REVIEW:
            if skip_fleet_review:
                continue
            resolve_fleet_review_finding(store, reference.finding_id)
        else:
            raise ValueError("fleet state contains a target-level finding")


def _validate_reservation_capacity(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Mapping[str, TargetTaskSpec],
    target_states: Mapping[str, TargetTaskState],
    store: FleetRuntimeStore,
) -> None:
    reservations = store.provider_reservations()
    if any(
        item.target_task_id is not None and item.target_task_id not in target_specs
        for item in reservations
    ):
        raise ValueError("provider reservation belongs to an unknown target")
    fleet_input = sum(item.input_token_reservation for item in reservations)
    fleet_output = sum(item.output_token_reservation for item in reservations)
    if (
        fleet_spec.fleet_budget.max_input_tokens is not None
        and fleet_input
        and budgeted_input_tokens(fleet_state.usage) + fleet_input
        > fleet_spec.fleet_budget.max_input_tokens
    ) or (
        fleet_spec.fleet_budget.max_output_tokens is not None
        and fleet_output
        and fleet_state.usage.output_tokens + fleet_output
        > fleet_spec.fleet_budget.max_output_tokens
    ):
        raise ValueError("provider ambiguity exceeds fleet token budget")
    for task_id, target_spec in target_specs.items():
        target_reservations = [
            item for item in reservations if item.target_task_id == task_id
        ]
        input_hold = sum(item.input_token_reservation for item in target_reservations)
        output_hold = sum(item.output_token_reservation for item in target_reservations)
        usage = target_states[task_id].usage
        if (
            target_spec.budget.max_input_tokens is not None
            and input_hold
            and budgeted_input_tokens(usage) + input_hold
            > target_spec.budget.max_input_tokens
        ) or (
            target_spec.budget.max_output_tokens is not None
            and output_hold
            and usage.output_tokens + output_hold > target_spec.budget.max_output_tokens
        ):
            raise ValueError("provider ambiguity exceeds target token budget")
        if target_states[task_id].phase in _ACTIVE_PHASES and target_reservations:
            input_limit = target_spec.budget.max_input_tokens
            output_limit = target_spec.budget.max_output_tokens
            if (
                input_limit is not None
                and budgeted_input_tokens(usage) + input_hold >= input_limit
            ) or (
                output_limit is not None
                and usage.output_tokens + output_hold >= output_limit
            ):
                raise ValueError(
                    "provider ambiguity leaves no safe target token capacity"
                )


def _validate_error_references(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    target_states: Mapping[str, TargetTaskState],
) -> None:
    referenced: list[tuple[str, str | None]] = []
    if fleet_state.last_error_ref is not None:
        referenced.append((fleet_state.last_error_ref, None))
    for task_id, target_state in target_states.items():
        if target_state.last_error_ref is not None:
            referenced.append((target_state.last_error_ref, task_id))
    for error_id, error_target_task_id in referenced:
        require_path_segment(error_id, "last_error_ref")
        record = RuntimeErrorRecord.model_validate_json(
            (store.paths.errors / f"{error_id}.json").read_bytes()
        )
        if (
            record.error_id != error_id
            or record.fleet_run_id != store.fleet_spec.fleet_run_id
            or record.target_task_id != error_target_task_id
        ):
            raise ValueError("runtime error reference identity mismatch")


__all__ = [
    "RecoveredFleet",
    "create_checkpoint",
    "initialize_persistence",
    "normalize_target_for_fleet_budget_stop",
    "record_runtime_error",
    "recover_fleet",
    "recover_target",
    "validate_checkpoint",
]
