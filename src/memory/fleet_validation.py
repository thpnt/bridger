"""Deterministic Stage 11 validation of the exact locally accepted fleet."""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from memory.acceptance import resolve_accepted_target_result
from memory.durability import FleetRuntimeStore, _model_bytes, _replace_model
from memory.errors import FleetValidationError, PersistenceRecoveryError
from memory.recovery import validate_checkpoint
from models.acceptance import AcceptedTargetResult
from models.fleet_validation import FleetValidationFinding, FleetValidationReport
from models.memory import (
    CandidateArtifactRef,
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from models.persistence import TargetFinalizationRequest
from models.validation import ValidationVerdict

_INLINE_LINK = re.compile(
    r"(?<!!)\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
_REFERENCE_DEFINITION = re.compile(
    r"(?m)^[ ]{0,3}\[([^\]\n]+)\]:[ \t]*(<[^>\n]+>|[^ \t\n]+)"
)
_REFERENCE_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]")
_SHORTCUT_REFERENCE = re.compile(r"(?<!!)\[([^\]\n]+)\](?![\[(])")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class _AcceptedArtifact:
    owner: TargetTaskSpec
    reference: CandidateArtifactRef
    fleet_path: str
    content: str


@dataclass(frozen=True)
class _FindingDraft:
    rule_id: str
    affected_target_task_ids: tuple[str, ...]
    subject_kind: str
    subject_ref: str | None
    message: str


def validate_fleet(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> FleetValidationReport:
    """Validate, persist, and route the exact current accepted fleet."""
    try:
        with store.state_locks():
            current = _load_current_fleet_state(store, fleet_state)
            target_specs = store.load_target_specs()
            target_states = _load_target_states(store, target_specs)

            if current.phase is FleetPhase.REVIEWING:
                results = _resolve_accepted_fleet(
                    store,
                    current,
                    target_specs,
                    target_states,
                )
                report = _require_existing_report(
                    store,
                    [result.accepted_target_result_id for result in results],
                    ValidationVerdict.PASS,
                )
                _require_clear_projection(current, target_states)
                _replace_model(fleet_state, current)
                return report

            if current.phase not in {
                FleetPhase.RUNNING,
                FleetPhase.VALIDATING,
                FleetPhase.REPAIRING,
            }:
                raise FleetValidationError(
                    "fleet validation requires RUNNING fleet admission"
                )

            results = _resolve_accepted_fleet(
                store,
                current,
                target_specs,
                target_states,
            )
            accepted_refs = [result.accepted_target_result_id for result in results]
            report_id = _fleet_validation_report_id(
                store.fleet_spec.fleet_run_id,
                accepted_refs,
            )

            if current.phase is FleetPhase.REPAIRING:
                report = _require_existing_report(
                    store,
                    accepted_refs,
                    ValidationVerdict.FAIL,
                )
                _route_failed_fleet(
                    store,
                    fleet_state,
                    current,
                    target_specs,
                    target_states,
                    report,
                )
                return report

            if current.phase is FleetPhase.RUNNING:
                _start_fleet_validation(
                    store,
                    fleet_state,
                    current,
                    accepted_refs,
                    report_id,
                )

            existing = resolve_fleet_validation_report(
                store,
                accepted_refs,
            )
            if existing is None:
                artifacts, path_findings = _build_artifact_index(
                    store,
                    target_specs,
                    results,
                )
                finding_drafts = [
                    *path_findings,
                    *_validate_markdown_links(artifacts),
                ]
                existing = _commit_fleet_validation(
                    store,
                    fleet_state,
                    target_specs,
                    target_states,
                    accepted_refs,
                    finding_drafts,
                )
                current = FleetRunState.model_validate_json(
                    store.paths.fleet_state.read_bytes()
                )
            elif current.phase is FleetPhase.VALIDATING:
                current = _commit_existing_report_state(
                    store,
                    fleet_state,
                    current,
                    target_specs,
                    target_states,
                    existing,
                )

            if existing.verdict is ValidationVerdict.FAIL:
                target_states = _load_target_states(store, target_specs)
                _route_failed_fleet(
                    store,
                    fleet_state,
                    current,
                    target_specs,
                    target_states,
                    existing,
                )
            return existing
    except (FleetValidationError, PersistenceRecoveryError):
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "fleet validation could not establish or persist a coherent outcome"
        ) from error


def resolve_fleet_validation_report(
    store: FleetRuntimeStore,
    accepted_target_result_refs: Sequence[str],
) -> FleetValidationReport | None:
    """Load the immutable report for one exact ordered accepted fleet."""
    report_id = _fleet_validation_report_id(
        store.fleet_spec.fleet_run_id,
        accepted_target_result_refs,
    )
    path = store.paths.fleet_validation_report(report_id)
    if not path.exists():
        return None
    try:
        report = FleetValidationReport.model_validate_json(path.read_bytes())
        if (
            report.fleet_validation_report_id != report_id
            or report.fleet_run_id != store.fleet_spec.fleet_run_id
            or report.accepted_target_result_refs != list(accepted_target_result_refs)
        ):
            raise ValueError("fleet validation report identities do not match")
        fleet_task_ids = {
            target_spec.target_task_id for target_spec in store.load_target_specs()
        }
        for reference in report.finding_refs:
            finding = resolve_fleet_validation_finding(
                store,
                reference.finding_id,
            )
            if (
                finding.fleet_validation_report_id != report_id
                or finding.fleet_run_id != report.fleet_run_id
                or not set(finding.affected_target_task_ids).issubset(fleet_task_ids)
            ):
                raise ValueError("fleet validation finding identities do not match")
        return report
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "committed fleet validation report failed integrity validation"
        ) from error


