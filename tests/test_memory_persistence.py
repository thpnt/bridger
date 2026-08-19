"""Correctness-critical Stage 5 persistence and recovery tests."""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from artifacts.writer import write_artifact
from llm.errors import LLMConnectionError
from memory import (
    FinalizationRequestError,
    FleetRuntimeStore,
    PersistenceRecoveryError,
    RecoveredFleet,
    TargetWorkspace,
    create_checkpoint,
    handle_finalization_request,
    initialize_persistence,
    record_runtime_error,
    recover_fleet,
    run_provider_with_retry,
    validate_checkpoint,
)
from memory.persistence import persist_fleet_spec, persist_initialization
from models.memory import (
    ActivationMode,
    CompletionItemState,
    CompletionObligationDefinition,
    ExecutionBudget,
    FleetRunState,
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
from models.persistence import TaskCheckpoint

_SOURCE = SourceBinding(
    repository_id="repository-1",
    repository_revision="a" * 40,
    graph_snapshot_id="snapshot-1",
)
_BUDGET = ExecutionBudget(
    max_cycles=100,
    max_model_calls=100,
    max_tool_calls=100,
    max_repair_cycles=20,
    max_input_tokens=100_000,
    max_output_tokens=100_000,
)


@dataclass
class RuntimeFixture:
    spec: MemoryFleetSpec
    fleet_state: FleetRunState
    target_spec: TargetTaskSpec
    target_state: TargetTaskState
    completion_state: TargetCompletionState
    catalog: MemoryTargetCatalog
    definition: TargetDefinition
    store: FleetRuntimeStore


def test_trace_sequence_and_torn_tail_recovery(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    before = fixture.store.recover_event_tail()
    with fixture.store.paths.events.open("ab") as stream:
        stream.write(b'{"torn":')

    recovered = fixture.store.recover_event_tail()
    appended = fixture.store.append_event("progress_updated", {})

    assert recovered == before
    assert appended.sequence == len(before) + 1
    assert fixture.store.paths.events.read_bytes().endswith(b"\n")


def test_run_lock_prevents_second_process_owner(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    with pytest.raises(RuntimeError, match="already owned"):
        fixture.store.run_lock().acquire()
    fixture.store.close()
    second = fixture.store.run_lock().acquire()
    second.__exit__(None, None, None)


def test_provider_retry_is_bounded_and_uses_locked_backoff() -> None:
    attempts: list[int] = []
    retries: list[tuple[int, float]] = []
    sleeps: list[float] = []

    async def scenario() -> str:
        outcomes = [
            LLMConnectionError("first", retryable=True),
            LLMConnectionError("second", retryable=True),
        ]

        async def operation() -> str:
            if outcomes:
                raise outcomes.pop(0)
            return "ok"

        async def before_attempt(attempt: int) -> None:
            attempts.append(attempt)

        async def on_retry(
            next_attempt: int,
            delay: float,
            _: LLMConnectionError,
        ) -> None:
            retries.append((next_attempt, delay))

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        return await run_provider_with_retry(
            operation,
            before_attempt=before_attempt,
            on_retry=on_retry,
            sleep=sleep,
        )

    assert asyncio.run(scenario()) == "ok"
    assert attempts == [1, 2, 3]
    assert retries == [(2, 1.0), (3, 2.0)]
    assert sleeps == [1.0, 2.0]


def test_committed_usage_transaction_recovers_forward_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime(tmp_path)
    original_apply = fixture.store._apply_intent

    def interrupt_after_commit(*_: object) -> None:
        raise OSError("simulated crash after intent")

    monkeypatch.setattr(fixture.store, "_apply_intent", interrupt_after_commit)
    with pytest.raises(OSError, match="simulated crash"):
        fixture.store.apply_usage_delta(
            fixture.fleet_state,
            fixture.target_spec,
            fixture.target_state,
            {"tool_calls": 1},
            operation_id="operation-crash-test",
        )
    assert fixture.target_state.usage.tool_calls == 0

    monkeypatch.setattr(fixture.store, "_apply_intent", original_apply)
    fixture.store.recover_transactions()
    fixture.store.recover_transactions()

    target = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )
    fleet = FleetRunState.model_validate_json(
        fixture.store.paths.fleet_state.read_bytes()
    )
    events = fixture.store.recover_event_tail()
    assert target.usage.tool_calls == 1
    assert fleet.usage.tool_calls == 1
    assert sum(event.operation_id == "operation-crash-test" for event in events) == 1


def test_artifact_bytes_reference_and_checkpoint_restore_are_exact(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    fixture.target_state.phase = TargetPhase.WORKING
    workspace = TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    )
    reference = workspace.write_target_artifact("architecture.md", "known good")
    checkpoint = create_checkpoint(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    fixture.target_state.phase = TargetPhase.SCHEDULED
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.WORKING.value,
            "to_phase": TargetPhase.SCHEDULED.value,
        },
    )
    artifact_path = Path(fixture.target_spec.target_workspace) / "architecture.md"
    artifact_path.write_text("corrupt", encoding="utf-8")

    recovered = _recover(fixture)
    try:
        assert artifact_path.read_text(encoding="utf-8") == "known good"
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.artifact_refs == [reference]
        assert state.last_checkpoint_ref == checkpoint.checkpoint_id
    finally:
        recovered.close()


def test_finalization_persists_exact_fresh_candidate_and_is_idempotent(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    workspace = TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    )
    artifact = workspace.write_target_artifact("architecture.md", "final candidate")
    previous_checkpoint = fixture.target_state.last_checkpoint_ref
    usage_before = fixture.target_state.usage.model_copy(deep=True)
    fleet_usage_before = fixture.fleet_state.usage.model_copy(deep=True)

    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )

    assert request.candidate_checkpoint_ref != previous_checkpoint
    assert fixture.target_state.phase is TargetPhase.FINALIZING
    assert fixture.target_state.pending_finalization_request_ref == (
        request.finalization_request_id
    )
    assert fixture.target_state.last_checkpoint_ref == request.candidate_checkpoint_ref
    assert fixture.target_state.usage == usage_before
    assert fixture.fleet_state.usage == fleet_usage_before
    checkpoint = validate_checkpoint(
        fixture.store,
        fixture.target_spec,
        request.candidate_checkpoint_ref,
    )
    assert checkpoint.task_state.phase is TargetPhase.WORKING
    assert checkpoint.task_state.artifact_refs == [artifact]
    snapshot = (
        fixture.store.paths.checkpoint_root(
            fixture.target_spec,
            request.candidate_checkpoint_ref,
        )
        / "artifacts/architecture.md"
    )
    assert snapshot.read_text(encoding="utf-8") == "final candidate"
    assert fixture.store.paths.finalization_request(
        fixture.target_spec,
        request.finalization_request_id,
    ).is_file()
    event = fixture.store.recover_event_tail()[-1]
    assert event.event_type == "finalization_requested"
    assert event.payload["candidate_checkpoint_ref"] == checkpoint.checkpoint_id

    with pytest.raises(ValueError, match="WORKING"):
        workspace.write_target_artifact(
            "architecture.md",
            "too late",
            expected_revision=artifact.revision,
        )

    checkpoint_count = len(
        list(
            (
                fixture.store.paths.target_root(fixture.target_spec) / "checkpoints"
            ).iterdir()
        )
    )
    repeated = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    assert repeated == request
    assert (
        len(
            list(
                (
                    fixture.store.paths.target_root(fixture.target_spec) / "checkpoints"
                ).iterdir()
            )
        )
        == checkpoint_count
    )


