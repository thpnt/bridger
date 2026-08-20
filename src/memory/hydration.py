"""Stage 3 deterministic durable-state to WorkerContext hydration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path, PurePosixPath
from typing import Protocol

import orjson
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_core import to_jsonable_python

from artifacts.writer import write_artifact
from memory.context_window import ContextWindowManager
from memory.durability import FleetRuntimeStore
from memory.errors import (
    InvalidTargetArtifacts,
    WorkerContextHydrationError,
    WorkerContextInvocationError,
)
from memory.persistence import require_path_segment
from memory.recovery import record_runtime_error
from memory.targets import _resolve_catalog_definitions
from models.fleet_validation import FleetValidationFinding
from models.hydration import (
    CompletionObligationView,
    ContextWindowDiagnostics,
    OpenQuestion,
    PermissionProfile,
    RemainingExecutionBudget,
    RepairFinding,
    TargetContractView,
    WorkerContext,
    WorkerContextMode,
    WorkerInstructions,
    WorkerProfile,
)
from models.memory import (
    CandidateArtifactRef,
    FindingOrigin,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    SourceBinding,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from models.review import ReviewFinding
from models.validation import ValidationFinding
from models.worker_cycle import EvidenceReference
from models.worker_cycle import OpenQuestion as DurableOpenQuestion

_LOGGER = logging.getLogger(__name__)
_HYDRATION_ERROR_REF = "stage-3-context-hydration"


class CandidateArtifactRecord(BaseModel):
    """Minimal authoritative artifact state needed for reference validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    target_workspace: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    revision: int = Field(ge=1)
    digest: str = Field(min_length=1)


class EvidenceRecord(BaseModel):
    """Minimal durable evidence identity needed for integrity validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    source: SourceBinding


class OpenQuestionRecord(BaseModel):
    """Minimal authoritative question record needed for hydration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    is_open: bool = True