def resolve_fleet_validation_finding(
    store: FleetRuntimeStore,
    finding_id: str,
) -> FleetValidationFinding:
    """Load and verify one immutable Stage 11 fleet finding."""
    try:
        finding = FleetValidationFinding.model_validate_json(
            store.paths.fleet_validation_finding(finding_id).read_bytes()
        )
        if (
            finding.finding_id != finding_id
            or finding.fleet_run_id != store.fleet_spec.fleet_run_id
        ):
            raise ValueError("fleet validation finding identities do not match")
        fleet_task_ids = {
            target_spec.target_task_id for target_spec in store.load_target_specs()
        }
        if not set(finding.affected_target_task_ids).issubset(fleet_task_ids):
            raise ValueError("fleet validation finding affects another fleet")
        return finding
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "fleet validation finding failed integrity validation"
        ) from error


def _load_current_fleet_state(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> FleetRunState:
    current = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    if (
        current.fleet_run_id != store.fleet_spec.fleet_run_id
        or fleet_state.fleet_run_id != current.fleet_run_id
    ):
        raise ValueError("fleet validation authorities identify different fleets")
    return current


def _load_target_states(
    store: FleetRuntimeStore,
    target_specs: Sequence[TargetTaskSpec],
) -> list[TargetTaskState]:
    return [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target_spec).read_bytes()
        )
        for target_spec in target_specs
    ]


def _resolve_accepted_fleet(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
) -> list[AcceptedTargetResult]:
    if (
        len(target_specs) != len(store.fleet_spec.target_ids)
        or len(target_states) != len(target_specs)
        or fleet_state.target_task_ids
        != [target_spec.target_task_id for target_spec in target_specs]
    ):
        raise PersistenceRecoveryError(
            "fleet validation target inventory is inconsistent"
        )
    results: list[AcceptedTargetResult] = []
    for target_id, target_spec, target_state in zip(
        store.fleet_spec.target_ids,
        target_specs,
        target_states,
        strict=True,
    ):
        if (
            target_spec.target_id != target_id
            or target_spec.fleet_run_id != store.fleet_spec.fleet_run_id
            or target_state.target_task_id != target_spec.target_task_id
            or target_state.fleet_run_id != target_spec.fleet_run_id
            or target_spec.source != store.fleet_spec.source
        ):
            raise PersistenceRecoveryError(
                "fleet validation target identities are inconsistent"
            )
        if target_state.phase is not TargetPhase.ACCEPTED:
            raise FleetValidationError(
                "fleet validation requires every activated target to be ACCEPTED"
            )
        result_id = target_state.last_accepted_result_ref
        if result_id is None:
            raise PersistenceRecoveryError(
                "accepted target has no accepted-result reference"
            )
        results.append(resolve_accepted_target_result(store, target_spec, result_id))
    return results


