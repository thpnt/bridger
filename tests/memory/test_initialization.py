"""Locked core-contract and Stage 0-1 memory-harness invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx  # type: ignore[import-untyped]
import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.files import FileIndex, summarize_files
from bridger.contracts.graph import GraphBuildResult, GraphSnapshotManifest
from bridger.contracts.memory.core import (
    ActivationMode,
    CompletionItemState,
    CompletionObligationDefinition,
    CompletionStatus,
    ExecutionBudget,
    ExecutionUsage,
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
    TargetTaskState,
)
from bridger.contracts.repository import RepositoryContext
from bridger.contracts.symbols import SymbolIndex, summarize_symbols
from bridger.memory import (
    FleetInitializationError,
    InvalidTargetArtifacts,
    MemoryRunBindingError,
    TargetActivationError,
    bind_memory_run,
    initialize_fleet,
    load_target_artifacts,
    resolve_target_activation,
)

_REVISION = "a" * 40
_DEFAULT_TARGETS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bridger"
    / "memory"
    / "default-targets"
)
_SHIPPED_OBLIGATION_IDS = {
    "repository": [
        "repository-purpose",
        "languages-frameworks-toolchain",
        "applications-packages-workspaces",
        "source-organization",
        "entry-surfaces",
        "generated-vendor-special-regions",
        "specialist-navigation",
    ],
    "business-logic": [
        "domain-concepts",
        "domain-actions",
        "domain-workflows",
        "rules-invariants",
        "domain-states-transitions",
        "validation-eligibility",
        "domain-authorization",
        "domain-side-effects",
        "domain-failures",
        "pricing-billing",
        "subscriptions-entitlements",
        "quotas-limits",
        "approvals-scheduling",
        "lifecycle-calculations",
        "regulatory-provider-semantics",
    ],
    "architecture": [
        "runtime-entrypoints",
        "runtime-components",
        "component-responsibilities",
        "component-dependencies",
        "execution-paths",
        "bootstrap-composition",
        "async-background-execution",
        "component-state-ownership",
        "extension-mechanisms",
        "runtime-error-recovery",
    ],
    "data-and-state": [
        "state-categories-stores",
        "sources-of-truth",
        "data-models",
        "read-write-ownership",
        "mutation-lifecycle",
        "consistency-transactions",
        "migrations-schema-evolution",
        "caches-derived-state",
        "retention-versioning-locking",
    ],
    "interfaces-and-integrations": [
        "inbound-interfaces",
        "outbound-integrations",
        "contracts-mappings",
        "boundary-authentication-security",
        "error-retry-idempotency",
        "callbacks-events-webhooks",
        "versioning-compatibility",
        "boundary-internal-handoff",
    ],
    "testing": [
        "frameworks-test-levels",
        "test-organization",
        "fixtures-factories-setup",
        "isolation-external-dependencies",
        "validation-commands",
        "change-verification-mapping",
        "ci-verification",
        "specialized-test-strategies",
        "material-testing-gaps",
    ],
    "conventions": [
        "naming-layout",
        "structural-patterns",
        "error-logging-configuration",
        "type-schema-patterns",
        "specialist-implementation-conventions",
        "enforced-vs-observed",
        "local-convention-scope",
    ],
    "operations": [
        "build-package-path",
        "runtime-prerequisites-configuration",
        "environments",
        "ci-cd-release",
        "deployment-topology",
        "secrets-config-injection",
        "health-observability",
        "migrations-rollout-rollback",
        "scaling-scheduled-operations",
        "operator-developer-commands",
    ],
    "design": [
        "visual-language",
        "tokens-themes",
        "component-design-patterns",
        "layout-navigation",
        "responsive-behavior",
        "interaction-feedback",
        "standardized-ui-states",
        "accessibility-patterns",
        "design-system-tooling",
    ],
}


@pytest.fixture
def upstream(
    tmp_path: Path,
) -> tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult]:
    context = RepositoryContext(
        repository_id="repository-1",
        root_path=tmp_path / "repository",
        revision=_REVISION,
    )
    file_index = FileIndex(
        schema_version="1",
        repository_id=context.repository_id,
        revision=context.revision,
        files=[],
        summary=summarize_files([]),
    )
    symbol_index = SymbolIndex(
        schema_version="1",
        repository_id=context.repository_id,
        revision=context.revision,
        symbols=[],
        summary=summarize_symbols([]),
    )
    manifest = GraphSnapshotManifest.model_construct(
        snapshot_id="snapshot-1",
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
    )
    graph_build = GraphBuildResult.model_construct(
        operation_mode="loaded",
        graph=nx.DiGraph(),
        manifest=manifest,
        diagnostics=None,
        snapshot_root=tmp_path / "graph" / "snapshot-1",
    )
    return context, file_index, symbol_index, graph_build


def test_locked_enum_values_and_core_mutability() -> None:
    assert [status.value for status in CompletionStatus] == [
        "uninvestigated",
        "covered",
        "not-applicable",
        "unknown",
    ]
    assert [phase.value for phase in TargetPhase] == [
        "initialized",
        "scheduled",
        "hydrating",
        "working",
        "finalizing",
        "validating",
        "reviewing",
        "repair",
        "accepted",
        "blocked",
        "exhausted",
        "failed",
        "stopped",
    ]
    assert [phase.value for phase in FleetPhase] == [
        "initialized",
        "running",
        "validating",
        "reviewing",
        "repairing",
        "accepted",
        "blocked",
        "exhausted",
        "failed",
        "stopped",
    ]
    assert [origin.value for origin in FindingOrigin] == [
        "hard-validation",
        "target-review",
        "fleet-validation",
        "fleet-review",
    ]

    source = SourceBinding(
        repository_id="repository-1",
        repository_revision=_REVISION,
        graph_snapshot_id="snapshot-1",
    )
    with pytest.raises(ValidationError, match="frozen"):
        source.repository_id = "changed"

    usage = ExecutionUsage()
    usage.cycles = 1
    assert usage.cycles == 1
    with pytest.raises(ValidationError):
        usage.cycles = -1


def test_mutable_state_defaults_and_model_invariants() -> None:
    target_state = TargetTaskState(
        target_task_id="task-1",
        fleet_run_id="fleet-1",
    )
    assert target_state.phase is TargetPhase.INITIALIZED
    assert target_state.usage == ExecutionUsage()
    assert target_state.working_summary is None
    assert target_state.open_question_refs == []
    assert target_state.artifact_refs == []
    assert target_state.evidence_refs == []
    assert target_state.open_finding_refs == []
    assert target_state.last_checkpoint_ref is None
    assert target_state.pending_finalization_request_ref is None
    assert target_state.last_error_ref is None
    assert target_state.last_accepted_result_ref is None

    fleet_state = FleetRunState(fleet_run_id="fleet-1")
    assert fleet_state.phase is FleetPhase.INITIALIZED
    assert fleet_state.usage == ExecutionUsage()
    assert fleet_state.target_task_ids == []
    assert fleet_state.open_finding_refs == []
    assert fleet_state.accepted_result_ref is None

    with pytest.raises(ValidationError, match="resolution_note"):
        CompletionItemState(
            obligation_id="obligation-1",
            status=CompletionStatus.COVERED,
        )
    with pytest.raises(ValidationError, match="unique"):
        TargetCompletionState(
            target_task_id="task-1",
            items=[
                CompletionItemState(obligation_id="duplicate"),
                CompletionItemState(obligation_id="duplicate"),
            ],
        )


def test_static_target_artifacts_load_from_yaml(tmp_path: Path) -> None:
    repository = _target_definition("repository")
    design = _target_definition(
        "design",
        activation=TargetActivation(
            mode=ActivationMode.CONDITIONAL,
            rule_id="test_frontend_present_v1",
        ),
    )
    catalog = _catalog(repository, design)
    artifact_root = _write_target_bundle(tmp_path, catalog, [repository, design])

    loaded_catalog, loaded_definitions = load_target_artifacts(artifact_root)

    assert loaded_catalog == catalog
    assert loaded_definitions == [repository, design]
    assert loaded_definitions[0].completion_obligations == (
        repository.completion_obligations
    )


def test_shipped_target_bundle_has_versioned_granular_contracts() -> None:
    catalog, definitions = load_target_artifacts(_DEFAULT_TARGETS_ROOT)

    assert catalog.catalog_version == "v2"
    assert [definition.target_id for definition in definitions] == list(
        _SHIPPED_OBLIGATION_IDS
    )
    assert {
        definition.target_id: [
            obligation.obligation_id for obligation in definition.completion_obligations
        ]
        for definition in definitions
    } == _SHIPPED_OBLIGATION_IDS
    assert all(definition.target_contract_version == "v2" for definition in definitions)
    assert all(entry.target_contract_version == "v2" for entry in catalog.targets)
    conditional = {
        obligation.obligation_id: obligation.condition_hint
        for definition in definitions
        for obligation in definition.completion_obligations
        if obligation.applicability is ObligationApplicability.CONDITIONAL
    }
    assert conditional
    assert all(condition_hint for condition_hint in conditional.values())


def test_static_target_artifacts_reject_duplicates_and_version_mismatch(
    tmp_path: Path,
) -> None:
    definition = _target_definition("repository")
    catalog = _catalog(definition)
    duplicate_root = _write_target_bundle(
        tmp_path / "duplicate",
        catalog,
        [definition, definition],
    )
    with pytest.raises(InvalidTargetArtifacts, match="duplicate"):
        load_target_artifacts(duplicate_root)

    mismatch = definition.model_copy(update={"target_contract_version": "contract-v2"})
    mismatch_root = _write_target_bundle(
        tmp_path / "mismatch",
        catalog,
        [mismatch],
    )
    with pytest.raises(InvalidTargetArtifacts, match="version-mismatched"):
        load_target_artifacts(mismatch_root)


def test_static_target_models_reject_invalid_activation_and_obligations() -> None:
    with pytest.raises(ValidationError, match="cannot declare"):
        TargetActivation(mode=ActivationMode.ALWAYS, rule_id="unexpected")
    with pytest.raises(ValidationError, match="requires rule_id"):
        TargetActivation(mode=ActivationMode.CONDITIONAL)

    duplicate = _completion_obligation("duplicate")
    with pytest.raises(ValidationError, match="obligation IDs must be unique"):
        _target_definition(
            "repository",
            completion_obligations=[duplicate, duplicate],
        )


def test_activation_is_ordered_deterministic_and_explicit_on_failure(
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    context, file_index, symbol_index, graph_build = upstream
    always = _target_definition("repository")
    conditional = _target_definition(
        "design",
        activation=TargetActivation(
            mode=ActivationMode.CONDITIONAL,
            rule_id="test_frontend_present_v1",
        ),
    )
    catalog = _catalog(always, conditional)

    active = resolve_target_activation(
        catalog,
        [always, conditional],
        context,
        file_index,
        symbol_index,
        graph_build,
        activation_rules={"test_frontend_present_v1": lambda *_: True},
    )
    inactive = resolve_target_activation(
        catalog,
        [always, conditional],
        context,
        file_index,
        symbol_index,
        graph_build,
        activation_rules={"test_frontend_present_v1": lambda *_: False},
    )

    assert active == ["repository", "design"]
    assert inactive == ["repository"]
    with pytest.raises(TargetActivationError, match="unknown activation rule"):
        resolve_target_activation(
            catalog,
            [always, conditional],
            context,
            file_index,
            symbol_index,
            graph_build,
        )

    def failing_rule(*_: object) -> bool:
        raise LookupError("required deterministic fact is unavailable")

    with pytest.raises(TargetActivationError, match="activation rule failed"):
        resolve_target_activation(
            catalog,
            [always, conditional],
            context,
            file_index,
            symbol_index,
            graph_build,
            activation_rules={"test_frontend_present_v1": failing_rule},
        )


def test_binding_persists_exact_immutable_spec_in_activation_order(
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    repository = _target_definition("repository")
    design = _target_definition(
        "design",
        activation=TargetActivation(
            mode=ActivationMode.CONDITIONAL,
            rule_id="test_frontend_present_v1",
        ),
    )
    testing = _target_definition("testing")
    catalog = _catalog(repository, design, testing)

    spec = _bind(
        tmp_path,
        upstream,
        catalog,
        [repository, design, testing],
        activation_rules={"test_frontend_present_v1": lambda *_: False},
    )

    assert spec.target_ids == ["repository", "testing"]
    assert spec.source == SourceBinding(
        repository_id="repository-1",
        repository_revision=_REVISION,
        graph_snapshot_id="snapshot-1",
    )
    assert spec.runtime_profile_id == "runtime-v1"
    assert spec.max_concurrent_targets == 2
    assert (Path(spec.runtime_root) / spec.fleet_run_id / "fleet-spec.json").is_file()
    assert set(spec.model_dump()) == {
        "schema_version",
        "fleet_run_id",
        "source",
        "target_catalog_id",
        "target_catalog_version",
        "target_ids",
        "runtime_profile_id",
        "default_worker_profile_id",
        "default_reviewer_profile_id",
        "default_permission_profile_id",
        "fleet_budget",
        "default_target_budget",
        "max_concurrent_targets",
        "runtime_root",
        "output_root",
    }
    with pytest.raises(ValidationError, match="frozen"):
        spec.runtime_profile_id = "changed"


def test_binding_rejects_incompatible_upstream_and_target_artifacts(
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    context, file_index, symbol_index, graph_build = upstream
    definition = _target_definition("repository")
    catalog = _catalog(definition)
    mismatched_index = file_index.model_copy(update={"repository_id": "other"})

    with pytest.raises(MemoryRunBindingError):
        _bind(
            tmp_path / "file-mismatch",
            (context, mismatched_index, symbol_index, graph_build),
            catalog,
            [definition],
        )

    mismatched_graph = graph_build.model_copy(
        update={
            "manifest": graph_build.manifest.model_copy(update={"revision": "b" * 40})
        }
    )
    with pytest.raises(MemoryRunBindingError):
        _bind(
            tmp_path / "graph-mismatch",
            (context, file_index, symbol_index, mismatched_graph),
            catalog,
            [definition],
        )

    overlay = GraphEnrichmentOverlay.model_construct(
        overlay_id="overlay-1",
        graph_snapshot_id="other-snapshot",
    )
    with pytest.raises(MemoryRunBindingError):
        _bind(
            tmp_path / "overlay-mismatch",
            upstream,
            catalog,
            [definition],
            enrichment_overlay=overlay,
        )

    wrong_version = definition.model_copy(
        update={"target_contract_version": "contract-v2"}
    )
    with pytest.raises(MemoryRunBindingError, match="version-mismatched"):
        _bind(
            tmp_path / "catalog-mismatch",
            upstream,
            catalog,
            [wrong_version],
        )


def test_initialize_fleet_materializes_exact_active_initial_state(
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    repository = _target_definition("repository")
    design = _target_definition(
        "design",
        activation=TargetActivation(
            mode=ActivationMode.CONDITIONAL,
            rule_id="test_frontend_present_v1",
        ),
    )
    testing = _target_definition(
        "testing",
        depends_on=["repository"],
        completion_obligations=[
            _completion_obligation("test-strategy"),
            _completion_obligation(
                "frontend-tests",
                applicability=ObligationApplicability.CONDITIONAL,
                condition_hint="When a frontend is present.",
            ),
        ],
    )
    catalog = _catalog(repository, design, testing)
    spec = _bind(
        tmp_path,
        upstream,
        catalog,
        [repository, design, testing],
        activation_rules={"test_frontend_present_v1": lambda *_: False},
    )

    fleet_state, task_specs, task_states, completion_states = initialize_fleet(
        spec,
        catalog,
        [repository, testing],
    )

    assert fleet_state == FleetRunState(
        fleet_run_id=spec.fleet_run_id,
        target_task_ids=[task.target_task_id for task in task_specs],
    )
    assert fleet_state.phase is FleetPhase.INITIALIZED
    assert [task.target_id for task in task_specs] == ["repository", "testing"]
    assert len({task.target_task_id for task in task_specs}) == 2
    assert all(task.source == spec.source for task in task_specs)
    assert all(task.budget == spec.default_target_budget for task in task_specs)
    assert task_specs[0].depends_on_target_task_ids == []
    assert task_specs[1].depends_on_target_task_ids == [task_specs[0].target_task_id]
    assert all(state.phase is TargetPhase.INITIALIZED for state in task_states)
    assert all(state.usage == ExecutionUsage() for state in task_states)
    assert all(state.artifact_refs == [] for state in task_states)
    assert all(state.evidence_refs == [] for state in task_states)
    assert all(state.open_finding_refs == [] for state in task_states)
    assert all(state.last_checkpoint_ref is None for state in task_states)
    assert all(state.last_error_ref is None for state in task_states)
    assert all(state.last_accepted_result_ref is None for state in task_states)
    assert [item.obligation_id for item in completion_states[1].items] == [
        "test-strategy",
        "frontend-tests",
    ]
    assert all(
        item.status is CompletionStatus.UNINVESTIGATED
        and item.resolution_note is None
        and item.evidence_refs == []
        for completion in completion_states
        for item in completion.items
    )
    assert not hasattr(task_specs[0], "completion_contract_version")
    assert not hasattr(completion_states[0], "completion_contract_version")

    output_root = Path(spec.output_root)
    assert sorted(path.name for path in output_root.iterdir()) == [
        "repository",
        "testing",
    ]
    assert all(Path(task.target_workspace).parent == output_root for task in task_specs)
    assert all(not any(Path(task.target_workspace).iterdir()) for task in task_specs)
    assert not (output_root / "design").exists()
    assert (
        Path(spec.runtime_root)
        / spec.fleet_run_id
        / "initialization"
        / "fleet-state.json"
    ).is_file()


def test_shipped_contracts_materialize_every_obligation_independently(
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    catalog, definitions = load_target_artifacts(_DEFAULT_TARGETS_ROOT)
    spec = _bind(
        tmp_path,
        upstream,
        catalog,
        definitions,
        activation_rules={"frontend_stack_present_v1": lambda *_: False},
    )

    _, task_specs, _, completion_states = initialize_fleet(
        spec,
        catalog,
        definitions,
    )

    target_ids_by_task = {task.target_task_id: task.target_id for task in task_specs}
    materialized = {
        target_ids_by_task[state.target_task_id]: [
            item.obligation_id for item in state.items
        ]
        for state in completion_states
    }
    assert materialized == {
        target_id: obligation_ids
        for target_id, obligation_ids in _SHIPPED_OBLIGATION_IDS.items()
        if target_id != "design"
    }

    architecture = next(
        state
        for state in completion_states
        if target_ids_by_task[state.target_task_id] == "architecture"
    )
    architecture.items[0] = architecture.items[0].model_copy(
        update={
            "status": CompletionStatus.COVERED,
            "resolution_note": "Entrypoints were investigated.",
        }
    )
    assert architecture.items[1].status is CompletionStatus.UNINVESTIGATED
    assert len(architecture.items) == len(_SHIPPED_OBLIGATION_IDS["architecture"])


@pytest.mark.parametrize("failure", ["inactive", "invalid", "cycle"])
def test_initialize_fleet_rejects_invalid_dependencies_without_runnable_state(
    failure: str,
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    activation_rules: dict[str, Any] = {}
    if failure == "inactive":
        first = _target_definition("repository", depends_on=["design"])
        second = _target_definition(
            "design",
            activation=TargetActivation(
                mode=ActivationMode.CONDITIONAL,
                rule_id="test_frontend_present_v1",
            ),
        )
        activation_rules["test_frontend_present_v1"] = lambda *_: False
    elif failure == "invalid":
        first = _target_definition("repository", depends_on=["missing"])
        second = _target_definition("testing")
    else:
        first = _target_definition("repository", depends_on=["testing"])
        second = _target_definition("testing", depends_on=["repository"])
    catalog = _catalog(first, second)
    spec = _bind(
        tmp_path,
        upstream,
        catalog,
        [first, second],
        activation_rules=activation_rules,
    )

    with pytest.raises(FleetInitializationError):
        initialize_fleet(spec, catalog, [first, second])

    assert not (Path(spec.runtime_root) / spec.fleet_run_id / "initialization").exists()
    assert not Path(spec.output_root).exists()


def test_initialize_fleet_rejects_catalog_mismatch_and_workspace_collision(
    tmp_path: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
) -> None:
    definition = _target_definition("repository")
    catalog = _catalog(definition)
    spec = _bind(tmp_path, upstream, catalog, [definition])
    mismatched_catalog = catalog.model_copy(update={"catalog_version": "catalog-v2"})

    with pytest.raises(FleetInitializationError, match="does not match"):
        initialize_fleet(spec, mismatched_catalog, [definition])

    workspace = Path(spec.output_root) / "repository"
    workspace.mkdir(parents=True)
    with pytest.raises(FleetInitializationError, match="already exists"):
        initialize_fleet(spec, catalog, [definition])
    assert not (Path(spec.runtime_root) / spec.fleet_run_id / "initialization").exists()


def test_target_definition_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        _target_definition("repository", depends_on=["repository"])


def _target_definition(
    target_id: str,
    *,
    activation: TargetActivation | None = None,
    depends_on: list[str] | None = None,
    completion_obligations: list[CompletionObligationDefinition] | None = None,
) -> TargetDefinition:
    return TargetDefinition(
        schema_version=1,
        target_id=target_id,
        target_contract_version="contract-v1",
        activation=activation or TargetActivation(mode=ActivationMode.ALWAYS),
        depends_on=depends_on or [],
        canonical_question=f"What does {target_id} own?",
        purpose=f"Explain {target_id}.",
        expected_abstraction="Repository-level semantics.",
        always_relevant_scope=[f"Core {target_id} behavior."],
        conditional_scope=[],
        exclusions=["Unrelated implementation detail."],
        boundary_guidance=["Keep target ownership explicit."],
        investigation_expectations=["Inspect deterministic repository evidence."],
        evidence_expectations=["Ground claims in the bound revision."],
        completion_obligations=(
            completion_obligations
            if completion_obligations is not None
            else [_completion_obligation(f"{target_id}-coverage")]
        ),
        output_quality_expectations=["Be concise and precise."],
    )


def _completion_obligation(
    obligation_id: str,
    *,
    applicability: ObligationApplicability = ObligationApplicability.ALWAYS,
    condition_hint: str | None = None,
) -> CompletionObligationDefinition:
    return CompletionObligationDefinition(
        obligation_id=obligation_id,
        description=f"Investigate {obligation_id}.",
        applicability=applicability,
        condition_hint=condition_hint,
    )


def _catalog(*definitions: TargetDefinition) -> MemoryTargetCatalog:
    return MemoryTargetCatalog(
        schema_version=1,
        catalog_id="bridger-memory",
        catalog_version="catalog-v1",
        targets=[
            TargetCatalogEntry(
                target_id=definition.target_id,
                target_contract_version=definition.target_contract_version,
            )
            for definition in definitions
        ],
        cross_target_ownership_rules=["Each fact has one canonical target owner."],
    )


def _write_target_bundle(
    root: Path,
    catalog: MemoryTargetCatalog,
    definitions: list[TargetDefinition],
) -> Path:
    target_root = root / "targets"
    target_root.mkdir(parents=True)
    (root / "catalog.yaml").write_text(
        yaml.safe_dump(catalog.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    for index, definition in enumerate(definitions):
        (target_root / f"{index:02}-{definition.target_id}.yaml").write_text(
            yaml.safe_dump(definition.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
    return root


def _bind(
    root: Path,
    upstream: tuple[RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
    catalog: MemoryTargetCatalog,
    definitions: list[TargetDefinition],
    *,
    activation_rules: dict[str, Any] | None = None,
    enrichment_overlay: GraphEnrichmentOverlay | None = None,
) -> MemoryFleetSpec:
    context, file_index, symbol_index, graph_build = upstream
    return bind_memory_run(
        context,
        file_index,
        symbol_index,
        graph_build,
        catalog,
        definitions,
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=_budget(),
        default_target_budget=_budget(),
        max_concurrent_targets=2,
        runtime_root=root / "runtime",
        output_root=root / "output",
        enrichment_overlay=enrichment_overlay,
        activation_rules=activation_rules,
    )


def _budget() -> ExecutionBudget:
    return ExecutionBudget(
        max_cycles=10,
        max_model_calls=10,
        max_tool_calls=50,
        max_repair_cycles=2,
    )
