"""Repository Brain concurrent target-batch composition tests."""

import asyncio
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

import bridger.repository_brain.harness as harness
from bridger.contracts.memory.core import FleetPhase, FleetRunState, TargetPhase
from bridger.init_pipeline import InitMode, resolve_init_configuration
from bridger.llm.profiles import LLMProfile
from bridger.memory import WorkerCycleOutcome
from bridger.memory.errors import TargetReviewBudgetError


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
    fleet_spec = SimpleNamespace(fleet_run_id="fleet-1")
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
        lambda *_args: expected,
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

    assert result == expected
    assert bound_concurrency == [len(task_ids)]
    assert first_batch_entered == set(task_ids)
    assert calls == Counter({task_id: 2 for task_id in task_ids})
    assert fleet_validation_calls == [(2, 2, 2)]
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
        states_by_task={task_id: object() for task_id in task_ids},
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
        states_by_task={spec.target_task_id: object()},
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

    async def run_worker(**_kwargs: object) -> WorkerCycleOutcome:
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

    def exhaust_fleet_budget(self, fleet_state: FleetRunState) -> None:
        fleet_state.phase = FleetPhase.EXHAUSTED

    def close(self) -> None:
        self.closed = True