def _start_fleet_validation(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    current: FleetRunState,
    accepted_refs: Sequence[str],
    report_id: str,
) -> None:
    if current.phase is not FleetPhase.RUNNING:
        raise FleetValidationError("fleet validation can start only from RUNNING")
    after = current.model_copy(update={"phase": FleetPhase.VALIDATING})
    store.commit_operation(
        operation_id=_operation_id("fleet-validation-start", report_id),
        writes={store.paths.fleet_state: _model_bytes(after)},
        event_type="fleet_validation_started",
        payload={
            "accepted_target_result_refs": list(accepted_refs),
            "from_phase": FleetPhase.RUNNING.value,
            "to_phase": FleetPhase.VALIDATING.value,
        },
    )
    _replace_model(current, after)
    _replace_model(fleet_state, after)


def _build_artifact_index(
    store: FleetRuntimeStore,
    target_specs: Sequence[TargetTaskSpec],
    results: Sequence[AcceptedTargetResult],
) -> tuple[dict[str, _AcceptedArtifact], list[_FindingDraft]]:
    artifacts: dict[str, _AcceptedArtifact] = {}
    owners_by_path: dict[str, list[str]] = {}
    findings: list[_FindingDraft] = []
    for target_spec, result in zip(target_specs, results, strict=True):
        request = TargetFinalizationRequest.model_validate_json(
            store.paths.finalization_request(
                target_spec,
                result.finalization_request_ref,
            ).read_bytes()
        )
        if (
            request.finalization_request_id != result.finalization_request_ref
            or request.fleet_run_id != result.fleet_run_id
            or request.target_task_id != result.target_task_id
        ):
            raise ValueError("accepted result finalization provenance is inconsistent")
        checkpoint = validate_checkpoint(
            store,
            target_spec,
            request.candidate_checkpoint_ref,
        )
        if checkpoint.task_state.artifact_refs != result.artifact_refs:
            raise ValueError("accepted artifact set differs from its checkpoint")
        snapshot_root = (
            store.paths.checkpoint_root(target_spec, checkpoint.checkpoint_id)
            / "artifacts"
        )
        for reference in result.artifact_refs:
            fleet_path, path_failure = _fleet_artifact_path(
                target_spec.target_id,
                reference.relative_path,
            )
            if path_failure is not None:
                findings.append(
                    _finding(
                        "artifact.invalid_fleet_path",
                        (target_spec.target_task_id,),
                        "fleet-path",
                        fleet_path,
                        path_failure,
                    )
                )
                continue
            content_bytes = (snapshot_root / reference.relative_path).read_bytes()
            if hashlib.sha256(content_bytes).hexdigest() != reference.digest:
                raise ValueError("accepted artifact bytes do not match their digest")
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("accepted Markdown is not valid UTF-8") from error
            accepted_artifact = _AcceptedArtifact(
                owner=target_spec,
                reference=reference,
                fleet_path=fleet_path,
                content=content,
            )
            owners = owners_by_path.setdefault(fleet_path, [])
            owners.append(target_spec.target_task_id)
            artifacts.setdefault(fleet_path, accepted_artifact)

    for fleet_path, owners in owners_by_path.items():
        if len(owners) > 1:
            findings.append(
                _finding(
                    "artifact.path_collision",
                    tuple(dict.fromkeys(owners)),
                    "fleet-path",
                    fleet_path,
                    "Multiple accepted artifacts resolve to this generated-memory "
                    "path; reorganize an affected target so every fleet path is "
                    "unique.",
                )
            )
    return artifacts, _unique_findings(findings)


def _fleet_artifact_path(
    target_id: str,
    relative_path: str,
) -> tuple[str, str | None]:
    fleet_path = f"{target_id}/{relative_path}"
    path = PurePosixPath(fleet_path)
    if (
        "\\" in fleet_path
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != fleet_path
        or posixpath.normpath(fleet_path) != fleet_path
    ):
        return (
            fleet_path,
            "The accepted artifact does not resolve to a normalized path inside "
            "the generated-memory namespace.",
        )
    return fleet_path, None


def _validate_markdown_links(
    artifacts: Mapping[str, _AcceptedArtifact],
) -> list[_FindingDraft]:
    findings: list[_FindingDraft] = []
    for artifact in artifacts.values():
        for destination in _markdown_link_destinations(artifact.content):
            failure = _resolve_link(artifact.fleet_path, destination, artifacts)
            if failure is None:
                continue
            rule_id, resolved_destination, message = failure
            findings.append(
                _finding(
                    rule_id,
                    (artifact.owner.target_task_id,),
                    "link",
                    f"{artifact.fleet_path} -> {resolved_destination}",
                    message,
                )
            )
    return _unique_findings(findings)