class FindingRecord(BaseModel):
    """Minimal authoritative routed finding record needed for repair context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    origin: FindingOrigin
    content: str = Field(min_length=1)
    is_open: bool = True
    affected_scope: str | None = Field(default=None, min_length=1)
    affected_artifact_id: str | None = Field(default=None, min_length=1)
    affected_artifact_refs: tuple[str, ...] = ()
    affected_obligation_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class HydrationStateReader(Protocol):
    """Small Stage-3 read boundary over later-stage authoritative stores."""

    def get_candidate_artifact(
        self,
        artifact_id: str,
    ) -> CandidateArtifactRecord | None:
        """Return current authoritative artifact metadata without its content."""

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        """Return durable evidence identity without evidence content."""

    def get_open_question(self, question_id: str) -> OpenQuestionRecord | None:
        """Return one authoritative open-question record."""

    def get_open_finding(self, finding_id: str) -> FindingRecord | None:
        """Return one authoritative routed finding record."""


class _PersistedHydrationStateReader:
    """Project Stage 5 target state through the existing Stage 3 read boundary."""

    def __init__(
        self,
        store: FleetRuntimeStore,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
    ) -> None:
        """Bind one reader to the current durable state of a target task."""
        if (
            target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
            or target_state.fleet_run_id != store.fleet_spec.fleet_run_id
            or target_state.target_task_id != target_spec.target_task_id
            or target_spec.source != store.fleet_spec.source
        ):
            raise WorkerContextInvocationError(
                "hydration persistence belongs to a different target"
            )
        self._store = store
        self._target_spec = target_spec
        self._target_state = target_state

    def get_candidate_artifact(
        self,
        artifact_id: str,
    ) -> CandidateArtifactRecord | None:
        """Return current artifact metadata only when its workspace bytes match."""
        reference = next(
            (
                item
                for item in self._target_state.artifact_refs
                if item.artifact_id == artifact_id
            ),
            None,
        )
        if reference is None:
            return None
        workspace = Path(self._target_spec.target_workspace).resolve()
        path = (workspace / reference.relative_path).resolve()
        if (
            not path.is_relative_to(workspace)
            or not path.is_file()
            or path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != reference.digest
        ):
            return None
        return CandidateArtifactRecord(
            artifact_id=reference.artifact_id,
            target_task_id=self._target_spec.target_task_id,
            target_workspace=self._target_spec.target_workspace,
            relative_path=reference.relative_path,
            revision=reference.revision,
            digest=reference.digest,
        )

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        """Load one immutable evidence identity from the target store."""
        path = self._store.paths.evidence(self._target_spec, evidence_id)
        if not path.is_file():
            return None
        try:
            reference = EvidenceReference.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            reference.evidence_id != evidence_id
            or reference.target_task_id != self._target_spec.target_task_id
        ):
            return None
        return EvidenceRecord(
            evidence_id=reference.evidence_id,
            source=reference.source,
        )

    def get_open_question(self, question_id: str) -> OpenQuestionRecord | None:
        """Load one immutable question and project its current openness."""
        path = self._store.paths.question(self._target_spec, question_id)
        if not path.is_file():
            return None
        try:
            question = DurableOpenQuestion.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            question.question_id != question_id
            or question.target_task_id != self._target_spec.target_task_id
        ):
            return None
        return OpenQuestionRecord(
            question_id=question.question_id,
            target_task_id=question.target_task_id,
            content=question.content,
            is_open=question_id in self._target_state.open_question_refs,
        )

    def get_open_finding(self, finding_id: str) -> FindingRecord | None:
        """Load one immutable evaluator finding in the current open projection."""
        reference = next(
            (
                item
                for item in self._target_state.open_finding_refs
                if item.finding_id == finding_id
            ),
            None,
        )
        if reference is None:
            return None
        if reference.origin is FindingOrigin.HARD_VALIDATION:
            return self._validation_finding(finding_id)
        if reference.origin is FindingOrigin.TARGET_REVIEW:
            return self._review_finding(finding_id)
        if reference.origin is FindingOrigin.FLEET_VALIDATION:
            return self._fleet_validation_finding(finding_id)
        if reference.origin is FindingOrigin.FLEET_REVIEW:
            return self._fleet_review_finding(finding_id)
        return None

    def _validation_finding(self, finding_id: str) -> FindingRecord | None:
        path = self._store.paths.validation_finding(self._target_spec, finding_id)
        if not path.is_file():
            return None
        try:
            finding = ValidationFinding.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            finding.finding_id != finding_id
            or finding.target_task_id != self._target_spec.target_task_id
        ):
            return None
        return FindingRecord(
            finding_id=finding.finding_id,
            target_task_id=finding.target_task_id,
            origin=FindingOrigin.HARD_VALIDATION,
            content=finding.message,
            affected_scope=finding.subject_ref,
            affected_artifact_id=(
                finding.subject_ref if finding.subject_kind == "artifact" else None
            ),
        )

    def _review_finding(self, finding_id: str) -> FindingRecord | None:
        path = self._store.paths.review_finding(self._target_spec, finding_id)
        if not path.is_file():
            return None
        try:
            finding = ReviewFinding.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            finding.finding_id != finding_id
            or finding.target_task_id != self._target_spec.target_task_id
        ):
            return None
        return FindingRecord(
            finding_id=finding.finding_id,
            target_task_id=finding.target_task_id,
            origin=FindingOrigin.TARGET_REVIEW,
            content=(
                f"{finding.message}\n\nRequired outcome: " f"{finding.required_outcome}"
            ),
            affected_artifact_refs=tuple(finding.affected_artifact_refs),
            affected_obligation_ids=tuple(finding.affected_obligation_ids),
        )

    def _fleet_validation_finding(
        self,
        finding_id: str,
    ) -> FindingRecord | None:
        path = self._store.paths.fleet_validation_finding(finding_id)
        if not path.is_file():
            return None
        try:
            finding = FleetValidationFinding.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            finding.finding_id != finding_id
            or finding.fleet_run_id != self._store.fleet_spec.fleet_run_id
            or self._target_spec.target_task_id not in finding.affected_target_task_ids
        ):
            return None
        return FindingRecord(
            finding_id=finding.finding_id,
            target_task_id=self._target_spec.target_task_id,
            origin=FindingOrigin.FLEET_VALIDATION,
            content=finding.message,
            affected_scope=finding.subject_ref,
        )

    def _fleet_review_finding(self, finding_id: str) -> FindingRecord | None:
        from models.fleet_review import FleetReviewFinding

        path = self._store.paths.fleet_review_finding(finding_id)
        if not path.is_file():
            return None
        try:
            finding = FleetReviewFinding.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None
        if (
            finding.finding_id != finding_id
            or finding.fleet_run_id != self._store.fleet_spec.fleet_run_id
            or self._target_spec.target_task_id not in finding.affected_target_task_ids
        ):
            return None
        return FindingRecord(
            finding_id=finding.finding_id,
            target_task_id=self._target_spec.target_task_id,
            origin=FindingOrigin.FLEET_REVIEW,
            content=(
                f"{finding.message}\n\nRequired outcome: " f"{finding.required_outcome}"
            ),
            affected_artifact_refs=tuple(finding.affected_artifact_paths),
        )


class WorkerContextDebugSnapshot(BaseModel):
    """Non-authoritative developer snapshot of one compiled worker context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: WorkerContext
    serialized_model_context: str
    diagnostics: ContextWindowDiagnostics


