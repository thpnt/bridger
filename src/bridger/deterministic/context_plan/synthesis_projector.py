"""Deterministic, coverage-balanced projection of Context Plan working state."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256

from bridger.deterministic.context_plan.evidence import canonical_json, stable_id
from bridger.deterministic.context_plan.working_state import validate_working_state
from bridger.models.synthesis_manifest import (
    SynthesisInputManifest,
    SynthesisOmission,
    SynthesisSelectionLimits,
    SynthesisVerbatimExcerpt,
)
from bridger.models.working_state import (
    ContextPlanWorkingState,
    EstablishedFinding,
    EvidenceKind,
    EvidenceLineRange,
    EvidenceRecord,
    EvidenceStatus,
    FindingStatus,
    InspectionLevel,
    OpenQuestion,
    PackageCandidate,
    PackageCandidateStatus,
    QuestionStatus,
    RelationshipRecord,
    RelationshipStatus,
)

_EVIDENCE_STRENGTH = {
    InspectionLevel.IMPLEMENTATION_INSPECTED: 0,
    InspectionLevel.EXCERPT_INSPECTED: 1,
    InspectionLevel.LINE_OBSERVED: 2,
    InspectionLevel.SYMBOL_ONLY: 3,
    InspectionLevel.LOCATED: 4,
    InspectionLevel.DISCOVERED: 5,
}


@dataclass(frozen=True)
class SynthesisProjection:
    manifest: SynthesisInputManifest
    candidates: tuple[PackageCandidate, ...]
    findings: tuple[EstablishedFinding, ...]
    relationships: tuple[RelationshipRecord, ...]
    questions: tuple[OpenQuestion, ...]
    evidence: tuple[EvidenceRecord, ...]


class SynthesisProjector:
    def __init__(self, limits: SynthesisSelectionLimits | None = None) -> None:
        self.limits = limits or SynthesisSelectionLimits()

    def project(
        self,
        state: ContextPlanWorkingState,
        *,
        priority_paths: list[str] | None = None,
    ) -> SynthesisProjection:
        validate_working_state(state)
        priorities = sorted(set(priority_paths or []))
        evidence = [
            item for item in state.evidence if item.status is EvidenceStatus.ACTIVE
        ]
        evidence_by_id = {item.evidence_id: item for item in evidence}
        candidates = sorted(
            (
                item
                for item in state.package_candidates
                if item.status is PackageCandidateStatus.ACTIVE
            ),
            key=lambda item: (item.priority, item.candidate_id),
        )
        findings_by_id = {
            item.finding_id: item
            for item in state.findings
            if item.status is FindingStatus.ACTIVE
        }
        candidate_finding_ids = {
            finding_id
            for candidate in candidates
            for finding_id in candidate.finding_ids
        }
        findings = sorted(
            (
                findings_by_id[finding_id]
                for finding_id in candidate_finding_ids
                if finding_id in findings_by_id
            ),
            key=lambda item: (
                item.area_key,
                item.created_sequence,
                item.finding_id,
            ),
        )
        relationships = sorted(
            (
                item
                for item in state.relationships
                if item.status is RelationshipStatus.ACTIVE
            ),
            key=lambda item: (
                item.area_key,
                item.created_sequence,
                item.relationship_id,
            ),
        )
        questions = sorted(
            (
                item
                for item in state.open_questions
                if item.status is QuestionStatus.OPEN and item.priority <= 2
            ),
            key=lambda item: (
                item.priority,
                item.area_key,
                item.created_sequence,
                item.question_id,
            ),
        )

        candidate_evidence = {
            evidence_id
            for candidate in candidates
            for evidence_id in candidate.evidence_ids
        }
        finding_evidence = {
            evidence_id for finding in findings for evidence_id in finding.evidence_ids
        }
        question_evidence = {
            evidence_id
            for question in questions
            for evidence_id in question.related_evidence_ids
        }
        mandatory = candidate_evidence | finding_evidence | question_evidence
        for path in priorities:
            path_records = [item for item in evidence if item.path == path]
            if path_records:
                mandatory.add(min(path_records, key=self._base_rank).evidence_id)

        by_area: dict[str, list[EvidenceRecord]] = defaultdict(list)
        for record in evidence:
            by_area[record.area_key].append(record)
        for records in by_area.values():
            mandatory.add(min(records, key=self._base_rank).evidence_id)

        relationship_evidence = {
            evidence_id
            for relationship in relationships
            for evidence_id in relationship.evidence_ids
        }
        selected_ids = {
            evidence_id for evidence_id in mandatory if evidence_id in evidence_by_id
        }
        estimated_size = sum(
            self._estimated_size(evidence_by_id[evidence_id])
            for evidence_id in selected_ids
        )

        remaining_by_area: dict[str, list[EvidenceRecord]] = defaultdict(list)
        for record in evidence:
            if record.evidence_id not in selected_ids:
                remaining_by_area[record.area_key].append(record)
        for area_records in remaining_by_area.values():
            area_records.sort(
                key=lambda item: self._rank(
                    item,
                    candidate_evidence,
                    finding_evidence,
                    relationship_evidence,
                    set(priorities),
                )
            )

        while remaining_by_area:
            added = False
            for area in sorted(remaining_by_area):
                records = remaining_by_area[area]
                if not records:
                    continue
                record = records.pop(0)
                size = self._estimated_size(record)
                if (
                    len(selected_ids) < self.limits.max_evidence_records
                    and estimated_size + size <= self.limits.max_estimated_characters
                ):
                    selected_ids.add(record.evidence_id)
                    estimated_size += size
                    added = True
            remaining_by_area = {
                area: records for area, records in remaining_by_area.items() if records
            }
            if not added:
                break

        selected_evidence = sorted(
            (evidence_by_id[evidence_id] for evidence_id in selected_ids),
            key=self._base_rank,
        )
        selected_relationships = [
            item
            for item in relationships
            if not item.evidence_ids
            or any(value in selected_ids for value in item.evidence_ids)
        ]
        selected_questions = [
            item
            for item in questions
            if not item.related_evidence_ids
            or any(value in selected_ids for value in item.related_evidence_ids)
        ]
        omissions = self._omissions(
            evidence,
            selected_ids,
            mandatory,
            estimated_size,
        )
        excerpts, excerpt_omitted = self._verbatim_excerpts(selected_evidence)
        omitted_by_kind = Counter(item.kind for item in omissions)
        omitted_by_area = Counter(item.area_key for item in omissions)
        omitted_by_path = Counter(
            item.path for item in omissions if item.path is not None
        )
        omission_counts = Counter(item.reason for item in omissions)
        if excerpt_omitted:
            omission_counts["verbatim_excerpt_limit"] += excerpt_omitted

        revision = self._working_state_revision(state)
        manifest_identity = {
            "run_id": state.run_id,
            "working_state_revision": revision,
            "selected_candidate_ids": [item.candidate_id for item in candidates],
            "selected_finding_ids": [item.finding_id for item in findings],
            "selected_relationship_ids": [
                item.relationship_id for item in selected_relationships
            ],
            "selected_question_ids": [item.question_id for item in selected_questions],
            "selected_evidence_ids": [item.evidence_id for item in selected_evidence],
            "priority_paths": priorities,
            "limits": self.limits.model_dump(mode="json"),
        }
        manifest = SynthesisInputManifest(
            manifest_id=stable_id("manifest", manifest_identity),
            run_id=state.run_id,
            working_state_revision=revision,
            selected_candidate_ids=[item.candidate_id for item in candidates],
            selected_finding_ids=[item.finding_id for item in findings],
            selected_relationship_ids=[
                item.relationship_id for item in selected_relationships
            ],
            selected_question_ids=[item.question_id for item in selected_questions],
            selected_evidence_ids=[item.evidence_id for item in selected_evidence],
            selected_verbatim_excerpts=excerpts,
            priority_paths=priorities,
            represented_area_keys=sorted(
                {item.area_key for item in selected_evidence}
                | {item.area_key for item in findings}
                | {area for item in candidates for area in item.area_keys}
            ),
            selection_limits=self.limits,
            estimated_size=estimated_size,
            available_record_count=len(evidence),
            selected_record_count=len(selected_evidence),
            omitted_record_count=len(omissions),
            omitted_counts=dict(sorted(omission_counts.items())),
            omitted_by_kind=dict(sorted(omitted_by_kind.items())),
            omitted_by_area=dict(sorted(omitted_by_area.items())),
            omitted_by_path=dict(sorted(omitted_by_path.items())),
            omission_reasons=omissions,
            created_at=state.updated_at,
        )
        return SynthesisProjection(
            manifest=manifest,
            candidates=tuple(candidates),
            findings=tuple(findings),
            relationships=tuple(selected_relationships),
            questions=tuple(selected_questions),
            evidence=tuple(selected_evidence),
        )

    @staticmethod
    def _working_state_revision(state: ContextPlanWorkingState) -> str:
        serialized = canonical_json(state.model_dump(mode="json"))
        return sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _estimated_size(record: EvidenceRecord) -> int:
        return len(canonical_json(record.model_dump(mode="json")))

    @staticmethod
    def _base_rank(record: EvidenceRecord) -> tuple[object, ...]:
        first_range = (
            record.line_ranges[0]
            if record.line_ranges
            else EvidenceLineRange(line_start=1, line_end=1)
        )
        return (
            record.area_key,
            _EVIDENCE_STRENGTH[record.inspection_level],
            record.path or "",
            first_range.line_start,
            first_range.line_end,
            record.evidence_id,
            record.sequence_number,
        )

    def _rank(
        self,
        record: EvidenceRecord,
        candidate_evidence: set[str],
        finding_evidence: set[str],
        relationship_evidence: set[str],
        priority_paths: set[str],
    ) -> tuple[object, ...]:
        if record.evidence_id in candidate_evidence:
            category = 0
        elif record.evidence_id in finding_evidence and record.inspection_level in {
            InspectionLevel.IMPLEMENTATION_INSPECTED,
            InspectionLevel.EXCERPT_INSPECTED,
        }:
            category = 1
        elif record.evidence_id in relationship_evidence:
            category = 3
        elif record.path in priority_paths:
            category = 4
        elif record.inspection_level in {
            InspectionLevel.IMPLEMENTATION_INSPECTED,
            InspectionLevel.EXCERPT_INSPECTED,
            InspectionLevel.LINE_OBSERVED,
        }:
            category = 5
        elif record.kind is EvidenceKind.MANIFEST_FACT:
            category = 6
        else:
            category = 7
        return (category, *self._base_rank(record))

    def _omissions(
        self,
        evidence: list[EvidenceRecord],
        selected_ids: set[str],
        mandatory: set[str],
        estimated_size: int,
    ) -> list[SynthesisOmission]:
        omissions: list[SynthesisOmission] = []
        for record in sorted(evidence, key=self._base_rank):
            if record.evidence_id in selected_ids:
                continue
            if record.evidence_id in mandatory:
                reason = "mandatory_reference_missing"
            elif len(selected_ids) >= self.limits.max_evidence_records:
                reason = "record_limit"
            elif (
                estimated_size + self._estimated_size(record)
                > self.limits.max_estimated_characters
            ):
                reason = "estimated_size_limit"
            else:
                reason = "coverage_balanced_lower_rank"
            omissions.append(
                SynthesisOmission(
                    evidence_id=record.evidence_id,
                    kind=record.kind.value,
                    area_key=record.area_key,
                    path=record.path,
                    reason=reason,
                )
            )
        return omissions

    def _verbatim_excerpts(
        self, evidence: list[EvidenceRecord]
    ) -> tuple[list[SynthesisVerbatimExcerpt], int]:
        line_maps: dict[str, dict[int, tuple[str, str]]] = defaultdict(dict)
        fallback_excerpts: list[SynthesisVerbatimExcerpt] = []
        for record in evidence:
            if (
                record.kind is not EvidenceKind.FILE_EXCERPT
                or record.path is None
                or record.content is None
                or len(record.line_ranges) != 1
            ):
                continue
            line_range = record.line_ranges[0]
            content_lines = record.content.splitlines()
            expected = line_range.line_end - line_range.line_start + 1
            if len(content_lines) != expected:
                fallback_excerpts.append(
                    SynthesisVerbatimExcerpt(
                        evidence_ids=[record.evidence_id],
                        path=record.path,
                        line_range=line_range,
                        content=record.content,
                    )
                )
                continue
            for line_number, content in enumerate(content_lines, line_range.line_start):
                line_maps[record.path].setdefault(
                    line_number, (content, record.evidence_id)
                )

        excerpts = list(fallback_excerpts)
        for path in sorted(line_maps):
            line_map = line_maps[path]
            numbers = sorted(line_map)
            if not numbers:
                continue
            groups: list[list[int]] = [[numbers[0]]]
            for number in numbers[1:]:
                if number == groups[-1][-1] + 1:
                    groups[-1].append(number)
                else:
                    groups.append([number])
            for group in groups:
                excerpts.append(
                    SynthesisVerbatimExcerpt(
                        evidence_ids=sorted({line_map[number][1] for number in group}),
                        path=path,
                        line_range=EvidenceLineRange(
                            line_start=group[0], line_end=group[-1]
                        ),
                        content="\n".join(line_map[number][0] for number in group),
                    )
                )
        excerpts.sort(
            key=lambda item: (
                item.path,
                item.line_range.line_start,
                item.line_range.line_end,
                item.evidence_ids,
            )
        )
        selected = excerpts[: self.limits.max_verbatim_excerpts]
        return selected, len(excerpts) - len(selected)