def _markdown_link_destinations(content: str) -> list[str]:
    searchable = _remove_markdown_code(content)
    definitions = {
        _reference_label(match.group(1)): _strip_angle_destination(match.group(2))
        for match in _REFERENCE_DEFINITION.finditer(searchable)
    }
    destinations: list[str] = []
    occupied: list[tuple[int, int]] = []
    for match in _INLINE_LINK.finditer(searchable):
        if match.start() > 0 and searchable[match.start() - 1] == "\\":
            continue
        destinations.append(_strip_angle_destination(match.group(1)))
        occupied.append(match.span())
    for match in _REFERENCE_LINK.finditer(searchable):
        if _span_overlaps(match.span(), occupied):
            continue
        label = match.group(2) or match.group(1)
        destination = definitions.get(_reference_label(label))
        if destination is not None:
            destinations.append(destination)
            occupied.append(match.span())
    for match in _SHORTCUT_REFERENCE.finditer(searchable):
        if _span_overlaps(match.span(), occupied):
            continue
        if match.end() < len(searchable) and searchable[match.end()] == ":":
            continue
        destination = definitions.get(_reference_label(match.group(1)))
        if destination is not None:
            destinations.append(destination)
    return destinations


def _strip_angle_destination(destination: str) -> str:
    if destination.startswith("<") and destination.endswith(">"):
        return destination[1:-1]
    return destination


def _reference_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def _span_overlaps(
    span: tuple[int, int],
    occupied: Sequence[tuple[int, int]],
) -> bool:
    return any(span[0] < end and start < span[1] for start, end in occupied)


def _remove_markdown_code(content: str) -> str:
    lines: list[str] = []
    fence: str | None = None
    for line in content.splitlines(keepends=True):
        stripped = line.lstrip(" ")
        marker = stripped[:3]
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            lines.append("\n" if line.endswith("\n") else "")
            continue
        if len(line) - len(stripped) <= 3 and marker in {"```", "~~~"}:
            fence = marker
            lines.append("\n" if line.endswith("\n") else "")
            continue
        lines.append(_remove_inline_code(line))
    return "".join(lines)


def _remove_inline_code(line: str) -> str:
    result = list(line)
    index = 0
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        marker = line[index:run_end]
        closing = line.find(marker, run_end)
        if closing == -1:
            index = run_end
            continue
        for position in range(index, closing + len(marker)):
            if result[position] not in {"\n", "\r"}:
                result[position] = " "
        index = closing + len(marker)
    return "".join(result)


def _resolve_link(
    source_path: str,
    destination: str,
    artifacts: Mapping[str, _AcceptedArtifact],
) -> tuple[str, str, str] | None:
    if not destination or destination.startswith("#"):
        return None
    if _URI_SCHEME.match(destination) or destination.startswith("//"):
        return None
    if (
        "\\" in destination
        or "\x00" in destination
        or _INVALID_PERCENT_ESCAPE.search(destination)
    ):
        return (
            "link.invalid_path",
            destination,
            "This Markdown link is not a structurally valid generated-memory path.",
        )
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return None
    link_path = unquote(parsed.path)
    if "\\" in link_path or "\x00" in link_path:
        return (
            "link.invalid_path",
            link_path,
            "This Markdown link is not a structurally valid generated-memory path.",
        )
    if not link_path:
        return None
    if link_path.startswith("/"):
        return (
            "link.outside_fleet",
            link_path,
            "This Markdown link escapes the generated-memory namespace; use a "
            "relative path to an accepted fleet artifact.",
        )
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(source_path), link_path)
    )
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        return (
            "link.outside_fleet",
            resolved,
            "This Markdown link escapes the generated-memory namespace; use a "
            "relative path to an accepted fleet artifact.",
        )
    if resolved not in artifacts:
        return (
            "link.missing_destination",
            resolved,
            "This Markdown link does not resolve to an artifact in the exact "
            "currently accepted fleet.",
        )
    return None