class WorkerContextDebugWriter:
    """Write optional non-authoritative Stage 3 snapshots under a debug root."""

    def __init__(self, debug_root: str) -> None:
        self._debug_root = Path(debug_root)

    def write(
        self,
        fleet_run_id: str,
        target_task_id: str,
        snapshot: WorkerContextDebugSnapshot,
    ) -> None:
        """Write the latest deterministic hydration snapshot for one task."""
        require_path_segment(fleet_run_id, "fleet_run_id")
        require_path_segment(target_task_id, "target_task_id")
        destination = (
            self._debug_root
            / fleet_run_id
            / "worker-contexts"
            / target_task_id
            / "hydration.json"
        )
        write_artifact(destination, snapshot)


def compile_worker_context(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition | None,
    worker_profile: WorkerProfile | None,
    permission_profile: PermissionProfile | None,
    worker_instructions: WorkerInstructions | None,
    state_reader: HydrationStateReader | None = None,
    *,
    context_window_manager: ContextWindowManager | None = None,
    fixed_request_input: str = "",
    provider_framing_tokens: int = 0,
    debug_writer: WorkerContextDebugWriter | None = None,
    persistence: FleetRuntimeStore | None = None,
) -> WorkerContext:
    """Compile one complete mandatory context and enter the HYDRATING phase."""
    _validate_invocation(fleet_spec, target_spec, target_state)
    if state_reader is None:
        if persistence is None:
            raise WorkerContextInvocationError(
                "hydration requires a state reader or persistence"
            )
        if persistence.fleet_spec != fleet_spec:
            raise WorkerContextInvocationError(
                "hydration persistence does not match the fleet specification"
            )
        state_reader = _PersistedHydrationStateReader(
            persistence,
            target_spec,
            target_state,
        )
    target_state.phase = TargetPhase.HYDRATING
    if persistence is not None:
        persistence.persist_target_state(
            target_spec,
            target_state,
            event_type="phase_transition",
            payload={
                "from_phase": TargetPhase.SCHEDULED.value,
                "to_phase": TargetPhase.HYDRATING.value,
            },
        )

    try:
        context, serialized, diagnostics = _compile_hydrating_context(
            fleet_spec,
            target_spec,
            target_state,
            completion_state,
            catalog,
            target_definition,
            worker_profile,
            permission_profile,
            worker_instructions,
            state_reader,
            context_window_manager=context_window_manager,
            fixed_request_input=fixed_request_input,
            provider_framing_tokens=provider_framing_tokens,
        )
    except WorkerContextHydrationError as error:
        _mark_hydration_failed(target_state)
        if persistence is not None:
            record_runtime_error(
                persistence,
                None,
                category="configuration",
                operation="context-hydration",
                message=str(error),
                retryable=False,
                target_spec=target_spec,
                target_state=target_state,
                phase=TargetPhase.HYDRATING.value,
            )
        raise
    except Exception as error:
        _mark_hydration_failed(target_state)
        if persistence is not None:
            record_runtime_error(
                persistence,
                None,
                category="runtime",
                operation="context-hydration",
                message="worker context hydration failed",
                retryable=False,
                target_spec=target_spec,
                target_state=target_state,
                phase=TargetPhase.HYDRATING.value,
            )
        raise WorkerContextHydrationError("worker context hydration failed") from error

    if debug_writer is not None:
        try:
            debug_writer.write(
                fleet_spec.fleet_run_id,
                target_spec.target_task_id,
                WorkerContextDebugSnapshot(
                    context=context,
                    serialized_model_context=serialized,
                    diagnostics=diagnostics,
                ),
            )
        except Exception:
            _LOGGER.warning(
                "could not write non-authoritative worker-context debug snapshot",
                exc_info=True,
            )
    if persistence is not None:
        persistence.persist_target_state(
            target_spec,
            target_state,
            event_type="context_hydrated",
            payload={},
        )
    return context


