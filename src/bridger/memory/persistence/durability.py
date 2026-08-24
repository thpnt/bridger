"""Crash-safe filesystem primitives for memory-harness Stage 5."""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from bridger.contracts.memory.core import (
    ExecutionBudget,
    ExecutionUsage,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
    budgeted_input_tokens,
)
from bridger.contracts.memory.persistence import TaskEvent
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.memory.persistence.store import require_path_segment

EventObserver = Callable[[TaskEvent], None]

_EVENTS_FILE = "events.jsonl"
_INITIALIZATION_DIRECTORY = "initialization"
_FLEET_STATE_FILE = "fleet-state.json"
_TARGETS_DIRECTORY = "targets"
_TARGET_SPEC_FILE = "target-task-spec.json"
_TARGET_STATE_FILE = "target-task-state.json"
_COMPLETION_STATE_FILE = "target-completion-state.json"
_TRANSACTIONS_DIRECTORY = "transactions"
_INFLIGHT_PROVIDER_DIRECTORY = "inflight/provider"
_ERRORS_DIRECTORY = "errors"
_CHECKPOINTS_DIRECTORY = "checkpoints"
_FINALIZATION_REQUESTS_DIRECTORY = "finalization-requests"
_VALIDATION_REPORTS_DIRECTORY = "validation-reports"
_VALIDATION_FINDINGS_DIRECTORY = "validation-findings"
_REVIEW_VERDICTS_DIRECTORY = "review-verdicts"
_REVIEW_FINDINGS_DIRECTORY = "review-findings"
_ACCEPTED_TARGET_RESULTS_DIRECTORY = "accepted-target-results"
_FLEET_VALIDATION_REPORTS_DIRECTORY = "fleet-validation-reports"
_FLEET_VALIDATION_FINDINGS_DIRECTORY = "fleet-validation-findings"
_FLEET_REVIEW_VERDICTS_DIRECTORY = "fleet-review-verdicts"
_FLEET_REVIEW_FINDINGS_DIRECTORY = "fleet-review-findings"
_ACCEPTED_MEMORY_FLEET_RESULTS_DIRECTORY = "accepted-memory-fleet-results"
_EVIDENCE_DIRECTORY = "evidence"
_QUESTIONS_DIRECTORY = "questions"