def _commit_fleet_validation(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    accepted_refs: Sequence[str],
    finding_drafts: Sequence[_FindingDraft],
) -> FleetValidationReport:
    current = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    if current.phase is not FleetPhase.VALIDATING:
        raise PersistenceRecoveryError(
            "fleet validation completion requires VALIDATING phase"
        )
    report_id = _fleet_validation_report_id(
        store.fleet_spec.fleet_run_id,
        accepted_refs,
    )
    findings = [
        FleetValidationFinding(
            finding_id=_finding_id(report_id, draft),
            fleet_validation_report_id=report_id,
            fleet_run_id=store.fleet_spec.fleet_run_id,
            rule_id=draft.rule_id,
            affected_target_task_ids=list(draft.affected_target_task_ids),
            subject_kind=draft.subject_kind,
            subject_ref=draft.subject_ref,
            message=draft.message,
        )
        for draft in _unique_findings(finding_drafts)
    ]
    finding_refs = [
        FindingRef(
            finding_id=finding.finding_id,
            origin=FindingOrigin.FLEET_VALIDATION,
        )
        for finding in findings
    ]
    verdict = ValidationVerdict.FAIL if findings else ValidationVerdict.PASS
    report = FleetValidationReport(
        fleet_validation_report_id=report_id,
        fleet_run_id=store.fleet_spec.fleet_run_id,
        accepted_target_result_refs=list(accepted_refs),
        verdict=verdict,
        finding_refs=finding_refs,
    )
    _commit_report_state(
        store,
        fleet_state,
        current,
        target_specs,
        target_states,
        report,
        findings,
    )
    return report


def _commit_existing_report_state(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    current: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    report: FleetValidationReport,
) -> FleetRunState:
    findings = [
        resolve_fleet_validation_finding(store, reference.finding_id)
        for reference in report.finding_refs
    ]
    return _commit_report_state(
        store,
        fleet_state,
        current,
        target_specs,
        target_states,
        report,
        findings,
        persist_report=False,
    )


def _commit_report_state(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    current: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    report: FleetValidationReport,
    findings: Sequence[FleetValidationFinding],
    *,
    persist_report: bool = True,
) -> FleetRunState:
    next_phase = (
        FleetPhase.REPAIRING
        if report.verdict is ValidationVerdict.FAIL
        else FleetPhase.REVIEWING
    )
    preserved_fleet = _without_fleet_validation(current.open_finding_refs)
    after_fleet = current.model_copy(
        deep=True,
        update={
            "phase": next_phase,
            "open_finding_refs": [*preserved_fleet, *report.finding_refs],
        },
    )
    writes = {store.paths.fleet_state: _model_bytes(after_fleet)}
    if persist_report:
        writes[
            store.paths.fleet_validation_report(report.fleet_validation_report_id)
        ] = _model_bytes(report)
        for finding in findings:
            writes[store.paths.fleet_validation_finding(finding.finding_id)] = (
                _model_bytes(finding)
            )
    if report.verdict is ValidationVerdict.PASS:
        for target_spec, target_state in zip(
            target_specs,
            target_states,
            strict=True,
        ):
            after_target = target_state.model_copy(
                deep=True,
                update={
                    "open_finding_refs": _without_fleet_validation(
                        target_state.open_finding_refs
                    )
                },
            )
            writes[store.paths.target_state(target_spec)] = _model_bytes(after_target)
    store.commit_operation(
        operation_id=_operation_id(
            "fleet-validation-complete",
            report.fleet_validation_report_id,
        ),
        writes=writes,
        event_type="fleet_validation_completed",
        payload={
            "fleet_validation_report_id": report.fleet_validation_report_id,
            "accepted_target_result_refs": report.accepted_target_result_refs,
            "verdict": report.verdict.value,
            "from_phase": FleetPhase.VALIDATING.value,
            "to_phase": next_phase.value,
        },
    )
    _replace_model(fleet_state, after_fleet)
    return after_fleet


