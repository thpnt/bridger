"""Focused Stage 11 fleet hard-validation and recovery tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_persistence import RuntimeFixture
from test_review import _client, _pass_result, _run_review
from test_validation import FakeNavigator

import bridger.memory.evaluation.fleet_validation as fleet_validation_module
from bridger.contracts.memory.core import (
    ActivationMode,
    CompletionItemState,
    CompletionObligationDefinition,
    CompletionStatus,
    ExecutionBudget,
    FindingOrigin,
    FleetPhase,
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
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.memory import (
    FleetValidationError,
    PersistenceRecoveryError,
    RecoveredFleet,
    TargetWorkspace,
    accept_target,
    handle_finalization_request,
    initialize_persistence,
    recover_fleet,
    resolve_fleet_validation_finding,
    schedule_runnable_targets,
    validate_fleet,
    validate_target_candidate,
)
from bridger.memory.persistence.store import persist_fleet_spec, persist_initialization

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
class FleetFixture:
    spec: MemoryFleetSpec
    fleet_state: FleetRunState
    catalog: MemoryTargetCatalog
    targets: list[RuntimeFixture]


def test_clean_exact_fleet_passes_and_duplicate_call_is_idempotent(
    tmp_path: Path,
) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": (
                "runtime.md",
                "# Runtime\n\nSee [persistence](../data-and-state/persistence.md).\n",
            ),
            "data-and-state": ("persistence.md", "# Persistence\n"),
        },
    )
    usage = fixture.fleet_state.usage.model_copy(deep=True)

    first = validate_fleet(fixture.targets[0].store, fixture.fleet_state)
    second = validate_fleet(fixture.targets[0].store, fixture.fleet_state)

    assert first.verdict is ValidationVerdict.PASS
    assert first.finding_refs == []
    assert first.accepted_target_result_refs == [
        target.target_state.last_accepted_result_ref for target in fixture.targets
    ]
    assert second == first
    assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    assert fixture.fleet_state.usage == usage
    report_root = fixture.targets[0].store.paths.run_root / "fleet-validation-reports"
    assert len(list(report_root.glob("*.json"))) == 1
    events = fixture.targets[0].store.recover_event_tail()
    assert (
        sum(event.event_type == "fleet_validation_completed" for event in events) == 1
    )


def test_admission_requires_running_fleet_with_every_target_accepted(
    tmp_path: Path,
) -> None:
    fixture = _fleet_runtime(tmp_path)

    with pytest.raises(FleetValidationError, match="RUNNING"):
        validate_fleet(fixture.targets[0].store, fixture.fleet_state)

    fixture.fleet_state.phase = FleetPhase.RUNNING
    _persist_fleet_state(fixture)
    with pytest.raises(FleetValidationError, match="every activated target"):
        validate_fleet(fixture.targets[0].store, fixture.fleet_state)

    assert not (
        fixture.targets[0].store.paths.run_root / "fleet-validation-reports"
    ).exists()


@pytest.mark.parametrize(
    ("destination", "expected_rule"),
    [
        ("../data-and-state/old-storage.md", "link.missing_destination"),
        ("../../../outside.md", "link.outside_fleet"),
    ],
)
def test_broken_cross_target_link_reopens_only_its_owner(
    tmp_path: Path,
    destination: str,
    expected_rule: str,
) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": (
                "runtime.md",
                f"See [old storage]({destination}).\n",
            ),
            "data-and-state": ("persistence.md", "# Persistence\n"),
        },
    )
    store = fixture.targets[0].store

    report = validate_fleet(store, fixture.fleet_state)
    states = _load_target_states(fixture)
    finding = resolve_fleet_validation_finding(
        store,
        report.finding_refs[0].finding_id,
    )

    assert report.verdict is ValidationVerdict.FAIL
    assert finding.rule_id == expected_rule
    assert finding.affected_target_task_ids == [
        fixture.targets[0].target_spec.target_task_id
    ]
    assert fixture.fleet_state.phase is FleetPhase.RUNNING
    assert states[0].phase is TargetPhase.REPAIR
    assert states[1].phase is TargetPhase.ACCEPTED
    assert states[1].last_accepted_result_ref == (
        fixture.targets[1].target_state.last_accepted_result_ref
    )
    assert [reference.origin for reference in states[0].open_finding_refs] == [
        FindingOrigin.FLEET_VALIDATION
    ]
    assert states[1].open_finding_refs == []
    events = store.recover_event_tail()
    transitions = [
        event.event_type for event in events if event.event_type.startswith("fleet_")
    ]
    assert transitions[-3:] == [
        "fleet_validation_started",
        "fleet_validation_completed",
        "fleet_repair_routed",
    ]


def test_reaccepted_target_changes_exact_candidate_and_replaces_findings(
    tmp_path: Path,
) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": (
                "runtime.md",
                "See [missing](../data-and-state/missing.md).\n",
            ),
            "data-and-state": ("persistence.md", "# Persistence\n"),
        },
    )
    store = fixture.targets[0].store
    failed = validate_fleet(store, fixture.fleet_state)
    old_refs = failed.accepted_target_result_refs
    states = _load_target_states(fixture)
    fixture.targets[0].target_state = states[0]
    fixture.targets[1].target_state = states[1]

    scheduled = schedule_runnable_targets(
        fixture.spec,
        fixture.fleet_state,
        [target.target_spec for target in fixture.targets],
        [target.target_state for target in fixture.targets],
        persistence=store,
    )
    assert scheduled == [fixture.targets[0].target_spec.target_task_id]
    repaired = fixture.targets[0]
    repaired.target_state.phase = TargetPhase.WORKING
    store.persist_target_state(
        repaired.target_spec,
        repaired.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.SCHEDULED.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
    TargetWorkspace(
        repaired.target_spec,
        repaired.target_state,
        store,
    ).write_target_artifact(
        "runtime.md",
        "See [persistence](../data-and-state/persistence.md).\n",
        expected_revision=1,
    )
    _accept_current_candidate(repaired)
    assert repaired.target_state.open_finding_refs

    passed = validate_fleet(store, fixture.fleet_state)
    final_states = _load_target_states(fixture)

    assert passed.verdict is ValidationVerdict.PASS
    assert passed.accepted_target_result_refs[0] != old_refs[0]
    assert passed.accepted_target_result_refs[1] == old_refs[1]
    assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    assert fixture.fleet_state.open_finding_refs == []
    assert all(
        reference.origin is not FindingOrigin.FLEET_VALIDATION
        for state in final_states
        for reference in state.open_finding_refs
    )
    assert store.paths.fleet_validation_report(
        failed.fleet_validation_report_id
    ).is_file()


def test_corrupt_accepted_provenance_is_runtime_failure_not_worker_finding(
    tmp_path: Path,
) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {"architecture": ("runtime.md", "# Runtime\n")},
    )
    target = fixture.targets[0]
    result_id = target.target_state.last_accepted_result_ref
    assert result_id is not None
    checkpoint_id = target.target_state.last_checkpoint_ref
    assert checkpoint_id is not None
    snapshot = (
        target.store.paths.checkpoint_root(target.target_spec, checkpoint_id)
        / "artifacts/runtime.md"
    )
    snapshot.write_text("corrupt", encoding="utf-8")

    with pytest.raises(PersistenceRecoveryError, match="checkpoint integrity"):
        validate_fleet(target.store, fixture.fleet_state)

    assert fixture.fleet_state.phase is FleetPhase.RUNNING
    assert not (target.store.paths.run_root / "fleet-validation-reports").exists()
    assert target.target_state.phase is TargetPhase.ACCEPTED


def test_recovery_completes_committed_failed_fleet_reopening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": (
                "runtime.md",
                "See [missing](../data-and-state/missing.md).\n",
            ),
            "data-and-state": ("persistence.md", "# Persistence\n"),
        },
    )

    def interrupt_routing(*_: object, **__: object) -> None:
        raise OSError("simulated crash before repair routing")

    monkeypatch.setattr(
        fleet_validation_module,
        "_route_failed_fleet",
        interrupt_routing,
    )
    with pytest.raises(PersistenceRecoveryError, match="coherent outcome"):
        validate_fleet(fixture.targets[0].store, fixture.fleet_state)
    persisted = FleetRunState.model_validate_json(
        fixture.targets[0].store.paths.fleet_state.read_bytes()
    )
    assert persisted.phase is FleetPhase.REPAIRING

    monkeypatch.undo()
    recovered = _recover(fixture)
    try:
        states = [
            recovered.target_states[target.target_spec.target_task_id]
            for target in fixture.targets
        ]
        assert recovered.fleet_state.phase is FleetPhase.RUNNING
        assert states[0].phase is TargetPhase.REPAIR
        assert states[1].phase is TargetPhase.ACCEPTED
        events = recovered.store.recover_event_tail()
        assert (
            sum(event.event_type == "fleet_validation_completed" for event in events)
            == 1
        )
        assert sum(event.event_type == "fleet_repair_routed" for event in events) == 1
    finally:
        recovered.close()


def test_recovery_reruns_incomplete_validating_fleet(tmp_path: Path) -> None:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": ("runtime.md", "# Runtime\n"),
            "data-and-state": ("persistence.md", "# Persistence\n"),
        },
    )
    original = fleet_validation_module._build_artifact_index

    def interrupt_validation(*_: object, **__: object) -> None:
        raise OSError("simulated crash during deterministic validation")

    fleet_validation_module._build_artifact_index = interrupt_validation
    try:
        with pytest.raises(PersistenceRecoveryError, match="coherent outcome"):
            validate_fleet(fixture.targets[0].store, fixture.fleet_state)
    finally:
        fleet_validation_module._build_artifact_index = original

    persisted = FleetRunState.model_validate_json(
        fixture.targets[0].store.paths.fleet_state.read_bytes()
    )
    assert persisted.phase is FleetPhase.VALIDATING

    recovered = _recover(fixture)
    try:
        assert recovered.fleet_state.phase is FleetPhase.REVIEWING
        events = recovered.store.recover_event_tail()
        assert (
            sum(event.event_type == "fleet_validation_completed" for event in events)
            == 1
        )
    finally:
        recovered.close()


def _fleet_runtime(tmp_path: Path, target_ids: list[str] | None = None) -> FleetFixture:
    activated = target_ids or ["architecture", "data-and-state"]
    runtime_root = (tmp_path / "runtime").resolve()
    output_root = (tmp_path / "output").resolve()
    spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id="memory-targets",
        target_catalog_version="1",
        target_ids=activated,
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=_BUDGET,
        default_target_budget=_BUDGET,
        max_concurrent_targets=len(activated),
        runtime_root=str(runtime_root),
        output_root=str(output_root),
    )
    target_specs: list[TargetTaskSpec] = []
    target_states: list[TargetTaskState] = []
    completion_states: list[TargetCompletionState] = []
    definitions: list[TargetDefinition] = []
    entries: list[TargetCatalogEntry] = []
    for target_id in activated:
        target_spec = TargetTaskSpec(
            target_task_id=uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"bridger-memory-target:{spec.fleet_run_id}:{target_id}",
            ).hex,
            fleet_run_id=spec.fleet_run_id,
            target_id=target_id,
            target_contract_version="1",
            source=_SOURCE,
            worker_profile_id="worker-v1",
            reviewer_profile_id="reviewer-v1",
            permission_profile_id="permissions-v1",
            budget=_BUDGET,
            target_workspace=str(output_root / target_id),
        )
        obligation_id = f"describe-{target_id}"
        target_specs.append(target_spec)
        target_states.append(
            TargetTaskState(
                target_task_id=target_spec.target_task_id,
                fleet_run_id=spec.fleet_run_id,
            )
        )
        completion_states.append(
            TargetCompletionState(
                target_task_id=target_spec.target_task_id,
                items=[CompletionItemState(obligation_id=obligation_id)],
            )
        )
        definitions.append(
            TargetDefinition(
                schema_version=1,
                target_id=target_id,
                target_contract_version="1",
                activation=TargetActivation(mode=ActivationMode.ALWAYS),
                depends_on=[],
                canonical_question=f"What belongs to {target_id}?",
                purpose=f"Describe {target_id}.",
                expected_abstraction="Repository-level knowledge.",
                always_relevant_scope=[],
                conditional_scope=[],
                exclusions=[],
                boundary_guidance=[],
                investigation_expectations=[],
                evidence_expectations=[],
                completion_obligations=[
                    CompletionObligationDefinition(
                        obligation_id=obligation_id,
                        description=f"Describe {target_id}.",
                        applicability=ObligationApplicability.ALWAYS,
                    )
                ],
                output_quality_expectations=[],
            )
        )
        entries.append(
            TargetCatalogEntry(
                target_id=target_id,
                target_contract_version="1",
            )
        )
    catalog = MemoryTargetCatalog(
        schema_version=1,
        catalog_id=spec.target_catalog_id,
        catalog_version=spec.target_catalog_version,
        targets=entries,
        cross_target_ownership_rules=[],
    )
    fleet_state = FleetRunState(
        fleet_run_id=spec.fleet_run_id,
        target_task_ids=[target_spec.target_task_id for target_spec in target_specs],
    )
    persist_fleet_spec(spec)
    persist_initialization(
        spec,
        fleet_state,
        target_specs,
        target_states,
        completion_states,
        [Path(target_spec.target_workspace) for target_spec in target_specs],
    )
    store = initialize_persistence(
        spec,
        fleet_state,
        target_specs,
        target_states,
        completion_states,
    )
    targets = [
        RuntimeFixture(
            spec=spec,
            fleet_state=fleet_state,
            target_spec=target_spec,
            target_state=target_state,
            completion_state=completion_state,
            catalog=catalog,
            definition=definition,
            store=store,
        )
        for target_spec, target_state, completion_state, definition in zip(
            target_specs,
            target_states,
            completion_states,
            definitions,
            strict=True,
        )
    ]
    return FleetFixture(
        spec=spec,
        fleet_state=fleet_state,
        catalog=catalog,
        targets=targets,
    )


def _accepted_fleet(
    tmp_path: Path,
    artifacts: dict[str, tuple[str, str]],
) -> FleetFixture:
    fixture = _fleet_runtime(tmp_path, list(artifacts))
    scheduled = schedule_runnable_targets(
        fixture.spec,
        fixture.fleet_state,
        [target.target_spec for target in fixture.targets],
        [target.target_state for target in fixture.targets],
        persistence=fixture.targets[0].store,
    )
    assert scheduled == [
        target.target_spec.target_task_id for target in fixture.targets
    ]
    for target in fixture.targets:
        target.target_state.phase = TargetPhase.WORKING
        target.store.persist_target_state(
            target.target_spec,
            target.target_state,
            event_type="phase_transition",
            payload={
                "from_phase": TargetPhase.SCHEDULED.value,
                "to_phase": TargetPhase.WORKING.value,
            },
        )
        relative_path, content = artifacts[target.target_spec.target_id]
        TargetWorkspace(
            target.target_spec,
            target.target_state,
            target.store,
        ).write_target_artifact(relative_path, content)
        _resolve_completion(target)
        _accept_current_candidate(target)
    return fixture


def _resolve_completion(target: RuntimeFixture) -> None:
    item = target.completion_state.items[0]
    item.resolution_note = "Mechanically resolved for validation."
    item.status = CompletionStatus.UNKNOWN
    target.store.persist_completion_state(
        target.target_spec,
        target.target_state,
        target.completion_state,
        obligation_id=item.obligation_id,
    )


def _accept_current_candidate(target: RuntimeFixture) -> None:
    handle_finalization_request(
        target.store,
        target.target_spec,
        target.target_state,
        target.completion_state,
        {},
        {},
    )
    report = validate_target_candidate(
        target.store,
        target.target_spec,
        target.target_state,
        target.definition,
        FakeNavigator(target),  # type: ignore[arg-type]
    )
    assert report.verdict is ValidationVerdict.PASS
    verdict = _run_review(target, _client(_pass_result()))
    assert verdict.verdict.value == "pass"
    accept_target(target.store, target.target_spec, target.target_state)


def _load_target_states(fixture: FleetFixture) -> list[TargetTaskState]:
    return [
        TargetTaskState.model_validate_json(
            target.store.paths.target_state(target.target_spec).read_bytes()
        )
        for target in fixture.targets
    ]


def _persist_fleet_state(fixture: FleetFixture) -> None:
    fixture.targets[0].store.commit_operation(
        operation_id="test-set-fleet-running",
        writes={
            fixture.targets[0].store.paths.fleet_state: (
                fixture.fleet_state.model_dump_json().encode() + b"\n"
            )
        },
        event_type="phase_transition",
        payload={
            "from_phase": FleetPhase.INITIALIZED.value,
            "to_phase": FleetPhase.RUNNING.value,
        },
    )


def _recover(fixture: FleetFixture) -> RecoveredFleet:
    fixture.targets[0].store.close()
    return recover_fleet(
        Path(fixture.spec.runtime_root),
        fixture.spec.fleet_run_id,
        source=fixture.spec.source,
        catalog=fixture.catalog,
        definitions=[target.definition for target in fixture.targets],
        runtime_profile_id=fixture.spec.runtime_profile_id,
        worker_profile_ids={
            target.target_spec.worker_profile_id for target in fixture.targets
        },
        reviewer_profile_ids={
            target.target_spec.reviewer_profile_id for target in fixture.targets
        },
        permission_profile_ids={
            target.target_spec.permission_profile_id for target in fixture.targets
        },
    )