def test_recovered_finalizing_target_resolves_request_without_worker_reset(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )

    recovered = _recover(fixture)
    try:
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.phase is TargetPhase.FINALIZING
        assert recovered.active_target_task_ids == (fixture.target_spec.target_task_id,)
        repeated = handle_finalization_request(
            recovered.store,
            fixture.target_spec,
            state,
            recovered.completion_states[fixture.target_spec.target_task_id],
            {},
            {},
        )
        assert repeated == request
    finally:
        recovered.close()


def test_finalization_rejects_invalid_lifecycle_call(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)

    with pytest.raises(FinalizationRequestError, match="WORKING"):
        handle_finalization_request(
            fixture.store,
            fixture.target_spec,
            fixture.target_state,
            fixture.completion_state,
            {},
            {},
        )


def test_committed_finalization_transaction_recovers_forward_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    original_apply = fixture.store._apply_intent

    def interrupt_after_commit(*_: object) -> None:
        raise OSError("simulated finalization crash")

    monkeypatch.setattr(fixture.store, "_apply_intent", interrupt_after_commit)
    with pytest.raises(FinalizationRequestError, match="could not persist"):
        handle_finalization_request(
            fixture.store,
            fixture.target_spec,
            fixture.target_state,
            fixture.completion_state,
            {},
            {},
        )
    assert fixture.target_state.phase is TargetPhase.WORKING

    monkeypatch.setattr(fixture.store, "_apply_intent", original_apply)
    fixture.store.recover_transactions()
    fixture.store.recover_transactions()
    recovered_state = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        recovered_state,
        fixture.completion_state,
        {},
        {},
    )

    assert recovered_state.phase is TargetPhase.FINALIZING
    assert recovered_state.pending_finalization_request_ref == (
        request.finalization_request_id
    )
    requests_root = fixture.store.paths.finalization_request(
        fixture.target_spec,
        request.finalization_request_id,
    ).parent
    assert len(list(requests_root.glob("*.json"))) == 1
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "finalization_requested" for event in events) == 1