def serialize_worker_context(context: WorkerContext) -> str:
    """Serialize WorkerContext deterministically with stable sections first."""
    sections = [
        _section("Shared worker instructions", context.shared_worker_instructions),
        _section(
            "Source binding and global ownership guidance",
            _canonical_json(
                {
                    "source": context.source,
                    "global_ownership_guidance": context.global_ownership_guidance,
                }
            ),
        ),
        _section(
            "Target instructions and semantic contract",
            context.target_worker_instructions
            + "\n\n"
            + _canonical_json(context.target_contract),
        ),
        _section(
            "Execution mode and permissions",
            _canonical_json(
                {
                    "mode": context.mode,
                    "worker_profile_id": context.worker_profile_id,
                    "permission_profile_id": context.permission_profile_id,
                    "allowed_tool_ids": context.allowed_tool_ids,
                }
            ),
        ),
        _section(
            "Completion obligations and current states",
            _canonical_json(context.completion_obligations),
        ),
    ]
    if context.mode is WorkerContextMode.REPAIR:
        sections.append(
            _section("Open repair findings", _canonical_json(context.repair_findings))
        )
    if context.working_summary is not None:
        sections.append(_section("Working summary", context.working_summary))
    sections.extend(
        (
            _section("Open questions", _canonical_json(context.open_questions)),
            _section(
                "Remaining target budget",
                _canonical_json(context.remaining_target_budget),
            ),
            _section(
                "Complete candidate-artifact inventory",
                _canonical_json(context.candidate_artifacts),
            ),
        )
    )
    return "\n\n".join(sections) + "\n"