def _route_failed_fleet(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    current: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    report: FleetValidationReport,
) -> None:
    persisted = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    if persisted.phase is FleetPhase.RUNNING:
        _replace_model(fleet_state, persisted)
        return
    if persisted.phase is not FleetPhase.REPAIRING or current.phase not in {
        FleetPhase.REPAIRING,
        FleetPhase.VALIDATING,
    }:
        raise PersistenceRecoveryError(
            "fleet repair routing requires committed REPAIRING state"
        )
    findings = [
        resolve_fleet_validation_finding(store, reference.finding_id)
        for reference in report.finding_refs
    ]
    refs_by_target: dict[str, list[FindingRef]] = {}
    for reference, finding in zip(report.finding_refs, findings, strict=True):
        for target_task_id in finding.affected_target_task_ids:
            refs_by_target.setdefault(target_task_id, []).append(reference)
    known_task_ids = {spec.target_task_id for spec in target_specs}
    if not refs_by_target or not set(refs_by_target).issubset(known_task_ids):
        raise PersistenceRecoveryError(
            "fleet validation findings cannot be routed to this fleet"
        )

    writes: dict[Path, bytes] = {}
    for target_spec, target_state in zip(
        target_specs,
        target_states,
        strict=True,
    ):
        if target_state.phase is not TargetPhase.ACCEPTED:
            raise PersistenceRecoveryError(
                "fleet repair routing requires accepted target states"
            )
        current_refs = _without_fleet_validation(target_state.open_finding_refs)
        routed_refs = refs_by_target.get(target_spec.target_task_id, [])
        after_target = target_state.model_copy(
            deep=True,
            update={
                "phase": (TargetPhase.REPAIR if routed_refs else TargetPhase.ACCEPTED),
                "open_finding_refs": [*current_refs, *routed_refs],
            },
        )
        writes[store.paths.target_state(target_spec)] = _model_bytes(after_target)
    after_fleet = persisted.model_copy(update={"phase": FleetPhase.RUNNING})
    writes[store.paths.fleet_state] = _model_bytes(after_fleet)
    store.commit_operation(
        operation_id=_operation_id(
            "fleet-repair-route",
            report.fleet_validation_report_id,
        ),
        writes=writes,
        event_type="fleet_repair_routed",
        payload={
            "fleet_validation_report_id": report.fleet_validation_report_id,
            "affected_target_task_ids": [
                target_spec.target_task_id
                for target_spec in target_specs
                if target_spec.target_task_id in refs_by_target
            ],
            "from_phase": FleetPhase.REPAIRING.value,
            "to_phase": FleetPhase.RUNNING.value,
        },
    )
    _replace_model(fleet_state, after_fleet)


def _require_existing_report(
    store: FleetRuntimeStore,
    accepted_refs: Sequence[str],
    verdict: ValidationVerdict,
) -> FleetValidationReport:
    report = resolve_fleet_validation_report(store, accepted_refs)
    if report is None or report.verdict is not verdict:
        raise PersistenceRecoveryError(
            "fleet phase lacks an applicable fleet-validation report"
        )
    return report


def _require_clear_projection(
    fleet_state: FleetRunState,
    target_states: Sequence[TargetTaskState],
) -> None:
    if any(
        reference.origin is FindingOrigin.FLEET_VALIDATION
        for reference in fleet_state.open_finding_refs
    ) or any(
        reference.origin is FindingOrigin.FLEET_VALIDATION
        for target_state in target_states
        for reference in target_state.open_finding_refs
    ):
        raise PersistenceRecoveryError(
            "reviewing fleet retains current fleet-validation findings"
        )


def _without_fleet_validation(
    references: Sequence[FindingRef],
) -> list[FindingRef]:
    return [
        reference
        for reference in references
        if reference.origin is not FindingOrigin.FLEET_VALIDATION
    ]


def _fleet_validation_report_id(
    fleet_run_id: str,
    accepted_refs: Sequence[str],
) -> str:
    identity = "\0".join((fleet_run_id, *accepted_refs))
    return f"fleet-validation-report-{hashlib.sha256(identity.encode()).hexdigest()}"


def _finding_id(report_id: str, finding: _FindingDraft) -> str:
    identity = "\0".join(
        (
            report_id,
            finding.rule_id,
            ",".join(finding.affected_target_task_ids),
            finding.subject_kind,
            finding.subject_ref or "",
        )
    )
    return f"fleet-validation-finding-{hashlib.sha256(identity.encode()).hexdigest()}"


def _operation_id(prefix: str, report_id: str) -> str:
    digest = hashlib.sha256(report_id.encode()).hexdigest()
    return f"{prefix}-{digest}"


def _finding(
    rule_id: str,
    affected_target_task_ids: tuple[str, ...],
    subject_kind: str,
    subject_ref: str | None,
    message: str,
) -> _FindingDraft:
    return _FindingDraft(
        rule_id=rule_id,
        affected_target_task_ids=affected_target_task_ids,
        subject_kind=subject_kind,
        subject_ref=subject_ref,
        message=message,
    )


def _unique_findings(
    findings: Sequence[_FindingDraft],
) -> list[_FindingDraft]:
    unique: dict[tuple[object, ...], _FindingDraft] = {}
    for finding in findings:
        key = (
            finding.rule_id,
            finding.affected_target_task_ids,
            finding.subject_kind,
            finding.subject_ref,
        )
        unique.setdefault(key, finding)
    return list(unique.values())


__all__ = [
    "resolve_fleet_validation_finding",
    "resolve_fleet_validation_report",
    "validate_fleet",
]
