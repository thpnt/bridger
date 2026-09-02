"""Repository Brain recovery composition regressions."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import bridger.init_pipeline as init_pipeline
import bridger.repository_brain.harness as harness
from bridger.contracts.memory.core import (
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    SourceBinding,
    TargetPhase,
)
from bridger.contracts.memory.review import ReviewVerdict
from bridger.contracts.repository import RepositoryContext
from bridger.init_pipeline import (
    InitMode,
    InitRunConfiguration,
    RepositoryBrainBuildError,
    resolve_init_configuration,
)
from bridger.llm.profiles import LLMProfile
from bridger.memory import WorkerCycleOutcome


def test_discovers_one_compatible_incomplete_fleet(tmp_path: Path) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    compatible = _fleet_spec(configuration, context, "compatible")
    incompatible = _fleet_spec(
        configuration,
        context.model_copy(update={"revision": "b" * 40}),
        "incompatible",
    )
    _persist_discovery_state(compatible, FleetPhase.RUNNING)
    _persist_discovery_state(incompatible, FleetPhase.RUNNING)

    selected = harness.discover_resumable_fleet(configuration, context)

    assert selected == compatible


def test_discovery_ignores_an_accepted_fleet(tmp_path: Path) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    accepted = _fleet_spec(configuration, context, "accepted")
    _persist_discovery_state(accepted, FleetPhase.ACCEPTED)

    assert harness.discover_resumable_fleet(configuration, context) is None


def test_discovery_rejects_multiple_compatible_incomplete_fleets(
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    first = _fleet_spec(configuration, context, "first")
    second = _fleet_spec(configuration, context, "second")
    _persist_discovery_state(first, FleetPhase.RUNNING)
    _persist_discovery_state(second, FleetPhase.REVIEWING)

    with pytest.raises(
        RepositoryBrainBuildError,
        match="multiple compatible incomplete memory fleets",
    ):
        harness.discover_resumable_fleet(configuration, context)


def test_resume_loads_exact_bound_graph_and_enrichment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    fleet_spec = _fleet_spec(configuration, context, "resume")
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "snapshot")
    enrichment = SimpleNamespace(
        overlay_id="overlay-resume",
        provider="openai",
        model="test-model",
        profile_version="test-v1",
    )
    loaded: list[tuple[object, ...]] = []

    def load_graph(root: Path, snapshot_id: str) -> object:
        loaded.append(("graph", root, snapshot_id))
        return graph_build

    def load_enrichment(path: Path, snapshot_id: str) -> object:
        loaded.append(("enrichment", path, snapshot_id))
        return enrichment

    monkeypatch.setattr(harness, "load_graph_snapshot", load_graph)
    monkeypatch.setattr(harness, "validate_graph_snapshot", lambda *_a, **_k: None)
    monkeypatch.setattr(harness, "load_graph_enrichment", load_enrichment)
    monkeypatch.setattr(harness, "validate_graph_enrichment", lambda *_a: None)
    monkeypatch.setattr(
        harness,
        "_resolve_model_profile",
        lambda _configuration: LLMProfile(
            name="test",
            provider="openai",
            model="test-model",
        ),
    )

    result = harness.load_recovery_model_layers(
        configuration,
        context,
        SimpleNamespace(),  # type: ignore[arg-type]
        fleet_spec,
    )

    assert result[0] is graph_build
    assert result[2] is enrichment
    assert loaded == [
        ("graph", configuration.graph_root, "graph-resume"),
        (
            "enrichment",
            configuration.bridger_root
            / "enrichment"
            / "graph-resume"
            / "overlay-resume",
            "graph-resume",
        ),
    ]


def test_init_resume_skips_new_graph_enrichment_and_memory_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    recovery_spec = _fleet_spec(configuration, context, "resume")
    graph_build = SimpleNamespace(snapshot_root=tmp_path / "persisted-graph")
    profile = LLMProfile(name="test", provider="openai", model="test-model")
    enrichment = SimpleNamespace(overlay_id="overlay-resume")
    received_recovery: list[object] = []

    monkeypatch.setattr(
        init_pipeline,
        "prepare_repository",
        lambda _root: (context, "file-index"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "extract_repository_facts",
        lambda *_args, **_kwargs: ("symbols", "report", "extraction"),
    )
    monkeypatch.setattr(
        harness,
        "discover_resumable_fleet",
        lambda *_args: recovery_spec,
    )
    monkeypatch.setattr(
        harness,
        "load_recovery_model_layers",
        lambda *_args: (graph_build, profile, enrichment),
    )
    monkeypatch.setattr(
        init_pipeline,
        "build_graph_intelligence",
        lambda *_args: pytest.fail("resume must not build graph intelligence"),
    )
    monkeypatch.setattr(
        init_pipeline,
        "create_graph_snapshot",
        lambda *_args: pytest.fail("resume must not create a graph snapshot"),
    )
    monkeypatch.setattr(
        harness,
        "prepare_model_layers",
        lambda *_args: pytest.fail("resume must not create enrichment"),
    )

    async def run_model(*args: object) -> Path:
        received_recovery.append(args[-1])
        return tmp_path / "published.json"

    monkeypatch.setattr(init_pipeline, "_run_model_driven_pipeline", run_model)

    result = init_pipeline.build_repository_brain(configuration)

    assert result.graph_build is graph_build
    assert received_recovery == [recovery_spec]


def test_old_worker_tool_profile_is_not_resume_compatible(tmp_path: Path) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    catalog, _definitions = harness.load_target_artifacts(
        harness._target_artifacts_root(configuration)
    )
    old_contract = _fleet_spec(configuration, context, "old-tools").model_copy(
        update={"default_permission_profile_id": "bridger-memory-tools-v1"}
    )

    assert not harness._is_resume_compatible(
        old_contract,
        configuration,
        context,
        catalog,
    )


def test_recovered_harness_reuses_authorities_without_stage_zero_or_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = resolve_init_configuration(
        InitMode.TEST,
        repository_root=tmp_path,
    )
    context = _context(tmp_path)
    recovery_spec = _fleet_spec(configuration, context, "resume")
    task_ids = ("task-accepted", "task-scheduled", "task-reviewing")
    target_ids = ("repository", "architecture", "testing")
    target_specs = {
        task_id: SimpleNamespace(target_task_id=task_id, target_id=target_id)
        for task_id, target_id in zip(task_ids, target_ids, strict=True)
    }
    target_states = {
        task_ids[0]: _HarnessTargetState(task_ids[0], TargetPhase.ACCEPTED),
        task_ids[1]: _HarnessTargetState(task_ids[1], TargetPhase.SCHEDULED),
        task_ids[2]: _HarnessTargetState(task_ids[2], TargetPhase.REVIEWING),
    }
    completion_states = {
        task_id: SimpleNamespace(target_task_id=task_id) for task_id in task_ids
    }
    fleet_state = FleetRunState(
        fleet_run_id=recovery_spec.fleet_run_id,
        phase=FleetPhase.RUNNING,
        target_task_ids=list(task_ids),
    )
    store = _Store()
    recovered = SimpleNamespace(
        fleet_spec=recovery_spec,
        fleet_state=fleet_state,
        target_specs=target_specs,
        target_states=target_states,
        completion_states=completion_states,
        store=store,
        close=lambda: setattr(store, "closed", True),
    )
    catalog = SimpleNamespace(
        targets=[SimpleNamespace(target_id=target_id) for target_id in target_ids]
    )
    definitions = [
        SimpleNamespace(target_id=target_id) for target_id in recovery_spec.target_ids
    ]
    started: set[str] = set()
    all_started = asyncio.Event()

    async def run_recovered_step(task_id: str, _runtime: object) -> WorkerCycleOutcome:
        started.add(task_id)
        if started == set(task_ids[1:]):
            all_started.set()
        await all_started.wait()
        target_states[task_id].phase = TargetPhase.ACCEPTED
        return WorkerCycleOutcome.FINALIZATION_REQUESTED

    monkeypatch.setattr(
        harness, "load_target_artifacts", lambda _root: (catalog, definitions)
    )
    monkeypatch.setattr(
        harness,
        "_profiles",
        lambda *_args: (
            SimpleNamespace(profile_id="bridger-worker-v1"),
            SimpleNamespace(profile_id="bridger-reviewer-v1"),
        ),
    )
    monkeypatch.setattr(harness, "recover_fleet", lambda *_args, **_kwargs: recovered)
    monkeypatch.setattr(
        harness,
        "bind_memory_run",
        lambda *_args, **_kwargs: pytest.fail("Stage 0 must not run"),
    )
    monkeypatch.setattr(
        harness,
        "initialize_fleet",
        lambda *_args: pytest.fail("Stage 1 must not run"),
    )
    monkeypatch.setattr(harness, "RepositoryNavigator", lambda *_args: object())
    monkeypatch.setattr(harness, "build_graph_overview", lambda *_args: object())
    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())
    monkeypatch.setattr(harness, "create_llm_client_from_profile", lambda _p: _Client())
    monkeypatch.setattr(
        harness,
        "_runnable_target_task_ids",
        lambda *_args: [
            task_id
            for task_id in task_ids
            if target_states[task_id].phase
            in {TargetPhase.SCHEDULED, TargetPhase.REVIEWING}
        ],
    )
    monkeypatch.setattr(harness, "_run_target_step", run_recovered_step)
    monkeypatch.setattr(
        harness,
        "validate_fleet",
        lambda *_args: SimpleNamespace(verdict=SimpleNamespace(value="pass")),
    )

    async def reconcile(**_kwargs: object) -> object:
        return SimpleNamespace(verdict=ReviewVerdict.PASS)

    monkeypatch.setattr(harness, "reconcile_fleet", reconcile)
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
        harness.run_memory_harness(
            configuration,
            context,
            SimpleNamespace(),  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            LLMProfile(name="test", provider="openai", model="test-model"),
            SimpleNamespace(),  # type: ignore[arg-type]
            recovery_spec=recovery_spec,
        )
    )

    assert result.publication_path == expected
    assert started == set(task_ids[1:])
    assert target_states[task_ids[0]].durable_marker == "preserved"
    assert store.closed is True


def test_reviewing_target_resumes_review_without_worker_investigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = "task-repository"
    spec = SimpleNamespace(
        target_task_id=task_id,
        target_id="repository",
        target_contract_version="1",
    )
    state = SimpleNamespace(phase=TargetPhase.REVIEWING)
    runtime = SimpleNamespace(
        specs_by_task={task_id: spec},
        states_by_task={task_id: state},
        completion_by_task={task_id: object()},
        definitions_by_id={"repository": object()},
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
    monkeypatch.setattr(
        harness,
        "compile_worker_context",
        lambda *_args, **_kwargs: pytest.fail("worker must not be hydrated"),
    )
    monkeypatch.setattr(
        harness,
        "validate_target_candidate",
        lambda *_args: pytest.fail("committed validation must not be duplicated"),
    )
    monkeypatch.setattr(harness, "ContextWindowManager", lambda _profile: object())

    async def review(**_kwargs: object) -> object:
        return SimpleNamespace(verdict=ReviewVerdict.PASS)

    accepted: list[str] = []
    monkeypatch.setattr(harness, "review_target", review)
    monkeypatch.setattr(
        harness,
        "accept_target",
        lambda _store, accepted_spec, _state: accepted.append(
            accepted_spec.target_task_id
        ),
    )

    outcome = asyncio.run(
        harness._run_target_step(task_id, runtime)  # type: ignore[arg-type]
    )

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert accepted == [task_id]


def _context(root: Path) -> RepositoryContext:
    return RepositoryContext(
        repository_id="repository-id",
        root_path=root,
        revision="a" * 40,
    )


def _fleet_spec(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    run_id: str,
) -> MemoryFleetSpec:
    catalog, _definitions = harness.load_target_artifacts(
        harness._target_artifacts_root(configuration)
    )
    target_capacity = len(catalog.targets)
    return MemoryFleetSpec(
        fleet_run_id=run_id,
        source=SourceBinding(
            repository_id=context.repository_id,
            repository_revision=context.revision,
            graph_snapshot_id=f"graph-{run_id}",
            enrichment_overlay_id=f"overlay-{run_id}",
        ),
        target_catalog_id=catalog.catalog_id,
        target_catalog_version=catalog.catalog_version,
        target_ids=[entry.target_id for entry in catalog.targets],
        runtime_profile_id="test-v1",
        default_worker_profile_id="bridger-worker-v1",
        default_reviewer_profile_id="bridger-reviewer-v1",
        default_permission_profile_id="bridger-memory-tools-v2",
        fleet_budget=harness._fleet_budget_for(True, target_capacity=target_capacity),
        default_target_budget=harness._target_budget_for(True),
        max_concurrent_targets=target_capacity,
        runtime_root=str(configuration.bridger_root / "runtime"),
        output_root=str(configuration.bridger_root / "memory"),
    )


def _persist_discovery_state(spec: MemoryFleetSpec, phase: FleetPhase) -> None:
    run_root = Path(spec.runtime_root) / spec.fleet_run_id
    initialization_root = run_root / "initialization"
    initialization_root.mkdir(parents=True)
    (run_root / "fleet-spec.json").write_text(
        spec.model_dump_json(),
        encoding="utf-8",
    )
    state = FleetRunState(
        fleet_run_id=spec.fleet_run_id,
        phase=phase,
        accepted_result_ref=(
            "accepted-result" if phase is FleetPhase.ACCEPTED else None
        ),
    )
    (initialization_root / "fleet-state.json").write_text(
        state.model_dump_json(),
        encoding="utf-8",
    )


class _Client:
    async def close(self) -> None:
        return None


class _Store:
    def __init__(self) -> None:
        self.closed = False


class _HarnessTargetState:
    def __init__(self, target_task_id: str, phase: TargetPhase) -> None:
        self.target_task_id = target_task_id
        self.phase = phase
        self.durable_marker = "preserved"

    def model_dump(self, *, mode: str) -> dict[str, str]:
        assert mode == "json"
        return {
            "target_task_id": self.target_task_id,
            "phase": self.phase.value,
            "durable_marker": self.durable_marker,
        }