def test_recovery_rejects_source_binding_mismatch(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    mismatched = fixture.spec.source.model_copy(
        update={"graph_snapshot_id": "another-snapshot"}
    )

    with pytest.raises(PersistenceRecoveryError, match="recovery validation"):
        _recover(fixture, source=mismatched)


def test_checkpoint_tampering_is_rejected(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    checkpoint_id = fixture.target_state.last_checkpoint_ref
    assert checkpoint_id is not None
    checkpoint_path = (
        fixture.store.paths.checkpoint_root(fixture.target_spec, checkpoint_id)
        / "checkpoint.json"
    )
    checkpoint = TaskCheckpoint.model_validate_json(checkpoint_path.read_bytes())
    write_artifact(
        checkpoint_path,
        checkpoint.model_copy(update={"trace_sequence": checkpoint.trace_sequence + 1}),
    )

    with pytest.raises(PersistenceRecoveryError, match="checkpoint integrity"):
        validate_checkpoint(fixture.store, fixture.target_spec, checkpoint_id)


def test_runtime_error_record_and_reference_recover_together(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    record = record_runtime_error(
        fixture.store,
        fixture.fleet_state,
        category="runtime",
        operation="worker-cycle",
        message="trajectory interrupted",
        retryable=True,
        target_spec=fixture.target_spec,
        target_state=fixture.target_state,
        phase=TargetPhase.WORKING.value,
    )

    recovered = _recover(fixture)
    try:
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.last_error_ref == record.error_id
        assert (fixture.store.paths.errors / f"{record.error_id}.json").is_file()
    finally:
        recovered.close()


def test_working_recovery_preserves_usage_and_bypasses_admission(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    fixture.store.prepare_provider_attempt(
        fixture.fleet_state,
        fixture.target_spec,
        fixture.target_state,
        input_tokens=100,
        output_tokens=100,
        cycle_start=True,
    )

    recovered = _recover(fixture)
    try:
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert recovered.active_target_task_ids == (fixture.target_spec.target_task_id,)
        assert state.phase is TargetPhase.SCHEDULED
        assert state.usage.cycles == 1
        assert state.usage.model_calls == 1
        assert recovered.fleet_state.usage == state.usage
        assert recovered.unresolved_provider_attempt_ids == ()
    finally:
        recovered.close()


def test_invoked_provider_ambiguity_retains_conservative_hold(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    attempt_id = fixture.store.prepare_provider_attempt(
        fixture.fleet_state,
        fixture.target_spec,
        fixture.target_state,
        input_tokens=100,
        output_tokens=100,
        cycle_start=True,
    )
    fixture.store.mark_provider_invoked(attempt_id)

    recovered = _recover(fixture)
    try:
        assert recovered.unresolved_provider_attempt_ids == (attempt_id,)
        assert recovered.store.provider_reservation_path(attempt_id).is_file()
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.usage.model_calls == 1
        assert state.phase is TargetPhase.SCHEDULED
    finally:
        recovered.close()


def test_concurrent_shared_usage_mutations_cannot_drift(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)

    def charge(_: int) -> None:
        fixture.store.apply_usage_delta(
            fixture.fleet_state,
            fixture.target_spec,
            fixture.target_state,
            {"tool_calls": 1},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(charge, range(40)))

    target = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )
    fleet = FleetRunState.model_validate_json(
        fixture.store.paths.fleet_state.read_bytes()
    )
    assert target.usage.tool_calls == 40
    assert fleet.usage.tool_calls == 40


def test_recovery_rejects_target_fleet_usage_drift(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    drifted = fixture.fleet_state.model_copy(deep=True)
    drifted.usage.tool_calls = 1
    write_artifact(fixture.store.paths.fleet_state, drifted)

    with pytest.raises(PersistenceRecoveryError, match="recovery validation"):
        _recover(fixture)


def _runtime(tmp_path: Path) -> RuntimeFixture:
    runtime_root = (tmp_path / "runtime").resolve()
    output_root = (tmp_path / "output").resolve()
    spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id="memory-targets",
        target_catalog_version="1",
        target_ids=["architecture"],
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=_BUDGET,
        default_target_budget=_BUDGET,
        max_concurrent_targets=1,
        runtime_root=str(runtime_root),
        output_root=str(output_root),
    )
    target_spec = TargetTaskSpec(
        target_task_id=uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"bridger-memory-target:{spec.fleet_run_id}:architecture",
        ).hex,
        fleet_run_id=spec.fleet_run_id,
        target_id="architecture",
        target_contract_version="1",
        source=_SOURCE,
        worker_profile_id="worker-v1",
        reviewer_profile_id="reviewer-v1",
        permission_profile_id="permissions-v1",
        budget=_BUDGET,
        target_workspace=str(output_root / "architecture"),
    )
    target_state = TargetTaskState(
        target_task_id=target_spec.target_task_id,
        fleet_run_id=spec.fleet_run_id,
    )
    completion_state = TargetCompletionState(
        target_task_id=target_spec.target_task_id,
        items=[CompletionItemState(obligation_id="describe-architecture")],
    )
    fleet_state = FleetRunState(
        fleet_run_id=spec.fleet_run_id,
        target_task_ids=[target_spec.target_task_id],
    )
    definition = TargetDefinition(
        schema_version=1,
        target_id=target_spec.target_id,
        target_contract_version=target_spec.target_contract_version,
        activation=TargetActivation(mode=ActivationMode.ALWAYS),
        depends_on=[],
        canonical_question="How is the repository structured?",
        purpose="Describe architecture.",
        expected_abstraction="Repository-level architecture.",
        always_relevant_scope=[],
        conditional_scope=[],
        exclusions=[],
        boundary_guidance=[],
        investigation_expectations=[],
        evidence_expectations=[],
        completion_obligations=[
            CompletionObligationDefinition(
                obligation_id="describe-architecture",
                description="Describe the architecture.",
                applicability=ObligationApplicability.ALWAYS,
            )
        ],
        output_quality_expectations=[],
    )
    catalog = MemoryTargetCatalog(
        schema_version=1,
        catalog_id=spec.target_catalog_id,
        catalog_version=spec.target_catalog_version,
        targets=[
            TargetCatalogEntry(
                target_id=target_spec.target_id,
                target_contract_version=target_spec.target_contract_version,
            )
        ],
        cross_target_ownership_rules=[],
    )
    persist_fleet_spec(spec)
    persist_initialization(
        spec,
        fleet_state,
        [target_spec],
        [target_state],
        [completion_state],
        [Path(target_spec.target_workspace)],
    )
    store = initialize_persistence(
        spec,
        fleet_state,
        [target_spec],
        [target_state],
        [completion_state],
    )
    return RuntimeFixture(
        spec=spec,
        fleet_state=fleet_state,
        target_spec=target_spec,
        target_state=target_state,
        completion_state=completion_state,
        catalog=catalog,
        definition=definition,
        store=store,
    )


def _recover(
    fixture: RuntimeFixture,
    *,
    source: SourceBinding | None = None,
) -> RecoveredFleet:
    fixture.store.close()
    return recover_fleet(
        Path(fixture.spec.runtime_root),
        fixture.spec.fleet_run_id,
        source=source or fixture.spec.source,
        catalog=fixture.catalog,
        definitions=[fixture.definition],
        runtime_profile_id=fixture.spec.runtime_profile_id,
        worker_profile_ids={fixture.target_spec.worker_profile_id},
        reviewer_profile_ids={fixture.target_spec.reviewer_profile_id},
        permission_profile_ids={fixture.target_spec.permission_profile_id},
    )


def _enter_working(fixture: RuntimeFixture) -> None:
    fixture.target_state.phase = TargetPhase.WORKING
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.INITIALIZED.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