def _validate_invocation(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    if target_state.phase is not TargetPhase.SCHEDULED:
        raise WorkerContextInvocationError(
            "worker context hydration requires a SCHEDULED target"
        )
    if target_state.target_task_id != target_spec.target_task_id:
        raise WorkerContextInvocationError(
            "target spec and state identities do not match"
        )
    if target_spec.fleet_run_id != fleet_spec.fleet_run_id:
        raise WorkerContextInvocationError("target spec belongs to a different fleet")
    if target_state.fleet_run_id != fleet_spec.fleet_run_id:
        raise WorkerContextInvocationError("target state belongs to a different fleet")
    if target_spec.target_id not in fleet_spec.target_ids:
        raise WorkerContextInvocationError("target is not activated in this fleet")


def _compile_hydrating_context(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition | None,
    worker_profile: WorkerProfile | None,
    permission_profile: PermissionProfile | None,
    worker_instructions: WorkerInstructions | None,
    state_reader: HydrationStateReader,
    *,
    context_window_manager: ContextWindowManager | None,
    fixed_request_input: str,
    provider_framing_tokens: int,
) -> tuple[WorkerContext, str, ContextWindowDiagnostics]:
    _validate_models(
        fleet_spec,
        target_spec,
        target_state,
        completion_state,
        catalog,
    )
    definition = _resolve_definition(
        fleet_spec,
        target_spec,
        catalog,
        target_definition,
    )
    profile, permissions, instructions = _validate_configuration(
        target_spec,
        target_definition=definition,
        worker_profile=worker_profile,
        permission_profile=permission_profile,
        worker_instructions=worker_instructions,
    )
    manager = context_window_manager or ContextWindowManager(
        profile,
        fixed_request_input=fixed_request_input,
        provider_framing_tokens=provider_framing_tokens,
    )
    if context_window_manager is not None and (
        fixed_request_input or provider_framing_tokens
    ):
        raise WorkerContextHydrationError(
            "fixed request input must be configured on the supplied context manager"
        )
    if manager.profile != profile:
        raise WorkerContextHydrationError(
            "context-window manager does not match the resolved worker profile"
        )

    completion_obligations, completion_evidence = _project_completion(
        target_spec,
        completion_state,
        definition,
    )
    candidate_artifacts = _resolve_artifacts(
        target_spec,
        target_state,
        state_reader,
    )
    open_questions = _resolve_questions(target_spec, target_state, state_reader)
    repair_findings, finding_evidence = _resolve_findings(
        target_spec,
        target_state,
        state_reader,
    )
    _validate_evidence(
        target_spec,
        (*target_state.evidence_refs, *completion_evidence, *finding_evidence),
        state_reader,
    )
    mode = (
        WorkerContextMode.REPAIR
        if target_state.open_finding_refs
        else WorkerContextMode.INITIAL
    )
    context = WorkerContext(
        target_task_id=target_spec.target_task_id,
        mode=mode,
        worker_profile_id=profile.profile_id,
        permission_profile_id=permissions.profile_id,
        allowed_tool_ids=permissions.allowed_tool_ids,
        source=target_spec.source,
        shared_worker_instructions=instructions.shared,
        global_ownership_guidance=tuple(catalog.cross_target_ownership_rules),
        target_worker_instructions=instructions.target_specific,
        target_contract=_project_target_contract(definition),
        completion_obligations=completion_obligations,
        repair_findings=repair_findings,
        working_summary=target_state.working_summary,
        open_questions=open_questions,
        remaining_target_budget=_remaining_budget(target_spec, target_state),
        candidate_artifacts=candidate_artifacts,
    )
    serialized = serialize_worker_context(context)
    diagnostics = manager.inspect_initial_worker_context(serialized)
    if not diagnostics.within_initial_input_limit:
        raise WorkerContextHydrationError(
            "complete mandatory initial provider input exceeds the hard cap"
        )
    if not diagnostics.within_model_context_limit:
        raise WorkerContextHydrationError(
            "complete mandatory request exceeds the model context window"
        )
    return context, serialized, diagnostics


def _validate_models(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    catalog: MemoryTargetCatalog,
) -> None:
    try:
        MemoryFleetSpec.model_validate(fleet_spec.model_dump(mode="python"))
        TargetTaskSpec.model_validate(target_spec.model_dump(mode="python"))
        TargetTaskState.model_validate(target_state.model_dump(mode="python"))
        TargetCompletionState.model_validate(completion_state.model_dump(mode="python"))
        MemoryTargetCatalog.model_validate(catalog.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        raise WorkerContextHydrationError("hydration inputs are malformed") from error
    if target_spec.source != fleet_spec.source:
        raise WorkerContextHydrationError(
            "target source binding does not match the fleet source binding"
        )
    if completion_state.target_task_id != target_spec.target_task_id:
        raise WorkerContextHydrationError(
            "completion state belongs to a different target task"
        )


def _resolve_definition(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition | None,
) -> TargetDefinition:
    if (
        catalog.catalog_id != fleet_spec.target_catalog_id
        or catalog.catalog_version != fleet_spec.target_catalog_version
    ):
        raise WorkerContextHydrationError(
            "target catalog identity does not match the fleet specification"
        )
    if target_definition is None:
        raise WorkerContextHydrationError("target definition is missing")
    try:
        _, definitions = _resolve_catalog_definitions(
            catalog,
            [target_definition],
            require_exact=False,
            required_target_ids={target_spec.target_id},
        )
    except InvalidTargetArtifacts as error:
        raise WorkerContextHydrationError(
            "target definition does not match the catalog"
        ) from error
    definition = definitions[target_spec.target_id]
    if definition.target_contract_version != target_spec.target_contract_version:
        raise WorkerContextHydrationError(
            "target definition does not match the task contract version"
        )
    return definition


def _validate_configuration(
    target_spec: TargetTaskSpec,
    *,
    target_definition: TargetDefinition,
    worker_profile: WorkerProfile | None,
    permission_profile: PermissionProfile | None,
    worker_instructions: WorkerInstructions | None,
) -> tuple[WorkerProfile, PermissionProfile, WorkerInstructions]:
    if worker_profile is None:
        raise WorkerContextHydrationError("worker profile is missing")
    if permission_profile is None:
        raise WorkerContextHydrationError("permission profile is missing")
    if worker_instructions is None:
        raise WorkerContextHydrationError("worker instructions are missing")
    try:
        worker_profile = WorkerProfile.model_validate(
            worker_profile.model_dump(mode="python")
        )
        permission_profile = PermissionProfile.model_validate(
            permission_profile.model_dump(mode="python")
        )
        worker_instructions = WorkerInstructions.model_validate(
            worker_instructions.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        raise WorkerContextHydrationError(
            "worker, permission, or instruction configuration is malformed"
        ) from error
    if worker_profile.profile_id != target_spec.worker_profile_id:
        raise WorkerContextHydrationError("worker profile identity does not match")
    if permission_profile.profile_id != target_spec.permission_profile_id:
        raise WorkerContextHydrationError("permission profile identity does not match")
    if worker_instructions.worker_profile_id != worker_profile.profile_id:
        raise WorkerContextHydrationError(
            "shared worker instructions do not match the worker profile"
        )
    if (
        worker_instructions.target_id != target_definition.target_id
        or worker_instructions.target_contract_version
        != target_definition.target_contract_version
    ):
        raise WorkerContextHydrationError(
            "target worker instructions do not match the target contract"
        )
    return worker_profile, permission_profile, worker_instructions


def _project_completion(
    target_spec: TargetTaskSpec,
    completion_state: TargetCompletionState,
    definition: TargetDefinition,
) -> tuple[tuple[CompletionObligationView, ...], tuple[str, ...]]:
    if completion_state.target_task_id != target_spec.target_task_id:
        raise WorkerContextHydrationError(
            "completion state belongs to a different target task"
        )
    items = {item.obligation_id: item for item in completion_state.items}
    expected_ids = [
        obligation.obligation_id for obligation in definition.completion_obligations
    ]
    if set(items) != set(expected_ids):
        raise WorkerContextHydrationError(
            "completion state does not exactly match target obligations"
        )
    projected: list[CompletionObligationView] = []
    evidence_refs: list[str] = []
    for obligation in definition.completion_obligations:
        item = items[obligation.obligation_id]
        evidence_refs.extend(item.evidence_refs)
        projected.append(
            CompletionObligationView(
                obligation_id=obligation.obligation_id,
                description=obligation.description,
                applicability=obligation.applicability,
                condition_hint=obligation.condition_hint,
                status=item.status,
                resolution_note=item.resolution_note,
                evidence_refs=tuple(item.evidence_refs),
            )
        )
    return tuple(projected), tuple(evidence_refs)


def _resolve_artifacts(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[CandidateArtifactRef, ...]:
    artifact_ids = [reference.artifact_id for reference in target_state.artifact_refs]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise WorkerContextHydrationError("candidate artifact IDs must be unique")
    normalized_paths: set[str] = set()
    resolved: list[tuple[str, CandidateArtifactRef]] = []
    for reference in target_state.artifact_refs:
        normalized_path = _normalized_relative_path(reference.relative_path)
        if normalized_path in normalized_paths:
            raise WorkerContextHydrationError(
                "candidate artifact relative paths must be unique"
            )
        normalized_paths.add(normalized_path)
        record = state_reader.get_candidate_artifact(reference.artifact_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"candidate artifact is missing: {reference.artifact_id}"
            )
        if (
            record.target_task_id != target_spec.target_task_id
            or record.target_workspace != target_spec.target_workspace
        ):
            raise WorkerContextHydrationError(
                "candidate artifact is outside the target workspace: "
                f"{reference.artifact_id}"
            )
        if (
            record.artifact_id != reference.artifact_id
            or record.relative_path != reference.relative_path
            or record.revision != reference.revision
            or record.digest != reference.digest
        ):
            raise WorkerContextHydrationError(
                "candidate artifact reference does not match authoritative state: "
                f"{reference.artifact_id}"
            )
        resolved.append((normalized_path, reference))
    return tuple(
        reference
        for _, reference in sorted(
            resolved,
            key=lambda item: (item[0], item[1].artifact_id),
        )
    )


def _resolve_questions(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[OpenQuestion, ...]:
    if len(target_state.open_question_refs) != len(
        set(target_state.open_question_refs)
    ):
        raise WorkerContextHydrationError("open question references must be unique")
    questions: list[OpenQuestion] = []
    for question_id in target_state.open_question_refs:
        record = state_reader.get_open_question(question_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"open question is missing: {question_id}"
            )
        if (
            record.question_id != question_id
            or record.target_task_id != target_spec.target_task_id
            or not record.is_open
        ):
            raise WorkerContextHydrationError(
                f"open question reference is invalid: {question_id}"
            )
        questions.append(OpenQuestion(question_id=question_id, content=record.content))
    return tuple(questions)


def _resolve_findings(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[tuple[RepairFinding, ...], tuple[str, ...]]:
    finding_ids = [reference.finding_id for reference in target_state.open_finding_refs]
    if len(finding_ids) != len(set(finding_ids)):
        raise WorkerContextHydrationError("open finding references must be unique")
    findings: list[RepairFinding] = []
    evidence_refs: list[str] = []
    for reference in target_state.open_finding_refs:
        record = state_reader.get_open_finding(reference.finding_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"open finding is missing: {reference.finding_id}"
            )
        if (
            record.finding_id != reference.finding_id
            or record.target_task_id != target_spec.target_task_id
            or record.origin is not reference.origin
            or not record.is_open
        ):
            raise WorkerContextHydrationError(
                f"open finding reference is invalid: {reference.finding_id}"
            )
        evidence_refs.extend(record.evidence_refs)
        findings.append(
            RepairFinding(
                finding_id=record.finding_id,
                origin=record.origin,
                content=record.content,
                affected_scope=record.affected_scope,
                affected_artifact_id=record.affected_artifact_id,
                affected_artifact_refs=record.affected_artifact_refs,
                affected_obligation_ids=record.affected_obligation_ids,
                evidence_refs=record.evidence_refs,
            )
        )
    return tuple(findings), tuple(evidence_refs)


def _validate_evidence(
    target_spec: TargetTaskSpec,
    evidence_ids: tuple[str, ...],
    state_reader: HydrationStateReader,
) -> None:
    for evidence_id in dict.fromkeys(evidence_ids):
        record = state_reader.get_evidence(evidence_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"referenced evidence is missing: {evidence_id}"
            )
        if record.evidence_id != evidence_id or record.source != target_spec.source:
            raise WorkerContextHydrationError(
                f"referenced evidence has incompatible identity: {evidence_id}"
            )


def _project_target_contract(definition: TargetDefinition) -> TargetContractView:
    return TargetContractView(
        target_id=definition.target_id,
        target_contract_version=definition.target_contract_version,
        canonical_question=definition.canonical_question,
        purpose=definition.purpose,
        expected_abstraction=definition.expected_abstraction,
        always_relevant_scope=tuple(definition.always_relevant_scope),
        conditional_scope=tuple(definition.conditional_scope),
        exclusions=tuple(definition.exclusions),
        boundary_guidance=tuple(definition.boundary_guidance),
        investigation_expectations=tuple(definition.investigation_expectations),
        evidence_expectations=tuple(definition.evidence_expectations),
        output_quality_expectations=tuple(definition.output_quality_expectations),
    )


def _remaining_budget(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> RemainingExecutionBudget:
    budget = target_spec.budget
    usage = target_state.usage
    values = {
        "cycles": budget.max_cycles - usage.cycles,
        "model_calls": budget.max_model_calls - usage.model_calls,
        "tool_calls": budget.max_tool_calls - usage.tool_calls,
        "repair_cycles": budget.max_repair_cycles - usage.repair_cycles,
        "input_tokens": (
            None
            if budget.max_input_tokens is None
            else budget.max_input_tokens - usage.input_tokens
        ),
        "output_tokens": (
            None
            if budget.max_output_tokens is None
            else budget.max_output_tokens - usage.output_tokens
        ),
    }
    if any(value is not None and value < 0 for value in values.values()):
        raise WorkerContextHydrationError(
            "target usage exceeds its configured execution budget"
        )
    return RemainingExecutionBudget.model_validate(values)


def _normalized_relative_path(relative_path: str) -> str:
    if "\\" in relative_path:
        raise WorkerContextHydrationError(
            "candidate artifact path must use normalized POSIX separators"
        )
    path = PurePosixPath(relative_path)
    if (
        relative_path in {"", "."}
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise WorkerContextHydrationError(
            "candidate artifact path must be normalized and relative"
        )
    normalized = path.as_posix()
    if normalized != relative_path:
        raise WorkerContextHydrationError(
            "candidate artifact path must be normalized and relative"
        )
    return normalized


def _mark_hydration_failed(target_state: TargetTaskState) -> None:
    target_state.last_error_ref = _HYDRATION_ERROR_REF
    target_state.phase = TargetPhase.FAILED


def _section(title: str, content: str) -> str:
    return f"# {title}\n\n{content}"


def _canonical_json(value: object) -> str:
    return orjson.dumps(
        to_jsonable_python(value),
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")


__all__ = [
    "CandidateArtifactRecord",
    "EvidenceRecord",
    "FindingRecord",
    "HydrationStateReader",
    "OpenQuestionRecord",
    "WorkerContextDebugSnapshot",
    "WorkerContextDebugWriter",
    "compile_worker_context",
    "serialize_worker_context",
]
