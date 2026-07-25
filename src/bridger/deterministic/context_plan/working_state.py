"""Validated mutation and atomic persistence for Context Plan working state."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from bridger.artifacts import write_artifact
from bridger.models.working_state import (
    ContextPlanWorkingState,
    EvidenceLineRange,
    EvidenceRecord,
    EvidenceStatus,
    FileInspectionStatus,
    FindingStatus,
    InspectedFileState,
    InspectionLevel,
    PackageCandidateStatus,
    QuestionStatus,
    RelationshipStatus,
)


class WorkingStateValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def merge_line_ranges(
    ranges: list[EvidenceLineRange],
) -> list[EvidenceLineRange]:
    ordered = sorted(ranges, key=lambda item: (item.line_start, item.line_end))
    merged: list[EvidenceLineRange] = []
    for item in ordered:
        if not merged or item.line_start > merged[-1].line_end + 1:
            merged.append(item)
            continue
        previous = merged[-1]
        merged[-1] = EvidenceLineRange(
            line_start=previous.line_start,
            line_end=max(previous.line_end, item.line_end),
        )
    return merged


def validate_working_state(state: ContextPlanWorkingState) -> None:
    issues: list[str] = []
    collections = {
        "evidence": [item.evidence_id for item in state.evidence],
        "findings": [item.finding_id for item in state.findings],
        "relationships": [item.relationship_id for item in state.relationships],
        "open_questions": [item.question_id for item in state.open_questions],
        "package_candidates": [item.candidate_id for item in state.package_candidates],
    }
    for name, values in collections.items():
        duplicates = sorted(
            value for value, count in Counter(values).items() if count > 1
        )
        if duplicates:
            issues.append(f"{name} contains duplicate IDs: {', '.join(duplicates)}")

    evidence = {item.evidence_id: item for item in state.evidence}
    findings = {item.finding_id: item for item in state.findings}
    questions = {item.question_id: item for item in state.open_questions}
    candidates = {item.candidate_id: item for item in state.package_candidates}

    def validate_evidence_ids(owner: str, values: list[str], *, active: bool) -> None:
        for evidence_id in values:
            record = evidence.get(evidence_id)
            if record is None:
                issues.append(f"{owner} references missing evidence {evidence_id}")
            elif active and record.status is not EvidenceStatus.ACTIVE:
                issues.append(
                    f"{owner} actively references {record.status.value} evidence "
                    f"{evidence_id}"
                )

    for finding_item in state.findings:
        validate_evidence_ids(
            f"finding {finding_item.finding_id}",
            finding_item.evidence_ids,
            active=finding_item.status is FindingStatus.ACTIVE,
        )
        if (
            finding_item.supersedes is not None
            and finding_item.supersedes not in findings
        ):
            issues.append(
                f"finding {finding_item.finding_id} supersedes missing finding "
                f"{finding_item.supersedes}"
            )
        elif finding_item.supersedes == finding_item.finding_id:
            issues.append(f"finding {finding_item.finding_id} cannot supersede itself")
    for relationship_item in state.relationships:
        validate_evidence_ids(
            f"relationship {relationship_item.relationship_id}",
            relationship_item.evidence_ids,
            active=relationship_item.status is RelationshipStatus.ACTIVE,
        )
    for question_item in state.open_questions:
        validate_evidence_ids(
            f"question {question_item.question_id}",
            [
                *question_item.related_evidence_ids,
                *question_item.resolution_evidence_ids,
            ],
            active=question_item.status
            in {QuestionStatus.OPEN, QuestionStatus.RESOLVED},
        )
    for candidate_item in state.package_candidates:
        active = candidate_item.status is PackageCandidateStatus.ACTIVE
        validate_evidence_ids(
            f"candidate {candidate_item.candidate_id}",
            candidate_item.evidence_ids,
            active=active,
        )
        for finding_id in candidate_item.finding_ids:
            finding = findings.get(finding_id)
            if finding is None:
                issues.append(
                    f"candidate {candidate_item.candidate_id} references missing "
                    f"finding {finding_id}"
                )
            elif active and finding.status is not FindingStatus.ACTIVE:
                issues.append(
                    f"active candidate {candidate_item.candidate_id} references "
                    f"{finding.status.value} finding {finding_id}"
                )
        for question_id in candidate_item.question_ids:
            if question_id not in questions:
                issues.append(
                    f"candidate {candidate_item.candidate_id} references missing "
                    f"question {question_id}"
                )
        if candidate_item.merged_into is not None:
            target = candidates.get(candidate_item.merged_into)
            if target is None:
                issues.append(
                    f"candidate {candidate_item.candidate_id} merged into missing "
                    f"candidate {candidate_item.merged_into}"
                )
            elif candidate_item.status is not PackageCandidateStatus.MERGED:
                issues.append(
                    f"candidate {candidate_item.candidate_id} has merged_into "
                    "without merged status"
                )
        elif candidate_item.status is PackageCandidateStatus.MERGED:
            issues.append(
                f"merged candidate {candidate_item.candidate_id} has no merge target"
            )
    if issues:
        raise WorkingStateValidationError(issues)


def canonicalize_working_state(
    state: ContextPlanWorkingState,
) -> ContextPlanWorkingState:
    return state.model_copy(
        update={
            "evidence": sorted(state.evidence, key=lambda item: item.evidence_id),
            "inspected_files": sorted(
                state.inspected_files, key=lambda item: item.path
            ),
            "findings": sorted(state.findings, key=lambda item: item.finding_id),
            "relationships": sorted(
                state.relationships, key=lambda item: item.relationship_id
            ),
            "open_questions": sorted(
                state.open_questions, key=lambda item: item.question_id
            ),
            "package_candidates": sorted(
                state.package_candidates, key=lambda item: item.candidate_id
            ),
        }
    )


class WorkingStateStore:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.checksum: str | None = None

    def persist(self, state: ContextPlanWorkingState) -> str:
        canonical = canonicalize_working_state(state)
        validate_working_state(canonical)
        write_artifact(self.destination, canonical)
        self.checksum = sha256(self.destination.read_bytes()).hexdigest()
        return self.checksum

    def load(self) -> ContextPlanWorkingState:
        state = ContextPlanWorkingState.model_validate_json(
            self.destination.read_bytes()
        )
        validate_working_state(state)
        self.checksum = sha256(self.destination.read_bytes()).hexdigest()
        return canonicalize_working_state(state)


class WorkingStateMutationService:
    """Apply narrow mutations and persist every successfully changed state."""

    def __init__(
        self,
        state: ContextPlanWorkingState,
        store: WorkingStateStore,
        *,
        total_lines_by_path: dict[str, int] | None = None,
    ) -> None:
        validate_working_state(state)
        self.state = canonicalize_working_state(state)
        self.store = store
        self.total_lines_by_path = total_lines_by_path or {}
        self.store.persist(self.state)

    def apply_evidence(
        self,
        records: list[EvidenceRecord],
        *,
        now: datetime | None = None,
    ) -> list[str]:
        existing = {item.evidence_id for item in self.state.evidence}
        new_records = [item for item in records if item.evidence_id not in existing]
        if not new_records:
            return []
        timestamp = now or datetime.now(UTC)
        next_sequence = self.state.mutation_sequence
        sequenced: list[EvidenceRecord] = []
        for record in new_records:
            next_sequence += 1
            sequenced.append(
                record.model_copy(update={"sequence_number": next_sequence})
            )
        updated_files = list(self.state.inspected_files)
        for record in sequenced:
            updated_files = self._apply_inspection(updated_files, record)
        candidate = self.state.model_copy(
            update={
                "evidence": [*self.state.evidence, *sequenced],
                "inspected_files": updated_files,
                "mutation_sequence": next_sequence,
                "updated_at": timestamp,
            }
        )
        self._commit(candidate)
        return [item.evidence_id for item in sequenced]

    def commit(self, candidate: ContextPlanWorkingState) -> None:
        self._commit(candidate)

    def next_sequence(self) -> int:
        return self.state.mutation_sequence + 1

    def _commit(self, candidate: ContextPlanWorkingState) -> None:
        canonical = canonicalize_working_state(candidate)
        validate_working_state(canonical)
        self.store.persist(canonical)
        self.state = canonical

    def _apply_inspection(
        self,
        files: list[InspectedFileState],
        record: EvidenceRecord,
    ) -> list[InspectedFileState]:
        if record.path is None:
            return files
        by_path = {item.path: item for item in files}
        if record.path not in by_path and record.inspection_level in {
            InspectionLevel.DISCOVERED,
            InspectionLevel.LOCATED,
        }:
            return files
        current = by_path.get(
            record.path,
            InspectedFileState(
                path=record.path,
                total_lines=self.total_lines_by_path.get(record.path),
            ),
        )
        observed_ranges = (
            record.line_ranges
            if record.inspection_level
            in {
                InspectionLevel.LINE_OBSERVED,
                InspectionLevel.EXCERPT_INSPECTED,
                InspectionLevel.IMPLEMENTATION_INSPECTED,
            }
            else []
        )
        ranges = merge_line_ranges([*current.inspected_ranges, *observed_ranges])
        seen = set(current.symbol_ids_seen)
        inspected = set(current.symbol_ids_inspected)
        if record.symbol_id is not None:
            seen.add(record.symbol_id)
            if record.source_tool == "get_symbol":
                inspected.add(record.symbol_id)
        status = current.inspection_status
        if record.inspection_level is InspectionLevel.IMPLEMENTATION_INSPECTED:
            status = FileInspectionStatus.IMPLEMENTATION_INSPECTED
        elif record.inspection_level in {
            InspectionLevel.LINE_OBSERVED,
            InspectionLevel.EXCERPT_INSPECTED,
        }:
            if status is not FileInspectionStatus.IMPLEMENTATION_INSPECTED:
                status = FileInspectionStatus.PARTIALLY_INSPECTED
        elif (
            record.inspection_level is InspectionLevel.SYMBOL_ONLY
            and status is FileInspectionStatus.DISCOVERED
        ):
            status = FileInspectionStatus.SYMBOL_ONLY
        observed_lines = sum(item.line_end - item.line_start + 1 for item in ranges)
        by_path[record.path] = current.model_copy(
            update={
                "inspected_ranges": ranges,
                "observed_lines": observed_lines,
                "symbol_ids_seen": sorted(seen),
                "symbol_ids_inspected": sorted(inspected),
                "inspection_status": status,
            }
        )
        return list(by_path.values())