_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_USAGE_FIELDS = (
    "cycles",
    "model_calls",
    "tool_calls",
    "repair_cycles",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
)
_EVENT_REQUIRED_KEYS: dict[str, frozenset[str]] = {
    "fleet_bound": frozenset(),
    "fleet_initialized": frozenset(),
    "target_initialized": frozenset(),
    "phase_transition": frozenset({"from_phase", "to_phase"}),
    "context_hydrated": frozenset(),
    "cycle_started": frozenset({"usage_delta"}),
    "cycle_finished": frozenset(
        {
            "cycle_id",
            "cycle_number",
            "outcome",
            "focus",
            "usage_delta",
            "completion_changes",
        }
    ),
    "model_attempt_started": frozenset({"attempt_id"}),
    "model_attempt_completed": frozenset({"attempt_id"}),
    "model_attempt_failed": frozenset({"attempt_id"}),
    "tool_dispatch_started": frozenset({"tool"}),
    "tool_dispatch_completed": frozenset({"tool", "status"}),
    "tool_dispatch_rejected": frozenset({"tool", "status"}),
    "tool_dispatch_failed": frozenset({"tool", "status"}),
    "compaction_started": frozenset(
        {
            "projected_context_tokens",
            "active_context_soft_limit_tokens",
            "model_context_window_tokens",
        }
    ),
    "compaction_completed": frozenset(
        {
            "projected_context_tokens",
            "active_context_soft_limit_tokens",
            "model_context_window_tokens",
        }
    ),
    "artifact_mutated": frozenset({"action"}),
    "evidence_recorded": frozenset({"evidence_id"}),
    "completion_updated": frozenset({"obligation_id"}),
    "progress_updated": frozenset(),
    "question_opened": frozenset({"question_ids"}),
    "question_resolved": frozenset({"question_ids"}),
    "usage_delta": frozenset({"usage_delta"}),
    "finalization_control_received": frozenset(),
    "finalization_requested": frozenset(
        {
            "finalization_request_id",
            "candidate_checkpoint_ref",
            "from_phase",
            "to_phase",
        }
    ),
    "validation_started": frozenset(
        {
            "finalization_request_id",
            "candidate_checkpoint_ref",
            "from_phase",
            "to_phase",
        }
    ),
    "validation_completed": frozenset(
        {
            "validation_report_id",
            "finalization_request_id",
            "candidate_checkpoint_ref",
            "verdict",
            "from_phase",
            "to_phase",
        }
    ),
    "review_completed": frozenset(
        {
            "review_verdict_id",
            "finalization_request_id",
            "candidate_checkpoint_ref",
            "verdict",
            "from_phase",
            "to_phase",
        }
    ),
    "target_accepted": frozenset(
        {
            "accepted_target_result_id",
            "finalization_request_id",
            "validation_report_id",
            "review_verdict_id",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_validation_started": frozenset(
        {
            "accepted_target_result_refs",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_validation_completed": frozenset(
        {
            "fleet_validation_report_id",
            "accepted_target_result_refs",
            "verdict",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_repair_routed": frozenset(
        {
            "fleet_validation_report_id",
            "affected_target_task_ids",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_review_completed": frozenset(
        {
            "fleet_review_id",
            "fleet_validation_report_ref",
            "verdict",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_review_repair_routed": frozenset(
        {
            "fleet_review_id",
            "affected_target_task_ids",
            "from_phase",
            "to_phase",
        }
    ),
    "fleet_accepted": frozenset(
        {
            "accepted_memory_fleet_result_id",
            "fleet_validation_report_ref",
            "fleet_review_verdict_ref",
            "from_phase",
            "to_phase",
        }
    ),
    "checkpoint_created": frozenset({"checkpoint_id"}),
    "retry_scheduled": frozenset({"attempt", "delay_seconds"}),
    "execution_interrupted": frozenset(
        {"reason", "operation", "retryable", "error_id"}
    ),
    "runtime_error_recorded": frozenset({"error_id"}),
    "recovery_reset": frozenset({"from_phase", "to_phase"}),
    "fleet_execution_finished": frozenset(
        {"fleet_phase", "target_phase_counts", "usage"}
    ),
}


class _StagedWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    destination: str
    staged_name: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class _EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    target_task_id: str | None = None
    event_type: str
    operation_id: str
    payload: dict[str, JsonValue]


class _TransactionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    operation_id: str
    fleet_run_id: str
    writes: list[_StagedWrite]
    deletions: list[str]
    event: _EventDraft


class _ProviderReservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    attempt_id: str
    target_task_id: str | None = None
    input_token_reservation: int = Field(ge=0)
    output_token_reservation: int = Field(ge=0)
    state: str = Field(pattern=r"^(prepared|invoked)$")
    trace_context: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimePaths:
    """Resolve the existing Stage 0/1 layout for one fleet run."""

    def __init__(self, fleet_spec: MemoryFleetSpec) -> None:
        self.fleet_spec = fleet_spec
        self.run_root = (
            Path(fleet_spec.runtime_root).resolve() / fleet_spec.fleet_run_id
        )
        self.initialization_root = self.run_root / _INITIALIZATION_DIRECTORY
        self.output_root = Path(fleet_spec.output_root).resolve()

    @property
    def fleet_state(self) -> Path:
        return self.initialization_root / _FLEET_STATE_FILE

    @property
    def events(self) -> Path:
        return self.run_root / _EVENTS_FILE

    @property
    def transactions(self) -> Path:
        return self.run_root / _TRANSACTIONS_DIRECTORY

    @property
    def provider_inflight(self) -> Path:
        return self.run_root / _INFLIGHT_PROVIDER_DIRECTORY

    @property
    def errors(self) -> Path:
        return self.run_root / _ERRORS_DIRECTORY

    def target_root(self, target_spec: TargetTaskSpec) -> Path:
        require_path_segment(target_spec.target_id, "target_id")
        return self.initialization_root / _TARGETS_DIRECTORY / target_spec.target_id

    def target_state(self, target_spec: TargetTaskSpec) -> Path:
        return self.target_root(target_spec) / _TARGET_STATE_FILE

    def target_spec(self, target_id: str) -> Path:
        require_path_segment(target_id, "target_id")
        return (
            self.initialization_root
            / _TARGETS_DIRECTORY
            / target_id
            / _TARGET_SPEC_FILE
        )

    def completion_state(self, target_spec: TargetTaskSpec) -> Path:
        return self.target_root(target_spec) / _COMPLETION_STATE_FILE

    def evidence(self, target_spec: TargetTaskSpec, evidence_id: str) -> Path:
        require_path_segment(evidence_id, "evidence_id")
        return (
            self.target_root(target_spec) / _EVIDENCE_DIRECTORY / f"{evidence_id}.json"
        )

    def question(self, target_spec: TargetTaskSpec, question_id: str) -> Path:
        require_path_segment(question_id, "question_id")
        return (
            self.target_root(target_spec) / _QUESTIONS_DIRECTORY / f"{question_id}.json"
        )

    def checkpoint_root(self, target_spec: TargetTaskSpec, checkpoint_id: str) -> Path:
        require_path_segment(checkpoint_id, "checkpoint_id")
        return self.target_root(target_spec) / _CHECKPOINTS_DIRECTORY / checkpoint_id

    def finalization_request(
        self,
        target_spec: TargetTaskSpec,
        finalization_request_id: str,
    ) -> Path:
        """Resolve one immutable target finalization-request record."""
        require_path_segment(finalization_request_id, "finalization_request_id")
        return (
            self.target_root(target_spec)
            / _FINALIZATION_REQUESTS_DIRECTORY
            / f"{finalization_request_id}.json"
        )

    def validation_report(
        self,
        target_spec: TargetTaskSpec,
        validation_report_id: str,
    ) -> Path:
        """Resolve one immutable target validation-report record."""
        require_path_segment(validation_report_id, "validation_report_id")
        return (
            self.target_root(target_spec)
            / _VALIDATION_REPORTS_DIRECTORY
            / f"{validation_report_id}.json"
        )

    def validation_finding(
        self,
        target_spec: TargetTaskSpec,
        finding_id: str,
    ) -> Path:
        """Resolve one immutable target hard-validation finding record."""
        require_path_segment(finding_id, "finding_id")
        return (
            self.target_root(target_spec)
            / _VALIDATION_FINDINGS_DIRECTORY
            / f"{finding_id}.json"
        )

    def review_verdict(
        self,
        target_spec: TargetTaskSpec,
        review_verdict_id: str,
    ) -> Path:
        """Resolve one immutable target-review verdict record."""
        require_path_segment(review_verdict_id, "review_verdict_id")
        return (
            self.target_root(target_spec)
            / _REVIEW_VERDICTS_DIRECTORY
            / f"{review_verdict_id}.json"
        )

    def review_finding(
        self,
        target_spec: TargetTaskSpec,
        finding_id: str,
    ) -> Path:
        """Resolve one immutable target-review finding record."""
        require_path_segment(finding_id, "finding_id")
        return (
            self.target_root(target_spec)
            / _REVIEW_FINDINGS_DIRECTORY
            / f"{finding_id}.json"
        )

    def accepted_target_result(
        self,
        target_spec: TargetTaskSpec,
        accepted_target_result_id: str,
    ) -> Path:
        """Resolve one immutable locally accepted target result."""
        require_path_segment(
            accepted_target_result_id,
            "accepted_target_result_id",
        )
        return (
            self.target_root(target_spec)
            / _ACCEPTED_TARGET_RESULTS_DIRECTORY
            / f"{accepted_target_result_id}.json"
        )

    def fleet_validation_report(self, report_id: str) -> Path:
        """Resolve one immutable fleet-validation report record."""
        require_path_segment(report_id, "fleet_validation_report_id")
        return self.run_root / _FLEET_VALIDATION_REPORTS_DIRECTORY / f"{report_id}.json"

    def fleet_validation_finding(self, finding_id: str) -> Path:
        """Resolve one immutable fleet-validation finding record."""
        require_path_segment(finding_id, "finding_id")
        return (
            self.run_root / _FLEET_VALIDATION_FINDINGS_DIRECTORY / f"{finding_id}.json"
        )

    def fleet_review_verdict(self, fleet_review_id: str) -> Path:
        """Resolve one immutable fleet-review verdict record."""
        require_path_segment(fleet_review_id, "fleet_review_id")
        return (
            self.run_root / _FLEET_REVIEW_VERDICTS_DIRECTORY / f"{fleet_review_id}.json"
        )

    def fleet_review_finding(self, finding_id: str) -> Path:
        """Resolve one immutable fleet-review finding record."""
        require_path_segment(finding_id, "finding_id")
        return self.run_root / _FLEET_REVIEW_FINDINGS_DIRECTORY / f"{finding_id}.json"

    def accepted_memory_fleet_result(self, result_id: str) -> Path:
        """Resolve one immutable accepted memory-fleet result."""
        require_path_segment(result_id, "accepted_memory_fleet_result_id")
        return (
            self.run_root
            / _ACCEPTED_MEMORY_FLEET_RESULTS_DIRECTORY
            / f"{result_id}.json"
        )


class FleetRunLock(AbstractContextManager["FleetRunLock"]):
    """Lifetime advisory ownership lock for one local fleet runtime."""

    def __init__(self, run_root: Path) -> None:
        self._path = run_root / "run.lock"
        self._file: Any | None = None

    def acquire(self) -> Self:
        """Acquire exclusive non-blocking process ownership."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        file = self._path.open("a+b")
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise RuntimeError("fleet runtime is already owned by another process")
        self._file = file
        return self

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None


class _RuntimeLocks:
    def __init__(self) -> None:
        self.fleet = threading.RLock()
        self.trace = threading.RLock()
        self.targets: dict[str, threading.RLock] = {}
        self.guard = threading.Lock()

    def target(self, target_task_id: str) -> threading.RLock:
        with self.guard:
            return self.targets.setdefault(target_task_id, threading.RLock())


_LOCKS_BY_RUN: dict[str, _RuntimeLocks] = {}
_LOCKS_GUARD = threading.Lock()


def _runtime_locks(run_root: Path) -> _RuntimeLocks:
    identity = str(run_root.resolve())
    with _LOCKS_GUARD:
        return _LOCKS_BY_RUN.setdefault(identity, _RuntimeLocks())


class FleetRuntimeStore:
    """Explicit Stage 5 durability boundary for one bound fleet run."""

    def __init__(
        self,
        fleet_spec: MemoryFleetSpec,
        *,
        event_observer: EventObserver | None = None,
    ) -> None:
        self.fleet_spec = MemoryFleetSpec.model_validate(
            fleet_spec.model_dump(mode="python")
        )
        self.paths = RuntimePaths(self.fleet_spec)
        self._locks = _runtime_locks(self.paths.run_root)
        self._ownership_lock: FleetRunLock | None = None
        self._event_observer = event_observer

    def run_lock(self) -> FleetRunLock:
        """Return the process-ownership lock for this fleet run."""
        return FleetRunLock(self.paths.run_root)

    def set_event_observer(self, observer: EventObserver | None) -> None:
        """Attach best-effort observation after an authoritative snapshot is seeded."""
        self._event_observer = observer

    def acquire_ownership(self) -> None:
        """Hold process ownership for the lifetime of a fresh fleet runtime."""
        if self._ownership_lock is None:
            self._ownership_lock = self.run_lock().acquire()

    def close(self) -> None:
        """Release fresh-run process ownership."""
        if self._ownership_lock is not None:
            self._ownership_lock.__exit__(None, None, None)
            self._ownership_lock = None

    @contextmanager
    def state_locks(self, target_task_id: str | None = None) -> Iterator[None]:
        """Acquire process-local state locks in the required global order."""
        with self._locks.fleet:
            if target_task_id is None:
                yield
                return
            with self._locks.target(target_task_id):
                yield

    @contextmanager
    def target_lock(self, target_task_id: str) -> Iterator[None]:
        """Acquire one target-local mutation lock without fleet state."""
        with self._locks.target(target_task_id):
            yield

    def append_event(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        target_task_id: str | None = None,
        operation_id: str | None = None,
        event_id: str | None = None,
    ) -> TaskEvent:
        """Validate and durably append one ordered trace event."""
        normalized_payload = self._validate_event_payload(event_type, payload)
        with self._locks.trace:
            events = self.recover_event_tail()
            resolved_event_id = event_id or f"event-{uuid4().hex}"
            for existing in events:
                if existing.event_id == resolved_event_id:
                    return existing
            event = TaskEvent(
                event_id=resolved_event_id,
                fleet_run_id=self.fleet_spec.fleet_run_id,
                target_task_id=target_task_id,
                sequence=events[-1].sequence + 1 if events else 1,
                event_type=event_type,
                timestamp=_timestamp(),
                operation_id=operation_id,
                payload=normalized_payload,
            )
            serialized = _canonical_json(event) + b"\n"
            self.paths.events.parent.mkdir(parents=True, exist_ok=True)
            created = not self.paths.events.exists()
            with self.paths.events.open("ab") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            if created:
                _fsync_directory(self.paths.events.parent)
            self._notify_event_observer(event)
            return event

    def _notify_event_observer(self, event: TaskEvent) -> None:
        observer = self._event_observer
        if observer is None:
            return
        try:
            observer(event)
        except Exception:
            pass

    def recover_event_tail(self) -> list[TaskEvent]:
        """Validate the trace and truncate only an invalid torn final record."""
        path = self.paths.events
        if not path.exists():
            return []
        data = path.read_bytes()
        if not data:
            return []
        lines = data.splitlines(keepends=True)
        events: list[TaskEvent] = []
        valid_bytes = 0
        seen_event_ids: set[str] = set()
        for index, line in enumerate(lines):
            is_last = index == len(lines) - 1
            try:
                event = TaskEvent.model_validate_json(line.rstrip(b"\r\n"))
            except Exception as error:
                if not is_last:
                    raise ValueError(
                        "events trace is corrupt before its tail"
                    ) from error
                _atomic_write_bytes(path, data[:valid_bytes])
                return events
            expected_sequence = events[-1].sequence + 1 if events else 1
            if event.fleet_run_id != self.fleet_spec.fleet_run_id:
                raise ValueError("trace event belongs to another fleet")
            if event.sequence != expected_sequence:
                raise ValueError("trace sequence is not contiguous")
            if event.event_id in seen_event_ids:
                raise ValueError("trace event identity is duplicated")
            self._validate_event_payload(event.event_type, event.payload)
            events.append(event)
            seen_event_ids.add(event.event_id)
            valid_bytes += len(line)
        if data and not data.endswith(b"\n"):
            _atomic_write_bytes(path, data + b"\n")
        return events

    def trace_high_water(self) -> int:
        """Return the latest valid fleet-global event sequence."""
        with self._locks.trace:
            events = self.recover_event_tail()
            return events[-1].sequence if events else 0

    def commit_operation(
        self,
        *,
        operation_id: str,
        writes: Mapping[Path, bytes],
        deletions: Iterable[Path] = (),
        event_type: str,
        payload: Mapping[str, object],
        target_task_id: str | None = None,
    ) -> None:
        """Commit and apply one redo-style multi-authority operation."""
        require_path_segment(operation_id, "operation_id")
        normalized_payload = self._validate_event_payload(event_type, payload)
        transaction_root = self.paths.transactions / operation_id
        if transaction_root.exists():
            intent_path = transaction_root / "intent.json"
            if not intent_path.exists():
                shutil.rmtree(transaction_root)
            else:
                intent = _TransactionIntent.model_validate_json(
                    intent_path.read_bytes()
                )
                self._apply_intent(transaction_root, intent)
                return
        transaction_root.mkdir(parents=True)
        staged_root = transaction_root / "staged"
        staged_root.mkdir()
        staged_writes: list[_StagedWrite] = []
        try:
            for index, (destination, content) in enumerate(writes.items()):
                resolved = self._validate_destination(destination)
                staged_name = f"{index:04d}.bin"
                staged_path = staged_root / staged_name
                _atomic_write_bytes(staged_path, content)
                staged_writes.append(
                    _StagedWrite(
                        destination=str(resolved),
                        staged_name=staged_name,
                        digest=_sha256(content),
                    )
                )
            resolved_deletions = [
                str(self._validate_destination(path)) for path in deletions
            ]
            intent = _TransactionIntent(
                operation_id=operation_id,
                fleet_run_id=self.fleet_spec.fleet_run_id,
                writes=staged_writes,
                deletions=resolved_deletions,
                event=_EventDraft(
                    event_id=f"event-{uuid4().hex}",
                    target_task_id=target_task_id,
                    event_type=event_type,
                    operation_id=operation_id,
                    payload=normalized_payload,
                ),
            )
            _atomic_create_bytes(
                transaction_root / "intent.json",
                _canonical_json(intent) + b"\n",
            )
            _fsync_directory(transaction_root)
            self._apply_intent(transaction_root, intent)
        except BaseException:
            if not (transaction_root / "intent.json").exists():
                shutil.rmtree(transaction_root, ignore_errors=True)
            raise

    def recover_transactions(self) -> None:
        """Discard uncommitted staging and finish committed intents forward."""
        root = self.paths.transactions
        if not root.exists():
            return
        for transaction_root in sorted(root.iterdir()):
            if not transaction_root.is_dir():
                raise ValueError("unexpected transaction entry")
            intent_path = transaction_root / "intent.json"
            if not intent_path.exists():
                shutil.rmtree(transaction_root)
                continue
            intent = _TransactionIntent.model_validate_json(intent_path.read_bytes())
            if intent.fleet_run_id != self.fleet_spec.fleet_run_id:
                raise ValueError("transaction intent belongs to another fleet")
            self._apply_intent(transaction_root, intent)

    def discard_temporary_files(self) -> None:
        """Remove known abandoned atomic-write siblings from runtime authorities."""
        roots = [self.paths.run_root]
        for target_spec in self.load_target_specs():
            roots.append(Path(target_spec.target_workspace).resolve())
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob(".*.tmp"):
                if path.is_file() and not path.is_symlink():
                    path.unlink()
                    _fsync_directory(path.parent)

    def persist_target_state(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        *,
        event_type: str,
        payload: Mapping[str, object],
        operation_id: str | None = None,
    ) -> None:
        """Atomically persist one target authority, then append its trace."""
        with self.target_lock(target_spec.target_task_id):
            self._validate_target_identity(target_spec, target_state)
            _atomic_write_model(self.paths.target_state(target_spec), target_state)
            self.append_event(
                event_type,
                payload,
                target_task_id=target_spec.target_task_id,
                operation_id=operation_id,
            )

    def exhaust_fleet_budget(self, fleet_state: FleetRunState) -> None:
        """Durably record expected fleet-level execution budget exhaustion."""
        with self.state_locks():
            if fleet_state.fleet_run_id != self.fleet_spec.fleet_run_id:
                raise ValueError("fleet state belongs to another fleet")
            before = fleet_state.phase
            after = fleet_state.model_copy(
                update={
                    "phase": FleetPhase.EXHAUSTED,
                    "termination_reason": "fleet budget exhaustion",
                }
            )
            self.commit_operation(
                operation_id=f"fleet-budget-exhausted-{uuid4().hex}",
                writes={self.paths.fleet_state: _model_bytes(after)},
                event_type="phase_transition",
                payload={
                    "from_phase": before.value,
                    "to_phase": FleetPhase.EXHAUSTED.value,
                    "reason": "fleet budget exhaustion",
                },
            )
            _replace_model(fleet_state, after)

    def persist_completion_state(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        completion_state: TargetCompletionState,
        *,
        obligation_id: str,
    ) -> None:
        """Atomically persist a completion update and its trace record."""
        with self.target_lock(target_spec.target_task_id):
            self._validate_target_identity(target_spec, target_state)
            self._require_worker_mutation_phase(target_state)
            if completion_state.target_task_id != target_spec.target_task_id:
                raise ValueError("completion state belongs to another target")
            status = next(
                (
                    item.status
                    for item in completion_state.items
                    if item.obligation_id == obligation_id
                ),
                None,
            )
            if status is None:
                raise ValueError("completion state is missing the updated obligation")
            _atomic_write_model(
                self.paths.completion_state(target_spec), completion_state
            )
            self.append_event(
                "completion_updated",
                {
                    "obligation_id": obligation_id,
                    "status": status.value,
                },
                target_task_id=target_spec.target_task_id,
            )

    def persist_scheduling_snapshot(
        self,
        fleet_state: FleetRunState,
        target_specs: Iterable[TargetTaskSpec],
        target_states: Iterable[TargetTaskState],
        scheduled_target_task_ids: Iterable[str],
    ) -> None:
        """Commit one Stage 2 admission pass as a durable state snapshot."""
        specs = {item.target_task_id: item for item in target_specs}
        states = {item.target_task_id: item for item in target_states}
        if set(specs) != set(states):
            raise ValueError("scheduling authorities do not align")
        scheduled = list(scheduled_target_task_ids)
        writes = {self.paths.fleet_state: _model_bytes(fleet_state)}
        for task_id, state in states.items():
            writes[self.paths.target_state(specs[task_id])] = _model_bytes(state)
        with self._locks.fleet, ExitStack() as stack:
            for task_id in sorted(states):
                stack.enter_context(self._locks.target(task_id))
            self.commit_operation(
                operation_id=f"scheduling-{uuid4().hex}",
                writes=writes,
                event_type="phase_transition",
                payload={
                    "from_phase": "schedulable",
                    "to_phase": "scheduled",
                    "target_task_ids": scheduled,
                },
            )

    def apply_usage_delta(
        self,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        delta: Mapping[str, int],
        *,
        event_type: str = "usage_delta",
        extra_writes: Mapping[Path, bytes] | None = None,
        deletions: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
        operation_id: str | None = None,
        phase: TargetPhase | None = None,
        allow_budget_overage: bool = False,
    ) -> str:
        """Serialize and durably apply one target/fleet usage operation."""
        with self.state_locks(target_spec.target_task_id):
            return self._apply_usage_delta_locked(
                fleet_state,
                target_spec,
                target_state,
                delta,
                event_type=event_type,
                extra_writes=extra_writes,
                deletions=deletions,
                payload=payload,
                operation_id=operation_id,
                phase=phase,
                allow_budget_overage=allow_budget_overage,
            )

    def apply_fleet_usage_delta(
        self,
        fleet_state: FleetRunState,
        delta: Mapping[str, int],
        *,
        event_type: str = "usage_delta",
        deletions: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
        operation_id: str | None = None,
        allow_budget_overage: bool = False,
    ) -> str:
        """Durably charge fleet-only work without attributing it to a target."""
        with self.state_locks():
            if fleet_state.fleet_run_id != self.fleet_spec.fleet_run_id:
                raise ValueError("fleet state belongs to another fleet")
            normalized = {name: 0 for name in _USAGE_FIELDS}
            for field_name, amount in delta.items():
                if (
                    field_name not in normalized
                    or isinstance(amount, bool)
                    or amount < 0
                ):
                    raise ValueError("usage deltas must be known non-negative integers")
                normalized[field_name] = amount
            after_fleet = fleet_state.model_copy(deep=True)
            for field_name, amount in normalized.items():
                setattr(
                    after_fleet.usage,
                    field_name,
                    getattr(after_fleet.usage, field_name) + amount,
                )
            if not allow_budget_overage:
                self._require_within_budget(
                    self.fleet_spec.fleet_budget,
                    after_fleet.usage,
                    "fleet",
                )
            resolved_operation_id = operation_id or f"operation-{uuid4().hex}"
            event_payload = dict(payload or {})
            event_payload["usage_delta"] = {
                field_name: amount
                for field_name, amount in normalized.items()
                if amount
            }
            self.commit_operation(
                operation_id=resolved_operation_id,
                writes={self.paths.fleet_state: _model_bytes(after_fleet)},
                deletions=deletions,
                event_type=event_type,
                payload=event_payload,
            )
            _replace_model(fleet_state, after_fleet)
            return resolved_operation_id

    def _apply_usage_delta_locked(
        self,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        delta: Mapping[str, int],
        *,
        event_type: str = "usage_delta",
        extra_writes: Mapping[Path, bytes] | None = None,
        deletions: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
        operation_id: str | None = None,
        phase: TargetPhase | None = None,
        allow_budget_overage: bool = False,
    ) -> str:
        """Durably apply one monotonic target/fleet usage operation."""
        self._validate_target_identity(target_spec, target_state)
        if fleet_state.fleet_run_id != self.fleet_spec.fleet_run_id:
            raise ValueError("fleet state belongs to another fleet")
        normalized = {name: 0 for name in _USAGE_FIELDS}
        for field_name, amount in delta.items():
            if field_name not in normalized or isinstance(amount, bool) or amount < 0:
                raise ValueError("usage deltas must be known non-negative integers")
            normalized[field_name] = amount
        after_target = target_state.model_copy(deep=True)
        after_fleet = fleet_state.model_copy(deep=True)
        for field_name, amount in normalized.items():
            setattr(
                after_target.usage,
                field_name,
                getattr(after_target.usage, field_name) + amount,
            )
            setattr(
                after_fleet.usage,
                field_name,
                getattr(after_fleet.usage, field_name) + amount,
            )
        if phase is not None:
            after_target.phase = phase
        if not allow_budget_overage:
            self._require_within_budget(
                target_spec.budget, after_target.usage, "target"
            )
            self._require_within_budget(
                self.fleet_spec.fleet_budget, after_fleet.usage, "fleet"
            )
        resolved_operation_id = operation_id or f"operation-{uuid4().hex}"
        writes = {
            self.paths.target_state(target_spec): _model_bytes(after_target),
            self.paths.fleet_state: _model_bytes(after_fleet),
        }
        if extra_writes:
            writes.update(extra_writes)
        event_payload = dict(payload or {})
        event_payload["usage_delta"] = {
            field_name: amount for field_name, amount in normalized.items() if amount
        }
        if phase is not None and target_state.phase is not phase:
            event_payload["from_phase"] = target_state.phase.value
            event_payload["to_phase"] = phase.value
        self.commit_operation(
            operation_id=resolved_operation_id,
            writes=writes,
            deletions=deletions,
            event_type=event_type,
            payload=event_payload,
            target_task_id=target_spec.target_task_id,
        )
        _replace_model(target_state, after_target)
        _replace_model(fleet_state, after_fleet)
        return resolved_operation_id

    def prepare_provider_attempt(
        self,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        *,
        input_tokens: int,
        output_tokens: int,
        cycle_start: bool,
        repair: bool = False,
        trace_context: Mapping[str, object] | None = None,
    ) -> str:
        """Charge a model attempt and persist its prepared budget reservation."""
        with self.state_locks(target_spec.target_task_id):
            self._require_provider_capacity(
                fleet_state,
                target_spec,
                target_state,
                input_tokens,
                output_tokens,
            )
            attempt_id = f"attempt-{uuid4().hex}"
            reservation = _ProviderReservation(
                attempt_id=attempt_id,
                target_task_id=target_spec.target_task_id,
                input_token_reservation=input_tokens,
                output_token_reservation=output_tokens,
                state="prepared",
                trace_context=_JSON_VALUE_ADAPTER.validate_python(
                    dict(trace_context or {})
                ),
            )
            delta = {"model_calls": 1}
            if cycle_start:
                delta["cycles"] = 1
                if repair:
                    delta["repair_cycles"] = 1
            self._apply_usage_delta_locked(
                fleet_state,
                target_spec,
                target_state,
                delta,
                event_type="cycle_started" if cycle_start else "usage_delta",
                extra_writes={
                    self.provider_reservation_path(attempt_id): _model_bytes(
                        reservation
                    )
                },
                payload={
                    "attempt_id": attempt_id,
                    **dict(trace_context or {}),
                },
                phase=TargetPhase.WORKING if cycle_start else None,
            )
            return attempt_id

    def prepare_fleet_provider_attempt(
        self,
        fleet_state: FleetRunState,
        *,
        input_tokens: int,
        output_tokens: int,
        trace_context: Mapping[str, object] | None = None,
    ) -> str:
        """Charge and reserve one fleet-only provider invocation."""
        with self.state_locks():
            self._require_fleet_provider_capacity(
                fleet_state,
                input_tokens,
                output_tokens,
            )
            attempt_id = f"attempt-{uuid4().hex}"
            reservation = _ProviderReservation(
                attempt_id=attempt_id,
                input_token_reservation=input_tokens,
                output_token_reservation=output_tokens,
                state="prepared",
                trace_context=_JSON_VALUE_ADAPTER.validate_python(
                    dict(trace_context or {})
                ),
            )
            after_fleet = fleet_state.model_copy(deep=True)
            after_fleet.usage.model_calls += 1
            self._require_within_budget(
                self.fleet_spec.fleet_budget,
                after_fleet.usage,
                "fleet",
            )
            self.commit_operation(
                operation_id=f"operation-{uuid4().hex}",
                writes={
                    self.paths.fleet_state: _model_bytes(after_fleet),
                    self.provider_reservation_path(attempt_id): _model_bytes(
                        reservation
                    ),
                },
                event_type="usage_delta",
                payload={
                    "attempt_id": attempt_id,
                    **dict(trace_context or {}),
                    "usage_delta": {"model_calls": 1},
                },
            )
            _replace_model(fleet_state, after_fleet)
            return attempt_id

    def mark_provider_invoked(self, attempt_id: str) -> None:
        """Cross the durable provider invocation boundary."""
        reservation = self.load_provider_reservation(attempt_id)
        if reservation.state == "invoked":
            return
        invoked = reservation.model_copy(update={"state": "invoked"})
        _atomic_write_model(self.provider_reservation_path(attempt_id), invoked)
        self.append_event(
            "model_attempt_started",
            {
                "attempt_id": attempt_id,
                "provider_attempt": 1,
                **reservation.trace_context,
            },
            target_task_id=reservation.target_task_id,
            operation_id=attempt_id,
        )

    def settle_provider_attempt(
        self,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        attempt_id: str,
        *,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
        output_tokens: int = 0,
        failed: bool = False,
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Charge reported tokens and remove a definitive reservation."""
        reservation_path = self.provider_reservation_path(attempt_id)
        reservation = self.load_provider_reservation(attempt_id)
        self.apply_usage_delta(
            fleet_state,
            target_spec,
            target_state,
            {
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_input_tokens,
                "cache_write_tokens": cache_write_tokens,
                "output_tokens": output_tokens,
            },
            event_type=(
                "model_attempt_failed" if failed else "model_attempt_completed"
            ),
            deletions=[reservation_path],
            payload={
                "attempt_id": reservation.attempt_id,
                **reservation.trace_context,
                **dict(trace_payload or {}),
            },
            operation_id=f"settle-{attempt_id}",
            allow_budget_overage=True,
        )

    def settle_fleet_provider_attempt(
        self,
        fleet_state: FleetRunState,
        attempt_id: str,
        *,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
        output_tokens: int = 0,
        failed: bool = False,
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Charge tokens and settle one fleet-only provider reservation."""
        reservation_path = self.provider_reservation_path(attempt_id)
        reservation = self.load_provider_reservation(attempt_id)
        if reservation.target_task_id is not None:
            raise ValueError("fleet provider reservation belongs to a target")
        self.apply_fleet_usage_delta(
            fleet_state,
            {
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_input_tokens,
                "cache_write_tokens": cache_write_tokens,
                "output_tokens": output_tokens,
            },
            event_type=(
                "model_attempt_failed" if failed else "model_attempt_completed"
            ),
            deletions=[reservation_path],
            payload={
                "attempt_id": reservation.attempt_id,
                **reservation.trace_context,
                **dict(trace_payload or {}),
            },
            operation_id=f"settle-{attempt_id}",
            allow_budget_overage=True,
        )

    def provider_reservation_path(self, attempt_id: str) -> Path:
        require_path_segment(attempt_id, "attempt_id")
        return self.paths.provider_inflight / f"{attempt_id}.json"

    def load_provider_reservation(self, attempt_id: str) -> _ProviderReservation:
        return _ProviderReservation.model_validate_json(
            self.provider_reservation_path(attempt_id).read_bytes()
        )

    def provider_reservations(self) -> list[_ProviderReservation]:
        if not self.paths.provider_inflight.exists():
            return []
        return [
            _ProviderReservation.model_validate_json(path.read_bytes())
            for path in sorted(self.paths.provider_inflight.glob("*.json"))
        ]

    def reconcile_provider_reservations(self) -> list[str]:
        """Release prepared records and retain invoked ambiguity holds."""
        unresolved: list[str] = []
        for reservation in self.provider_reservations():
            path = self.provider_reservation_path(reservation.attempt_id)
            if reservation.state == "prepared":
                path.unlink(missing_ok=True)
                _fsync_directory(path.parent)
            else:
                unresolved.append(reservation.attempt_id)
        return unresolved

    def commit_artifact_mutation(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        after_state: TargetTaskState,
        *,
        writes: Mapping[Path, bytes],
        deletions: Iterable[Path] = (),
        action: str,
        artifact_id: str,
    ) -> None:
        """Commit candidate bytes and their current reference together."""
        with self.target_lock(target_spec.target_task_id):
            self._commit_artifact_mutation_locked(
                target_spec,
                target_state,
                after_state,
                writes=writes,
                deletions=deletions,
                action=action,
                artifact_id=artifact_id,
            )

    def _commit_artifact_mutation_locked(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        after_state: TargetTaskState,
        *,
        writes: Mapping[Path, bytes],
        deletions: Iterable[Path] = (),
        action: str,
        artifact_id: str,
    ) -> None:
        self._validate_target_identity(target_spec, target_state)
        self._require_worker_mutation_phase(target_state)
        operation_id = f"artifact-{uuid4().hex}"
        all_writes = dict(writes)
        all_writes[self.paths.target_state(target_spec)] = _model_bytes(after_state)
        self.commit_operation(
            operation_id=operation_id,
            writes=all_writes,
            deletions=deletions,
            event_type="artifact_mutated",
            payload={"action": action, "artifact_id": artifact_id},
            target_task_id=target_spec.target_task_id,
        )
        _replace_model(target_state, after_state)

    def commit_evidence(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        reference: EvidenceReference,
    ) -> None:
        """Commit an immutable evidence record and current state reference."""
        with self.target_lock(target_spec.target_task_id):
            self._commit_evidence_locked(target_spec, target_state, reference)

    def _commit_evidence_locked(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        reference: EvidenceReference,
    ) -> None:
        self._validate_target_identity(target_spec, target_state)
        self._require_worker_mutation_phase(target_state)
        after_state = target_state.model_copy(deep=True)
        if reference.evidence_id not in after_state.evidence_refs:
            after_state.evidence_refs = [
                *after_state.evidence_refs,
                reference.evidence_id,
            ]
        self.commit_operation(
            operation_id=f"evidence-{uuid4().hex}",
            writes={
                self.paths.evidence(target_spec, reference.evidence_id): _model_bytes(
                    reference
                ),
                self.paths.target_state(target_spec): _model_bytes(after_state),
            },
            event_type="evidence_recorded",
            payload={"evidence_id": reference.evidence_id},
            target_task_id=target_spec.target_task_id,
        )
        _replace_model(target_state, after_state)

    def commit_progress(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        after_state: TargetTaskState,
        opened: Iterable[OpenQuestion],
        resolved_question_ids: Iterable[str],
    ) -> None:
        """Commit question records and their target-state projection together."""
        with self.target_lock(target_spec.target_task_id):
            self._commit_progress_locked(
                target_spec,
                target_state,
                after_state,
                opened,
                resolved_question_ids,
            )

    def _commit_progress_locked(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        after_state: TargetTaskState,
        opened: Iterable[OpenQuestion],
        resolved_question_ids: Iterable[str],
    ) -> None:
        self._validate_target_identity(target_spec, target_state)
        self._require_worker_mutation_phase(target_state)
        opened_questions = list(opened)
        resolved = list(resolved_question_ids)
        writes = {self.paths.target_state(target_spec): _model_bytes(after_state)}
        for question in opened_questions:
            question_path = self.paths.question(target_spec, question.question_id)
            writes[question_path] = _model_bytes(question)
        event_type = "progress_updated"
        payload: dict[str, object] = {}
        if opened_questions:
            event_type = "question_opened"
            payload["question_ids"] = [item.question_id for item in opened_questions]
            payload["resolved_question_ids"] = resolved
        elif resolved:
            event_type = "question_resolved"
            payload["question_ids"] = resolved
        self.commit_operation(
            operation_id=f"progress-{uuid4().hex}",
            writes=writes,
            event_type=event_type,
            payload=payload,
            target_task_id=target_spec.target_task_id,
        )
        _replace_model(target_state, after_state)

    def load_target_specs(self) -> list[TargetTaskSpec]:
        """Load target specs in the bound fleet activation order."""
        return [
            TargetTaskSpec.model_validate_json(
                self.paths.target_spec(target_id).read_bytes()
            )
            for target_id in self.fleet_spec.target_ids
        ]

    def _apply_intent(
        self,
        transaction_root: Path,
        intent: _TransactionIntent,
    ) -> None:
        for staged_write in intent.writes:
            destination = self._validate_destination(Path(staged_write.destination))
            staged_path = transaction_root / "staged" / staged_write.staged_name
            content = staged_path.read_bytes()
            if _sha256(content) != staged_write.digest:
                raise ValueError("transaction staged content digest mismatch")
            if destination.exists() and destination.is_file():
                if _sha256(destination.read_bytes()) == staged_write.digest:
                    continue
            _atomic_write_bytes(destination, content)
        for deletion in intent.deletions:
            destination = self._validate_destination(Path(deletion))
            destination.unlink(missing_ok=True)
            if destination.parent.exists():
                _fsync_directory(destination.parent)
        self.append_event(
            intent.event.event_type,
            intent.event.payload,
            target_task_id=intent.event.target_task_id,
            operation_id=intent.event.operation_id,
            event_id=intent.event.event_id,
        )
        shutil.rmtree(transaction_root)
        if self.paths.transactions.exists():
            _fsync_directory(self.paths.transactions)

    def _validate_destination(self, path: Path) -> Path:
        resolved = path.resolve()
        if not (
            resolved == self.paths.run_root
            or resolved.is_relative_to(self.paths.run_root)
            or resolved == self.paths.output_root
            or resolved.is_relative_to(self.paths.output_root)
        ):
            raise ValueError("transaction destination escapes runtime authorities")
        return resolved

    def _validate_target_identity(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
    ) -> None:
        if (
            target_spec.fleet_run_id != self.fleet_spec.fleet_run_id
            or target_state.fleet_run_id != self.fleet_spec.fleet_run_id
            or target_state.target_task_id != target_spec.target_task_id
            or target_spec.source != self.fleet_spec.source
        ):
            raise ValueError("target authorities do not belong to this fleet")

    @staticmethod
    def _require_worker_mutation_phase(target_state: TargetTaskState) -> None:
        if target_state.phase is not TargetPhase.WORKING:
            raise ValueError("worker mutation requires a WORKING target")

    def _require_provider_capacity(
        self,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        reservations = self.provider_reservations()
        target_reservations = [
            item
            for item in reservations
            if item.target_task_id == target_spec.target_task_id
        ]
        checks = (
            (
                target_spec.budget.max_input_tokens,
                budgeted_input_tokens(target_state.usage),
                sum(item.input_token_reservation for item in target_reservations),
                input_tokens,
                "target input",
            ),
            (
                target_spec.budget.max_output_tokens,
                target_state.usage.output_tokens,
                sum(item.output_token_reservation for item in target_reservations),
                output_tokens,
                "target output",
            ),
            (
                self.fleet_spec.fleet_budget.max_input_tokens,
                budgeted_input_tokens(fleet_state.usage),
                sum(item.input_token_reservation for item in reservations),
                input_tokens,
                "fleet input",
            ),
            (
                self.fleet_spec.fleet_budget.max_output_tokens,
                fleet_state.usage.output_tokens,
                sum(item.output_token_reservation for item in reservations),
                output_tokens,
                "fleet output",
            ),
        )
        for limit, usage, held, requested, label in checks:
            if limit is not None and usage + held + requested > limit:
                raise ValueError(f"{label} token budget cannot reserve provider call")

    def _require_fleet_provider_capacity(
        self,
        fleet_state: FleetRunState,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        reservations = self.provider_reservations()
        checks = (
            (
                self.fleet_spec.fleet_budget.max_input_tokens,
                budgeted_input_tokens(fleet_state.usage),
                sum(item.input_token_reservation for item in reservations),
                input_tokens,
                "fleet input",
            ),
            (
                self.fleet_spec.fleet_budget.max_output_tokens,
                fleet_state.usage.output_tokens,
                sum(item.output_token_reservation for item in reservations),
                output_tokens,
                "fleet output",
            ),
        )
        for limit, usage, held, requested, label in checks:
            if limit is not None and usage + held + requested > limit:
                raise ValueError(f"{label} token budget cannot reserve provider call")

    @staticmethod
    def _require_within_budget(
        budget: ExecutionBudget,
        usage: ExecutionUsage,
        scope: str,
    ) -> None:
        limits = {
            "cycles": budget.max_cycles,
            "model_calls": budget.max_model_calls,
            "tool_calls": budget.max_tool_calls,
            "repair_cycles": budget.max_repair_cycles,
            "input_tokens": budget.max_input_tokens,
            "output_tokens": budget.max_output_tokens,
        }
        for field_name, limit in limits.items():
            amount = (
                budgeted_input_tokens(usage)
                if field_name == "input_tokens"
                else getattr(usage, field_name)
            )
            if limit is not None and amount > limit:
                raise ValueError(f"{scope} usage exceeds {field_name} budget")

    @staticmethod
    def _validate_event_payload(
        event_type: str,
        payload: Mapping[str, object],
    ) -> dict[str, JsonValue]:
        required = _EVENT_REQUIRED_KEYS.get(event_type)
        if required is None:
            raise ValueError(f"unsupported task event type: {event_type}")
        missing = required - payload.keys()
        if missing:
            raise ValueError(
                f"event payload is missing required field: {sorted(missing)[0]}"
            )
        normalized = _JSON_VALUE_ADAPTER.validate_python(dict(payload))
        if not isinstance(normalized, dict):
            raise ValueError("event payload must be an object")
        if len(orjson.dumps(normalized)) > 64 * 1024:
            raise ValueError("event payload exceeds the V0 trace size limit")
        return normalized


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(model: BaseModel) -> bytes:
    return orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)


def _model_bytes(model: BaseModel) -> bytes:
    return _canonical_json(model) + b"\n"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _atomic_write_model(path: Path, model: BaseModel) -> None:
    _atomic_write_bytes(path, _model_bytes(model))


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_create_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.link(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_model(current: BaseModel, replacement: BaseModel) -> None:
    for field_name in type(current).model_fields:
        setattr(current, field_name, getattr(replacement, field_name))


__all__ = ["FleetRunLock", "FleetRuntimeStore", "RuntimePaths"]
