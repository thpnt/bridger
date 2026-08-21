"""Deterministic Stage 7 validation of an exact submitted checkpoint."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from bridger.contracts.memory.core import (
    CompletionStatus,
    FindingOrigin,
    FindingRef,
    ObligationApplicability,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.persistence import (
    TargetFinalizationRequest,
    TaskCheckpoint,
)
from bridger.contracts.memory.validation import (
    TargetValidationReport,
    ValidationFinding,
    ValidationVerdict,
)
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    EvidenceReference,
    FileEvidenceLocator,
    GraphEntityEvidenceLocator,
    SourceRangeEvidenceLocator,
    SymbolEvidenceLocator,
)
from bridger.memory.errors import PersistenceRecoveryError
from bridger.memory.persistence.durability import (
    FleetRuntimeStore,
    _model_bytes,
    _replace_model,
)
from bridger.memory.persistence.recovery import validate_checkpoint
from bridger.navigation.navigator import RepositoryNavigator
from bridger.repository.errors import RepositoryError, SourceReadDeniedError

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _FindingDraft:
    rule_id: str
    subject_kind: str
    subject_ref: str | None
    message: str


def validate_target_candidate(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    target_definition: TargetDefinition,
    navigator: RepositoryNavigator,
    *,
    finalization_request_id: str | None = None,
) -> TargetValidationReport:
    """Validate and durably route one exact Stage 6 candidate submission."""
    request_id = (
        finalization_request_id or target_state.pending_finalization_request_ref
    )
    if request_id is None:
        raise PersistenceRecoveryError(
            "hard validation requires a finalization request identity"
        )

    existing = resolve_validation_report(store, target_spec, request_id)
    if existing is not None:
        return existing

    try:
        with store.target_lock(target_spec.target_task_id):
            request, checkpoint = resolve_validation_subject(
                store,
                target_spec,
                target_state,
                finalization_request_id=request_id,
            )
            _validate_static_authorities(
                store,
                target_spec,
                target_definition,
                navigator,
            )
            if target_state.phase is TargetPhase.FINALIZING:
                _start_validation(store, target_spec, target_state, request)

        findings = _run_candidate_gates(
            store,
            target_spec,
            target_definition,
            checkpoint,
            navigator,
        )
        return _complete_validation(
            store,
            target_spec,
            target_state,
            request,
            findings,
        )
    except PersistenceRecoveryError:
        raise
    except (OSError, RepositoryError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "hard validation could not establish or persist a coherent outcome"
        ) from error


def resolve_validation_subject(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    *,
    finalization_request_id: str | None = None,
) -> tuple[TargetFinalizationRequest, TaskCheckpoint]:
    """Resolve the immutable Stage 6 request and exact candidate checkpoint."""
    if target_state.phase not in {
        TargetPhase.FINALIZING,
        TargetPhase.VALIDATING,
        TargetPhase.REVIEWING,
    }:
        raise PersistenceRecoveryError(
            "hard validation subject is outside an evaluation phase"
        )
    request_id = (
        finalization_request_id or target_state.pending_finalization_request_ref
    )
    if (
        request_id is None
        or target_state.pending_finalization_request_ref != request_id
    ):
        raise PersistenceRecoveryError(
            "hard validation request is not the current pending request"
        )
    try:
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(target_spec, request_id).read_bytes()
        )
        if (
            request.finalization_request_id != request_id
            or request.fleet_run_id != store.fleet_spec.fleet_run_id
            or request.target_task_id != target_spec.target_task_id
            or target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
            or target_state.fleet_run_id != target_spec.fleet_run_id
            or target_state.target_task_id != target_spec.target_task_id
            or target_spec.source != store.fleet_spec.source
        ):
            raise ValueError("validation subject identities do not match")
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
        return request, checkpoint
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "hard validation subject integrity failed"
        ) from error


def resolve_validation_report(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    finalization_request_id: str,
) -> TargetValidationReport | None:
    """Load and verify the one immutable report for a finalization request."""
    report_id = _validation_report_id(finalization_request_id)
    path = store.paths.validation_report(target_spec, report_id)
    if not path.exists():
        return None
    try:
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(
                target_spec,
                finalization_request_id,
            ).read_bytes()
        )
        report = TargetValidationReport.model_validate_json(path.read_bytes())
        if (
            report.validation_report_id != report_id
            or report.fleet_run_id != store.fleet_spec.fleet_run_id
            or report.target_task_id != target_spec.target_task_id
            or report.finalization_request_id != finalization_request_id
            or report.candidate_checkpoint_ref != request.candidate_checkpoint_ref
            or request.fleet_run_id != report.fleet_run_id
            or request.target_task_id != report.target_task_id
        ):
            raise ValueError("validation report identities do not match")
        findings = [
            resolve_validation_finding(
                store,
                target_spec,
                reference.finding_id,
            )
            for reference in report.finding_refs
        ]
        if any(
            finding.finding_id != reference.finding_id
            or finding.validation_report_id != report.validation_report_id
            or finding.target_task_id != report.target_task_id
            for reference, finding in zip(report.finding_refs, findings, strict=True)
        ):
            raise ValueError("validation finding identities do not match")
        return report
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "committed validation report failed integrity validation"
        ) from error


def resolve_validation_finding(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    finding_id: str,
) -> ValidationFinding:
    """Load and verify one immutable hard-validation finding."""
    try:
        finding = ValidationFinding.model_validate_json(
            store.paths.validation_finding(target_spec, finding_id).read_bytes()
        )
        if (
            finding.finding_id != finding_id
            or finding.target_task_id != target_spec.target_task_id
            or target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
        ):
            raise ValueError("validation finding identities do not match")
        return finding
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "validation finding failed integrity validation"
        ) from error


def _validate_static_authorities(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_definition: TargetDefinition,
    navigator: RepositoryNavigator,
) -> None:
    expected_source = (
        target_spec.source.repository_id,
        target_spec.source.repository_revision,
        target_spec.source.graph_snapshot_id,
        target_spec.source.enrichment_overlay_id,
    )
    workspace = Path(target_spec.target_workspace).resolve()
    output_root = Path(store.fleet_spec.output_root).resolve()
    runtime_root = Path(store.fleet_spec.runtime_root).resolve()
    if (
        target_definition.target_id != target_spec.target_id
        or target_definition.target_contract_version
        != target_spec.target_contract_version
        or navigator.source_identity != expected_source
        or workspace == output_root
        or not workspace.is_relative_to(output_root)
        or workspace == runtime_root
        or workspace.is_relative_to(runtime_root)
    ):
        raise PersistenceRecoveryError(
            "hard validation static authorities are incompatible"
        )


def _start_validation(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    request: TargetFinalizationRequest,
) -> None:
    after_state = target_state.model_copy(
        deep=True,
        update={"phase": TargetPhase.VALIDATING},
    )
    store.commit_operation(
        operation_id=_operation_id("validation-start", request.finalization_request_id),
        writes={store.paths.target_state(target_spec): _model_bytes(after_state)},
        event_type="validation_started",
        payload={
            "finalization_request_id": request.finalization_request_id,
            "candidate_checkpoint_ref": request.candidate_checkpoint_ref,
            "from_phase": TargetPhase.FINALIZING.value,
            "to_phase": TargetPhase.VALIDATING.value,
        },
        target_task_id=target_spec.target_task_id,
    )
    _replace_model(target_state, after_state)


def _run_candidate_gates(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_definition: TargetDefinition,
    checkpoint: TaskCheckpoint,
    navigator: RepositoryNavigator,
) -> list[_FindingDraft]:
    evidence_findings, valid_evidence_ids = _validate_evidence(
        target_spec,
        checkpoint.evidence_records,
        navigator,
    )
    findings = [
        *_validate_completion(
            target_spec,
            target_definition,
            checkpoint,
            valid_evidence_ids,
        ),
        *_validate_artifacts(store, target_spec, checkpoint),
        *evidence_findings,
        *_validate_open_questions(target_spec, checkpoint),
    ]
    unique: dict[tuple[str, str, str | None], _FindingDraft] = {}
    for finding in findings:
        key = (finding.rule_id, finding.subject_kind, finding.subject_ref)
        unique.setdefault(key, finding)
    return list(unique.values())


def _validate_completion(
    target_spec: TargetTaskSpec,
    target_definition: TargetDefinition,
    checkpoint: TaskCheckpoint,
    valid_evidence_ids: set[str],
) -> list[_FindingDraft]:
    findings: list[_FindingDraft] = []
    expected = {
        obligation.obligation_id: obligation
        for obligation in target_definition.completion_obligations
    }
    actual = {item.obligation_id: item for item in checkpoint.completion_state.items}
    for obligation_id in sorted(expected.keys() - actual.keys()):
        findings.append(
            _draft(
                "completion.missing_obligation",
                "completion-obligation",
                obligation_id,
                "The submitted completion state omits this obligation.",
            )
        )
    for obligation_id in sorted(actual.keys() - expected.keys()):
        findings.append(
            _draft(
                "completion.unknown_obligation",
                "completion-obligation",
                obligation_id,
                "The submitted completion state contains an unknown obligation.",
            )
        )
    for obligation_id in sorted(expected.keys() & actual.keys()):
        item = actual[obligation_id]
        definition = expected[obligation_id]
        if item.status is CompletionStatus.UNINVESTIGATED:
            findings.append(
                _draft(
                    "completion.uninvestigated",
                    "completion-obligation",
                    obligation_id,
                    "The obligation must leave uninvestigated before validation.",
                )
            )
        elif item.resolution_note is None or not item.resolution_note.strip():
            findings.append(
                _draft(
                    "completion.missing_resolution_note",
                    "completion-obligation",
                    obligation_id,
                    "The terminal completion resolution requires a non-empty note.",
                )
            )
        if (
            item.status is CompletionStatus.NOT_APPLICABLE
            and definition.applicability is not ObligationApplicability.CONDITIONAL
        ):
            findings.append(
                _draft(
                    "completion.invalid_not_applicable",
                    "completion-obligation",
                    obligation_id,
                    "Only a conditional obligation may be not-applicable.",
                )
            )
        for evidence_id in item.evidence_refs:
            if evidence_id not in valid_evidence_ids:
                findings.append(
                    _draft(
                        "evidence.unresolvable",
                        "evidence",
                        evidence_id,
                        "A completion item references evidence that is not valid "
                        "for the submitted candidate.",
                    )
                )
        if item.status is CompletionStatus.COVERED and not any(
            evidence_id in valid_evidence_ids for evidence_id in item.evidence_refs
        ):
            findings.append(
                _draft(
                    "completion.covered_without_evidence",
                    "completion-obligation",
                    obligation_id,
                    "A covered obligation requires at least one valid durable "
                    "evidence reference.",
                )
            )
    return findings


def _validate_artifacts(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    checkpoint: TaskCheckpoint,
) -> list[_FindingDraft]:
    references = checkpoint.task_state.artifact_refs
    if not references:
        return [
            _draft(
                "artifact.missing",
                "target",
                target_spec.target_task_id,
                "The submitted candidate contains no artifacts.",
            )
        ]

    findings: list[_FindingDraft] = []
    artifact_ids: set[str] = set()
    relative_paths: set[str] = set()
    non_empty_markdown = False
    snapshot_root = (
        store.paths.checkpoint_root(target_spec, checkpoint.checkpoint_id) / "artifacts"
    ).resolve()
    for reference in references:
        if reference.artifact_id in artifact_ids:
            findings.append(
                _draft(
                    "artifact.duplicate_id",
                    "artifact",
                    reference.artifact_id,
                    "Candidate artifact identities must be unique.",
                )
            )
        artifact_ids.add(reference.artifact_id)
        if reference.relative_path in relative_paths:
            findings.append(
                _draft(
                    "artifact.duplicate_path",
                    "artifact",
                    reference.relative_path,
                    "Candidate artifact paths must be unique.",
                )
            )
        relative_paths.add(reference.relative_path)

        path_rule = _artifact_path_failure(reference.relative_path)
        if path_rule is not None:
            rule_id, message = path_rule
            findings.append(
                _draft(
                    rule_id,
                    "artifact",
                    reference.artifact_id,
                    message,
                )
            )
        if _DIGEST.fullmatch(reference.digest) is None:
            findings.append(
                _draft(
                    "artifact.invalid_digest",
                    "artifact",
                    reference.artifact_id,
                    "The candidate artifact digest is not a SHA-256 identity.",
                )
            )

        snapshot_path = (snapshot_root / reference.relative_path).resolve()
        content = snapshot_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != reference.digest:
            findings.append(
                _draft(
                    "artifact.digest_mismatch",
                    "artifact",
                    reference.artifact_id,
                    "The checkpointed artifact bytes do not match the recorded digest.",
                )
            )
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                _draft(
                    "artifact.invalid_text",
                    "artifact",
                    reference.artifact_id,
                    "The candidate Markdown is not valid UTF-8 text.",
                )
            )
        else:
            if path_rule is None and decoded.strip():
                non_empty_markdown = True

    if not non_empty_markdown:
        findings.append(
            _draft(
                "artifact.non_empty_markdown_missing",
                "target",
                target_spec.target_task_id,
                "The submitted candidate requires at least one non-empty "
                "Markdown artifact.",
            )
        )
    return findings


def _artifact_path_failure(relative_path: str) -> tuple[str, str] | None:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or relative_path in {"", ".", ".."} or ".." in path.parts:
        return (
            "artifact.outside_workspace",
            "The candidate artifact path escapes the exact target workspace.",
        )
    if (
        path.as_posix() != relative_path
        or relative_path.startswith("./")
        or relative_path.endswith("/")
        or "/./" in relative_path
        or "//" in relative_path
    ):
        return (
            "artifact.invalid_path",
            "The candidate artifact path is not normalized target-relative form.",
        )
    if path.suffix.lower() != ".md":
        return (
            "artifact.invalid_type",
            "Candidate artifacts must be Markdown files.",
        )
    return None


def _validate_evidence(
    target_spec: TargetTaskSpec,
    evidence_records: Sequence[EvidenceReference],
    navigator: RepositoryNavigator,
) -> tuple[list[_FindingDraft], set[str]]:
    findings: list[_FindingDraft] = []
    valid_ids: set[str] = set()
    seen_ids: set[str] = set()
    for evidence in evidence_records:
        if evidence.evidence_id in seen_ids:
            findings.append(
                _draft(
                    "evidence.duplicate",
                    "evidence",
                    evidence.evidence_id,
                    "Candidate evidence identities must be unique.",
                )
            )
            continue
        seen_ids.add(evidence.evidence_id)
        if (
            evidence.target_task_id != target_spec.target_task_id
            or evidence.source != target_spec.source
        ):
            findings.append(
                _draft(
                    "evidence.source_mismatch",
                    "evidence",
                    evidence.evidence_id,
                    "The evidence does not match the target and source binding.",
                )
            )
            continue
        try:
            _resolve_evidence(target_spec, evidence, navigator)
        except (KeyError, SourceReadDeniedError, ValueError):
            findings.append(
                _draft(
                    "evidence.unresolvable",
                    "evidence",
                    evidence.evidence_id,
                    "The evidence locator does not resolve against the bound "
                    "source authorities.",
                )
            )
            continue
        valid_ids.add(evidence.evidence_id)
    return findings, valid_ids


def _resolve_evidence(
    target_spec: TargetTaskSpec,
    evidence: EvidenceReference,
    navigator: RepositoryNavigator,
) -> None:
    locator = evidence.locator
    if evidence.kind is EvidenceKind.FILE and isinstance(locator, FileEvidenceLocator):
        overview = navigator.get_file_overview(locator.path)
        if overview.file.disposition.read_mode == "denied":
            raise ValueError("repository read policy denies evidence")
        return
    if evidence.kind is EvidenceKind.SOURCE_RANGE and isinstance(
        locator, SourceRangeEvidenceLocator
    ):
        result = navigator.read_file_ranges(
            locator.path,
            [(locator.start_line, locator.end_line)],
        )[0]
        if (
            result.revision != target_spec.source.repository_revision
            or result.path != locator.path
            or result.start_line != locator.start_line
            or result.end_line != locator.end_line
            or result.content_digest != locator.content_digest
        ):
            raise ValueError("source range does not resolve exactly")
        return
    if evidence.kind is EvidenceKind.SYMBOL and isinstance(
        locator, SymbolEvidenceLocator
    ):
        result = navigator.read_symbol_excerpt(locator.symbol_id, context_lines=0)
        if result.revision != target_spec.source.repository_revision:
            raise ValueError("symbol belongs to another revision")
        return
    if evidence.kind is EvidenceKind.GRAPH_ENTITY and isinstance(
        locator, GraphEntityEvidenceLocator
    ):
        navigator.get_graph_entity(locator.target_type, locator.target_ref)
        return
    raise ValueError("evidence kind does not match locator")


def _validate_open_questions(
    target_spec: TargetTaskSpec,
    checkpoint: TaskCheckpoint,
) -> list[_FindingDraft]:
    findings: list[_FindingDraft] = []
    seen: set[str] = set()
    for question in checkpoint.open_questions:
        if question.question_id in seen:
            findings.append(
                _draft(
                    "question.duplicate",
                    "open-question",
                    question.question_id,
                    "Checkpointed open-question identities must be unique.",
                )
            )
        seen.add(question.question_id)
        if question.target_task_id != target_spec.target_task_id:
            findings.append(
                _draft(
                    "question.target_mismatch",
                    "open-question",
                    question.question_id,
                    "The open question belongs to another target task.",
                )
            )
    return findings


def _complete_validation(
    store: FleetRuntimeStore,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    request: TargetFinalizationRequest,
    finding_drafts: Sequence[_FindingDraft],
) -> TargetValidationReport:
    with store.target_lock(target_spec.target_task_id):
        existing = resolve_validation_report(
            store,
            target_spec,
            request.finalization_request_id,
        )
        if existing is not None:
            persisted = TargetTaskState.model_validate_json(
                store.paths.target_state(target_spec).read_bytes()
            )
            _replace_validation_state(target_state, persisted)
            return existing
        if (
            target_state.phase is not TargetPhase.VALIDATING
            or target_state.pending_finalization_request_ref
            != request.finalization_request_id
        ):
            raise PersistenceRecoveryError(
                "validation completion requires the same VALIDATING request"
            )

        report_id = _validation_report_id(request.finalization_request_id)
        findings = [
            ValidationFinding(
                finding_id=_finding_id(report_id, draft),
                validation_report_id=report_id,
                target_task_id=target_spec.target_task_id,
                rule_id=draft.rule_id,
                subject_kind=draft.subject_kind,
                subject_ref=draft.subject_ref,
                message=draft.message,
            )
            for draft in finding_drafts
        ]
        finding_refs = [
            FindingRef(
                finding_id=finding.finding_id,
                origin=FindingOrigin.HARD_VALIDATION,
            )
            for finding in findings
        ]
        verdict = ValidationVerdict.FAIL if findings else ValidationVerdict.PASS
        report = TargetValidationReport(
            validation_report_id=report_id,
            fleet_run_id=store.fleet_spec.fleet_run_id,
            target_task_id=target_spec.target_task_id,
            finalization_request_id=request.finalization_request_id,
            candidate_checkpoint_ref=request.candidate_checkpoint_ref,
            verdict=verdict,
            finding_refs=finding_refs,
            created_at=datetime.now(UTC),
        )
        preserved = [
            reference
            for reference in target_state.open_finding_refs
            if reference.origin is not FindingOrigin.HARD_VALIDATION
        ]
        next_phase = (
            TargetPhase.REPAIR
            if verdict is ValidationVerdict.FAIL
            else TargetPhase.REVIEWING
        )
        after_state = target_state.model_copy(
            deep=True,
            update={
                "phase": next_phase,
                "open_finding_refs": [*preserved, *finding_refs],
                "pending_finalization_request_ref": (
                    None
                    if verdict is ValidationVerdict.FAIL
                    else request.finalization_request_id
                ),
            },
        )
        writes = {
            store.paths.validation_finding(target_spec, finding.finding_id): (
                _model_bytes(finding)
            )
            for finding in findings
        }
        writes[store.paths.validation_report(target_spec, report_id)] = _model_bytes(
            report
        )
        writes[store.paths.target_state(target_spec)] = _model_bytes(after_state)
        store.commit_operation(
            operation_id=_operation_id(
                "validation-complete",
                request.finalization_request_id,
            ),
            writes=writes,
            event_type="validation_completed",
            payload={
                "validation_report_id": report.validation_report_id,
                "finalization_request_id": request.finalization_request_id,
                "candidate_checkpoint_ref": request.candidate_checkpoint_ref,
                "verdict": report.verdict.value,
                "from_phase": TargetPhase.VALIDATING.value,
                "to_phase": next_phase.value,
            },
            target_task_id=target_spec.target_task_id,
        )
        _replace_validation_state(target_state, after_state)
        return report


def _replace_validation_state(
    current: TargetTaskState,
    replacement: TargetTaskState,
) -> None:
    if replacement.phase is TargetPhase.REPAIR:
        current.open_finding_refs = replacement.open_finding_refs
        current.phase = replacement.phase
        current.pending_finalization_request_ref = None
    _replace_model(current, replacement)


def _validation_report_id(finalization_request_id: str) -> str:
    digest = hashlib.sha256(finalization_request_id.encode()).hexdigest()
    return f"validation-report-{digest}"


def _finding_id(report_id: str, finding: _FindingDraft) -> str:
    identity = "\0".join(
        (
            report_id,
            finding.rule_id,
            finding.subject_kind,
            finding.subject_ref or "",
        )
    )
    return f"validation-finding-{hashlib.sha256(identity.encode()).hexdigest()}"


def _operation_id(prefix: str, finalization_request_id: str) -> str:
    digest = hashlib.sha256(finalization_request_id.encode()).hexdigest()
    return f"{prefix}-{digest}"


def _draft(
    rule_id: str,
    subject_kind: str,
    subject_ref: str | None,
    message: str,
) -> _FindingDraft:
    return _FindingDraft(
        rule_id=rule_id,
        subject_kind=subject_kind,
        subject_ref=subject_ref,
        message=message,
    )


__all__ = [
    "resolve_validation_finding",
    "resolve_validation_report",
    "resolve_validation_subject",
    "validate_target_candidate",
]
