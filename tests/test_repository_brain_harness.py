"""Repository Brain concurrent target-batch composition tests."""

import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import bridger.repository_brain.harness as harness
import bridger.repository_brain.publication as publication_module
from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.graph import GraphBuildResult
from bridger.contracts.memory.core import (
    ExecutionBudget,
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    SourceBinding,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.fleet_acceptance import AcceptedMemoryFleetResult
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.init_pipeline import InitMode, resolve_init_configuration
from bridger.llm.profiles import LLMProfile
from bridger.memory import WorkerCycleOutcome
from bridger.memory.errors import TargetReviewBudgetError


def test_v2_publication_is_typed_content_addressed_and_collision_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[Path] = []
    original_sync = publication_module._fsync_directory

    def sync(directory: Path) -> None:
        synced.append(directory)
        original_sync(directory)

    monkeypatch.setattr(publication_module, "_fsync_directory", sync)
    monkeypatch.setattr(publication_module, "validate_graph_snapshot", lambda *_: None)
    monkeypatch.setattr(
        publication_module,
        "validate_graph_enrichment",
        lambda *_: None,
    )
    graph = GraphBuildResult.model_construct(
        manifest=SimpleNamespace(
            repository_id="repository-1",
            revision="a" * 40,
            snapshot_id="snapshot-1",
        ),
        snapshot_root=tmp_path / "graphs" / "snapshot-1",
    )
    enrichment = GraphEnrichmentOverlay.model_construct(
        overlay_id="overlay-1",
        graph_snapshot_id="snapshot-1",
    )
    accepted = AcceptedMemoryFleetResult.model_construct(
        accepted_memory_fleet_result_id="accepted-fleet-1",
        fleet_run_id="fleet-1",
        source=SimpleNamespace(
            graph_snapshot_id="snapshot-1",
            enrichment_overlay_id="overlay-1",
        ),
        target_catalog_id="catalog-1",
        target_catalog_version="1",
        accepted_target_result_refs=["accepted-target-1"],
    )
    output_root = tmp_path / ".bridger" / "memory"
    runtime_root = tmp_path / ".bridger" / "runtime"

    manifest_path = publication_module.publish_repository_brain(
        graph,
        accepted,
        enrichment,
        output_root,
        runtime_root=runtime_root,
    )
    manifest = RepositoryBrainManifest.model_validate_json(manifest_path.read_bytes())

    assert manifest.schema_version == 2
    assert manifest.fleet_run_id == "fleet-1"
    assert manifest.memory_runtime_root == str(runtime_root)
    assert manifest.memory_output_root == str(output_root)
    assert manifest.accepted_target_result_refs == ["accepted-target-1"]
    assert (
        publication_module.publish_repository_brain(
            graph,
            accepted,
            enrichment,
            output_root,
            runtime_root=runtime_root,
        )
        == manifest_path
    )
    expected_id = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16]
    assert manifest_path.parent.name == expected_id
    assert synced == [manifest_path.parent.parent]
    assert not list(manifest_path.parent.parent.glob(f".{expected_id}-*"))

    manifest_path.write_text(json.dumps({"collision": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="identity collision"):
        publication_module.publish_repository_brain(
            graph,
            accepted,
            enrichment,
            output_root,
            runtime_root=runtime_root,
        )


def test_memory_harness_runs_all_targets_in_concurrent_batches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_ids = ("task-repository", "task-architecture", "task-testing")
    target_ids = ("repository", "architecture", "testing")
    target_specs = [
        SimpleNamespace(target_task_id=task_id, target_id=target_id)
        for task_id, target_id in zip(task_ids, target_ids, strict=True)
    ]
    target_states = [SimpleTargetState(task_id) for task_id in task_ids]
    states_by_task = {state.target_task_id: state for state in target_states}
    completion_states = [
        SimpleNamespace(target_task_id=task_id) for task_id in task_ids
    ]
    fleet_state = FleetRunState(
        fleet_run_id="fleet-1",
        target_task_ids=list(task_ids),
    )
    fleet_spec = SimpleNamespace(
        fleet_run_id="fleet-1",
        target_ids=list(target_ids),
        runtime_root=str(tmp_path / ".bridger" / "runtime"),
    )
    catalog = SimpleNamespace(
        targets=[SimpleNamespace(target_id=target_id) for target_id in target_ids]
    )
    definitions = [SimpleNamespace(target_id=target_id) for target_id in target_ids]
    store = _Store()
    client = _Client()
    bound_concurrency: list[int] = []
    calls: Counter[str] = Counter()
    first_batch_entered: set[str] = set()
    first_batch_complete = 0
    all_first_batch_entered = asyncio.Event()
    fleet_validation_calls: list[tuple[int, ...]] = []

    def bind(*_args: object, **kwargs: object) -> object:
        bound_concurrency.append(int(kwargs["max_concurrent_targets"]))
        return fleet_spec

    async def run_target_step(task_id: str, _runtime: object) -> WorkerCycleOutcome:
        nonlocal first_batch_complete
        calls[task_id] += 1
        if calls[task_id] == 1:
            first_batch_entered.add(task_id)
            if first_batch_entered == set(task_ids):
                all_first_batch_entered.set()
            await all_first_batch_entered.wait()
            states_by_task[task_id].phase = TargetPhase.SCHEDULED
            first_batch_complete += 1
            return WorkerCycleOutcome.CYCLE_YIELDED

        assert first_batch_complete == len(task_ids)
        states_by_task[task_id].phase = TargetPhase.ACCEPTED
        return WorkerCycleOutcome.FINALIZATION_REQUESTED

    def validate_fleet(_store: object, _state: object) -> object:
        fleet_validation_calls.append(tuple(calls[task_id] for task_id in task_ids))
        return SimpleNamespace(verdict=SimpleNamespace(value="pass"))

    async def reconcile_fleet(**_kwargs: object) -> object:
        return SimpleNamespace(verdict=harness.ReviewVerdict.PASS)

    monkeypatch.setattr(
        harness,
        "load_target_artifacts",
        lambda _root: (catalog, definitions),
    )
    monkeypatch.setattr(
        harness,
        "_profiles",
        lambda *_args: (
            SimpleNamespace(profile_id="worker"),
            SimpleNamespace(profile_id="reviewer"),
        ),
    )
    monkeypatch.setattr(harness, "bind_memory_run", bind)
    monkeypatch.setattr(
        harness,
        "initialize_fleet",
        lambda *_args: (
            fleet_state,
            target_specs,
            target_states,
            completion_states,
        ),
    )
    monkeypatch.setattr(harness, "initialize_persistence", lambda *_args: store)
    monkeypatch.setattr(harness, "RepositoryNavigator", lambda *_args: object())
    monkeypatch.setattr(harness, "build_graph_overview", lambda *_args: object())
    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())
    monkeypatch.setattr(
        harness,
        "create_llm_client_from_profile",
        lambda _profile: client,
    )
    monkeypatch.setattr(
        harness,
        "_runnable_target_task_ids",
        lambda *_args: [
            task_id
            for task_id in task_ids
            if states_by_task[task_id].phase is not TargetPhase.ACCEPTED
        ],
    )
    monkeypatch.setattr(harness, "_run_target_step", run_target_step)
    monkeypatch.setattr(harness, "validate_fleet", validate_fleet)
    monkeypatch.setattr(harness, "reconcile_fleet", reconcile_fleet)
    monkeypatch.setattr(harness, "accept_fleet", lambda *_args: object())
    expected = tmp_path / "repository-brain.json"
    monkeypatch.setattr(
        harness,
        "publish_repository_brain",
        lambda *_args, **_kwargs: expected,
    )
    monkeypatch.setattr(
        harness,
        "persist_token_usage_report",
        lambda *_args: tmp_path / "token-usage.json",
    )

    result = asyncio.run(
        asyncio.wait_for(
            harness.run_memory_harness(
                resolve_init_configuration(InitMode.TEST, repository_root=tmp_path),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                LLMProfile(name="test", provider="openai", model="test-model"),
                SimpleNamespace(),
            ),
            timeout=1,
        )
    )

    assert result.publication_path == expected
    assert bound_concurrency == [len(task_ids)]
    assert first_batch_entered == set(task_ids)
    assert calls == Counter({task_id: 2 for task_id in task_ids})
    assert fleet_validation_calls == [(2, 2, 2)]
    assert [event[0] for event in store.events] == ["fleet_execution_finished"]
    assert store.events[0][1]["fleet_phase"] == "initialized"
    assert client.closed is True
    assert store.closed is True


def test_fleet_review_repair_state_is_synchronized_before_scheduling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target_ids = ("repository", "architecture", "testing")
    task_ids = tuple(f"task-{target_id}" for target_id in target_ids)
    source = SourceBinding(
        repository_id="repository-1",
        repository_revision="a" * 40,
        graph_snapshot_id="snapshot-1",
    )
    budget = ExecutionBudget(
        max_cycles=20,
        max_model_calls=20,
        max_tool_calls=20,
        max_repair_cycles=3,
    )
    fleet_spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=source,
        target_catalog_id="catalog-1",
        target_catalog_version="1",
        target_ids=list(target_ids),
        runtime_profile_id="test-v1",
        default_worker_profile_id="worker",
        default_reviewer_profile_id="reviewer",
        default_permission_profile_id="permissions",
        fleet_budget=budget,
        default_target_budget=budget,
        max_concurrent_targets=len(target_ids),
        runtime_root=str(tmp_path / "runtime"),
        output_root=str(tmp_path / "memory"),
    )
    target_specs = [
        TargetTaskSpec(
            target_task_id=f"task-{target_id}",
            fleet_run_id=fleet_spec.fleet_run_id,
            target_id=target_id,
            target_contract_version="1",
            source=source,
            worker_profile_id="worker",
            reviewer_profile_id="reviewer",
            permission_profile_id="permissions",
            budget=budget,
            target_workspace=str(tmp_path / "memory" / target_id),
        )
        for target_id in target_ids
    ]
    target_states = [
        TargetTaskState(
            target_task_id=spec.target_task_id,
            fleet_run_id=fleet_spec.fleet_run_id,
        )
        for spec in target_specs
    ]
    states_by_task = {state.target_task_id: state for state in target_states}
    fleet_state = FleetRunState(
        fleet_run_id=fleet_spec.fleet_run_id,
        target_task_ids=list(task_ids),
    )
    catalog = SimpleNamespace(
        targets=[SimpleNamespace(target_id=target_id) for target_id in target_ids]
    )
    definitions = [SimpleNamespace(target_id=target_id) for target_id in target_ids]
    completion_states = [
        SimpleNamespace(target_task_id=task_id) for task_id in task_ids
    ]

    class PersistedStore(_Store):
        def __init__(self) -> None:
            super().__init__()
            self.scheduled_batches: list[list[str]] = []
            self.paths = SimpleNamespace(
                target_state=lambda spec: tmp_path / "states" / f"{spec.target_id}.json"
            )

        def persist_target_state(
            self, spec: TargetTaskSpec, state: TargetTaskState
        ) -> None:
            path = self.paths.target_state(spec)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(state.model_dump_json(), encoding="utf-8")

        def persist_scheduling_snapshot(
            self,
            _fleet_state: FleetRunState,
            specs: list[TargetTaskSpec],
            states: list[TargetTaskState],
            scheduled: list[str],
        ) -> None:
            self.scheduled_batches.append(list(scheduled))
            for spec, state in zip(specs, states, strict=True):
                self.persist_target_state(spec, state)

    store = PersistedStore()
    for spec, state in zip(target_specs, target_states, strict=True):
        store.persist_target_state(spec, state)

    calls: Counter[str] = Counter()
    repair_runs: list[str] = []
    fleet_validation_calls: list[tuple[int, ...]] = []
    fleet_reconciliation_calls: list[tuple[int, ...]] = []
    accepted_fleets: list[object] = []
    expected_publication = tmp_path / "repository-brain.json"
    client = _Client()

    async def run_worker_cycle(**kwargs: object) -> WorkerCycleOutcome:
        spec = cast(TargetTaskSpec, kwargs["target_spec"])
        state = cast(TargetTaskState, kwargs["target_state"])
        task_id = spec.target_task_id
        assert state is states_by_task[task_id]
        assert state.phase is TargetPhase.SCHEDULED
        calls[task_id] += 1
        if state.open_finding_refs:
            repair_runs.append(task_id)
        state.pending_finalization_request_ref = f"request-{calls[task_id]}"
        state.phase = TargetPhase.FINALIZING
        return WorkerCycleOutcome.FINALIZATION_REQUESTED

    def accept_target(
        _store: object, spec: TargetTaskSpec, state: TargetTaskState
    ) -> None:
        state.last_accepted_result_ref = f"accepted-{calls[spec.target_task_id]}"
        state.phase = TargetPhase.ACCEPTED
        state.open_finding_refs = []
        store.persist_target_state(spec, state)

    def validate_fleet(_store: object, _state: FleetRunState) -> object:
        fleet_validation_calls.append(tuple(calls[task_id] for task_id in task_ids))
        return SimpleNamespace(verdict=SimpleNamespace(value="pass"))

    async def reconcile_fleet(**_kwargs: object) -> object:
        fleet_reconciliation_calls.append(tuple(calls[task_id] for task_id in task_ids))
        if len(fleet_reconciliation_calls) == 1:
            architecture_spec = target_specs[1]
            architecture_state = TargetTaskState.model_validate_json(
                store.paths.target_state(architecture_spec).read_bytes()
            )
            architecture_state.open_finding_refs = [
                FindingRef(
                    finding_id="fleet-review-finding-1",
                    origin=FindingOrigin.FLEET_REVIEW,
                )
            ]
            architecture_state.phase = TargetPhase.REPAIR
            store.persist_target_state(architecture_spec, architecture_state)
            fleet_state.phase = FleetPhase.RUNNING
            return SimpleNamespace(verdict=harness.ReviewVerdict.NEEDS_WORK)
        return SimpleNamespace(verdict=harness.ReviewVerdict.PASS)

    monkeypatch.setattr(
        harness, "load_target_artifacts", lambda _root: (catalog, definitions)
    )
    monkeypatch.setattr(
        harness,
        "_profiles",
        lambda *_args: (
            SimpleNamespace(profile_id="worker"),
            SimpleNamespace(profile_id="reviewer"),
        ),
    )
    monkeypatch.setattr(
        harness, "bind_memory_run", lambda *_args, **_kwargs: fleet_spec
    )
    monkeypatch.setattr(
        harness,
        "initialize_fleet",
        lambda *_args: (fleet_state, target_specs, target_states, completion_states),
    )
    monkeypatch.setattr(harness, "initialize_persistence", lambda *_args: store)
    monkeypatch.setattr(harness, "RepositoryNavigator", lambda *_args: object())
    monkeypatch.setattr(harness, "build_graph_overview", lambda *_args: object())
    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())
    monkeypatch.setattr(
        harness, "create_llm_client_from_profile", lambda _profile: client
    )
    monkeypatch.setattr(harness, "_read_prompt", lambda _path: "prompt")
    monkeypatch.setattr(
        harness, "compile_worker_context", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(harness, "_load_evidence", lambda *_args: {})
    monkeypatch.setattr(harness, "_load_questions", lambda *_args: {})
    monkeypatch.setattr(harness, "run_worker_cycle", run_worker_cycle)
    monkeypatch.setattr(
        harness,
        "validate_target_candidate",
        lambda *_args: SimpleNamespace(verdict=SimpleNamespace(value="pass")),
    )
    monkeypatch.setattr(
        harness,
        "review_target",
        lambda **_kwargs: asyncio.sleep(
            0, result=SimpleNamespace(verdict=harness.ReviewVerdict.PASS)
        ),
    )
    monkeypatch.setattr(harness, "accept_target", accept_target)
    monkeypatch.setattr(harness, "validate_fleet", validate_fleet)
    monkeypatch.setattr(harness, "reconcile_fleet", reconcile_fleet)
    monkeypatch.setattr(
        harness,
        "accept_fleet",
        lambda *_args: accepted_fleets.append(object()) or accepted_fleets[-1],
    )
    monkeypatch.setattr(
        harness,
        "publish_repository_brain",
        lambda *_args, **_kwargs: expected_publication,
    )
    monkeypatch.setattr(
        harness,
        "persist_token_usage_report",
        lambda *_args: tmp_path / "token-usage.json",
    )

    result = asyncio.run(
        asyncio.wait_for(
            harness.run_memory_harness(
                resolve_init_configuration(InitMode.TEST, repository_root=tmp_path),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                LLMProfile(name="test", provider="openai", model="test-model"),
                SimpleNamespace(),
            ),
            timeout=1,
        )
    )

    assert result.publication_path == expected_publication
    assert store.scheduled_batches == [list(task_ids), ["task-architecture"]]
    assert calls == Counter(
        {"task-repository": 1, "task-architecture": 2, "task-testing": 1}
    )
    assert repair_runs == ["task-architecture"]
    assert fleet_validation_calls == [(1, 1, 1), (1, 2, 1)]
    assert fleet_reconciliation_calls == [(1, 1, 1), (1, 2, 1)]
    assert len(accepted_fleets) == 1
    assert all(state.phase is TargetPhase.ACCEPTED for state in target_states)
    assert client.closed is True
    assert store.closed is True


def test_target_batch_joins_fleet_budget_stop_with_sibling_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settled: list[str] = []
    release_siblings = asyncio.Event()

    async def run_target_step(task_id: str, _runtime: object) -> WorkerCycleOutcome:
        if task_id == "budget-stop":
            release_siblings.set()
            settled.append(task_id)
            return WorkerCycleOutcome.FLEET_BUDGET_STOP
        await release_siblings.wait()
        settled.append(task_id)
        return WorkerCycleOutcome.CYCLE_YIELDED

    monkeypatch.setattr(harness, "_run_target_step", run_target_step)

    outcomes = asyncio.run(
        harness._run_target_batch(
            ["budget-stop", "sibling-a", "sibling-b"],
            SimpleNamespace(),  # type: ignore[arg-type]
        )
    )

    assert set(settled) == {"budget-stop", "sibling-a", "sibling-b"}
    assert outcomes == [
        WorkerCycleOutcome.FLEET_BUDGET_STOP,
        WorkerCycleOutcome.CYCLE_YIELDED,
        WorkerCycleOutcome.CYCLE_YIELDED,
    ]


def test_target_batch_overlaps_shared_client_model_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_ids = ("task-architecture", "task-testing")
    client = _BarrierClient(set(task_ids))
    specs = {
        task_id: SimpleNamespace(
            target_task_id=task_id,
            target_id=task_id.removeprefix("task-"),
            target_contract_version="1",
        )
        for task_id in task_ids
    }
    runtime = SimpleNamespace(
        specs_by_task=specs,
        states_by_task={
            task_id: SimpleNamespace(phase=TargetPhase.SCHEDULED)
            for task_id in task_ids
        },
        completion_by_task={task_id: object() for task_id in task_ids},
        definitions_by_id={spec.target_id: object() for spec in specs.values()},
        fleet_spec=object(),
        fleet_state=object(),
        catalog=object(),
        worker_profile=SimpleNamespace(profile_id="worker"),
        reviewer_profile=SimpleNamespace(profile_id="reviewer"),
        permissions=object(),
        graph_overview=object(),
        store=object(),
        client=client,
        navigator=object(),
        coordinator=object(),
        configuration=SimpleNamespace(test_budgets=True),
    )

    async def run_worker(**kwargs: object) -> WorkerCycleOutcome:
        target_spec = kwargs["target_spec"]
        llm_client = kwargs["llm_client"]
        await llm_client.generate(  # type: ignore[union-attr]
            SimpleNamespace(target_task_id=target_spec.target_task_id)  # type: ignore[union-attr]
        )
        return WorkerCycleOutcome.CYCLE_YIELDED

    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())
    monkeypatch.setattr(
        harness,
        "compile_worker_context",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(harness, "_load_evidence", lambda *_args: {})
    monkeypatch.setattr(harness, "_load_questions", lambda *_args: {})
    monkeypatch.setattr(harness, "run_worker_cycle", run_worker)

    outcomes = asyncio.run(
        asyncio.wait_for(
            harness._run_target_batch(
                task_ids,
                runtime,  # type: ignore[arg-type]
            ),
            timeout=1,
        )
    )

    assert outcomes == [
        WorkerCycleOutcome.CYCLE_YIELDED,
        WorkerCycleOutcome.CYCLE_YIELDED,
    ]
    assert client.started == set(task_ids)
    assert client.maximum_in_flight == len(task_ids)


def test_target_batch_does_not_hide_unexpected_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sibling_cancelled = asyncio.Event()
    sibling_started = asyncio.Event()

    async def run_target_step(task_id: str, _runtime: object) -> WorkerCycleOutcome:
        if task_id == "broken":
            await sibling_started.wait()
            raise RuntimeError("unexpected target failure")
        sibling_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise
        return WorkerCycleOutcome.CYCLE_YIELDED

    monkeypatch.setattr(harness, "_run_target_step", run_target_step)

    with pytest.raises(ExceptionGroup) as error:
        asyncio.run(
            harness._run_target_batch(
                ["waiting", "broken"],
                SimpleNamespace(),  # type: ignore[arg-type]
            )
        )

    assert any(
        isinstance(exception, RuntimeError)
        and str(exception) == "unexpected target failure"
        for exception in error.value.exceptions
    )
    assert sibling_cancelled.is_set()


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("target", WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED),
        ("fleet", WorkerCycleOutcome.FLEET_BUDGET_STOP),
    ],
)
def test_target_step_reports_review_budget_stops_as_expected_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    expected: WorkerCycleOutcome,
) -> None:
    spec = SimpleNamespace(
        target_task_id="task-repository",
        target_id="repository",
        target_contract_version="1",
    )
    runtime = SimpleNamespace(
        specs_by_task={spec.target_task_id: spec},
        states_by_task={
            spec.target_task_id: SimpleNamespace(phase=TargetPhase.SCHEDULED)
        },
        completion_by_task={spec.target_task_id: object()},
        definitions_by_id={spec.target_id: object()},
        fleet_spec=object(),
        fleet_state=object(),
        catalog=object(),
        worker_profile=SimpleNamespace(profile_id="worker"),
        reviewer_profile=SimpleNamespace(profile_id="reviewer"),
        permissions=object(),
        graph_overview=object(),
        store=object(),
        client=object(),
        navigator=object(),
        coordinator=object(),
        configuration=SimpleNamespace(test_budgets=True),
    )

    async def run_worker(**kwargs: object) -> WorkerCycleOutcome:
        kwargs["target_state"].phase = TargetPhase.FINALIZING  # type: ignore[union-attr]
        return WorkerCycleOutcome.FINALIZATION_REQUESTED

    async def review(**_kwargs: object) -> object:
        raise TargetReviewBudgetError(scope)

    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())
    monkeypatch.setattr(
        harness, "compile_worker_context", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(harness, "_load_evidence", lambda *_args: {})
    monkeypatch.setattr(harness, "_load_questions", lambda *_args: {})
    monkeypatch.setattr(harness, "run_worker_cycle", run_worker)
    monkeypatch.setattr(
        harness,
        "validate_target_candidate",
        lambda *_args: SimpleNamespace(verdict=SimpleNamespace(value="pass")),
    )
    monkeypatch.setattr(harness, "review_target", review)

    outcome = asyncio.run(
        harness._run_target_step(
            spec.target_task_id,
            runtime,  # type: ignore[arg-type]
        )
    )

    assert outcome is expected


class SimpleTargetState:
    """Small mutable target-state double with the harness snapshot interface."""

    def __init__(self, target_task_id: str) -> None:
        self.target_task_id = target_task_id
        self.phase = TargetPhase.INITIALIZED

    def model_dump(self, *, mode: str) -> dict[str, str]:
        assert mode == "json"
        return {
            "target_task_id": self.target_task_id,
            "phase": self.phase.value,
        }


class _Client:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _BarrierClient:
    def __init__(self, expected_task_ids: set[str]) -> None:
        self.expected_task_ids = expected_task_ids
        self.started: set[str] = set()
        self.in_flight = 0
        self.maximum_in_flight = 0
        self.all_started = asyncio.Event()

    async def generate(self, request: object) -> object:
        task_id = request.target_task_id  # type: ignore[attr-defined]
        self.started.add(task_id)
        self.in_flight += 1
        self.maximum_in_flight = max(self.maximum_in_flight, self.in_flight)
        if self.started == self.expected_task_ids:
            self.all_started.set()
        await self.all_started.wait()
        self.in_flight -= 1
        return object()


class _Store:
    def __init__(self) -> None:
        self.closed = False
        self.events: list[tuple[str, dict[str, object]]] = []

    def exhaust_fleet_budget(self, fleet_state: FleetRunState) -> None:
        fleet_state.phase = FleetPhase.EXHAUSTED

    def append_event(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))

    def close(self) -> None:
        self.closed = True
