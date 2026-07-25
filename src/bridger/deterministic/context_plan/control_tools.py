"""Narrow model-facing operations for durable Context Plan knowledge state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)

from bridger.deterministic.context_plan.evidence import stable_id
from bridger.deterministic.context_plan.working_state import (
    WorkingStateMutationService,
    WorkingStateValidationError,
)
from bridger.llm.models import LLMToolDefinition
from bridger.models.context_plan import ContextPlanValidationIssue
from bridger.models.working_state import (
    EstablishedFinding,
    FindingStatus,
    OpenQuestion,
    PackageCandidate,
    PackageCandidateStatus,
    QuestionStatus,
    RelationshipRecord,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
StableId = NonEmptyString

CONTROL_TOOL_NAMES = frozenset(
    {
        "record_finding",
        "refine_finding",
        "supersede_finding",
        "record_relationship",
        "open_question",
        "resolve_question",
        "create_package_candidate",
        "update_package_candidate",
        "merge_package_candidates",
        "discard_package_candidate",
        "restore_package_candidate",
    }
)


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecordFindingInput(ControlInput):
    statement: NonEmptyString
    evidence_ids: Annotated[list[StableId], Field(min_length=1)]
    area_key: NonEmptyString
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class RefineFindingInput(RecordFindingInput):
    finding_id: StableId


class SupersedeFindingInput(ControlInput):
    finding_id: StableId
    replacement_finding_id: StableId


class RecordRelationshipInput(ControlInput):
    source_entity: NonEmptyString
    relationship_type: NonEmptyString
    target_entity: NonEmptyString
    evidence_ids: Annotated[list[StableId], Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    area_key: NonEmptyString = "repository"


class OpenQuestionInput(ControlInput):
    question: NonEmptyString
    area_key: NonEmptyString
    related_evidence_ids: list[StableId] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=1, le=5)] = 3


class ResolveQuestionInput(ControlInput):
    question_id: StableId
    resolution: NonEmptyString
    resolution_evidence_ids: list[StableId] = Field(default_factory=list)
    status: Literal["resolved", "unanswerable"] = "resolved"


class CreatePackageCandidateInput(ControlInput):
    title: NonEmptyString
    purpose: NonEmptyString
    target_memory_kind: NonEmptyString | None = None
    area_keys: Annotated[list[NonEmptyString], Field(min_length=1)]
    finding_ids: list[StableId] = Field(default_factory=list)
    evidence_ids: list[StableId] = Field(default_factory=list)
    question_ids: list[StableId] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=1)]


class UpdatePackageCandidateInput(ControlInput):
    candidate_id: StableId
    title: NonEmptyString | None = None
    purpose: NonEmptyString | None = None
    target_memory_kind: NonEmptyString | None = None
    area_keys: list[NonEmptyString] | None = None
    finding_ids: list[StableId] | None = None
    evidence_ids: list[StableId] | None = None
    question_ids: list[StableId] | None = None
    priority: Annotated[int, Field(ge=1)] | None = None


class MergePackageCandidatesInput(ControlInput):
    source_candidate_ids: Annotated[list[StableId], Field(min_length=1)]
    target_candidate_id: StableId


class CandidateIdInput(ControlInput):
    candidate_id: StableId


class WorkingStateOperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: NonEmptyString
    status: Literal["completed", "rejected"]
    entity_ids: list[StableId] = Field(default_factory=list)
    mutation_sequence: Annotated[int, Field(ge=0)]
    issues: list[ContextPlanValidationIssue] = Field(default_factory=list)


_INPUT_MODELS: dict[str, type[ControlInput]] = {
    "record_finding": RecordFindingInput,
    "refine_finding": RefineFindingInput,
    "supersede_finding": SupersedeFindingInput,
    "record_relationship": RecordRelationshipInput,
    "open_question": OpenQuestionInput,
    "resolve_question": ResolveQuestionInput,
    "create_package_candidate": CreatePackageCandidateInput,
    "update_package_candidate": UpdatePackageCandidateInput,
    "merge_package_candidates": MergePackageCandidatesInput,
    "discard_package_candidate": CandidateIdInput,
    "restore_package_candidate": CandidateIdInput,
}

_DESCRIPTIONS = {
    "record_finding": "Record one evidence-backed factual repository conclusion.",
    "refine_finding": (
        "Replace an active finding with a refined evidence-backed version."
    ),
    "supersede_finding": "Supersede one active finding with another active finding.",
    "record_relationship": "Record one evidence-backed relationship between entities.",
    "open_question": "Record one unresolved repository question or contradiction.",
    "resolve_question": "Resolve or mark unanswerable one recorded question.",
    "create_package_candidate": (
        "Create an incremental Context Plan package hypothesis."
    ),
    "update_package_candidate": "Update one active package hypothesis.",
    "merge_package_candidates": "Merge package hypotheses into one active candidate.",
    "discard_package_candidate": "Discard one active package hypothesis.",
    "restore_package_candidate": "Restore one discarded package hypothesis.",
}


def control_tool_definitions() -> list[LLMToolDefinition]:
    return [
        LLMToolDefinition(
            name=name,
            description=_DESCRIPTIONS[name],
            input_schema=cast(dict[str, JsonValue], model.model_json_schema()),
        )
        for name, model in sorted(_INPUT_MODELS.items())
    ]


class WorkingStateOperationExecutor:
    def __init__(self, service: WorkingStateMutationService) -> None:
        self.service = service

    def execute(
        self, operation: str, arguments: dict[str, JsonValue]
    ) -> WorkingStateOperationResult:
        input_model = _INPUT_MODELS.get(operation)
        if input_model is None:
            return self._rejected(operation, "unknown_operation", "Unknown operation")
        try:
            value = input_model.model_validate(arguments)
            entity_ids = self._execute_validated(operation, value)
        except ValidationError as error:
            return self._rejected(
                operation,
                "invalid_arguments",
                "Arguments do not match the operation schema",
                {"errors": cast(JsonValue, error.errors(include_url=False))},
            )
        except (ValueError, WorkingStateValidationError) as error:
            return self._rejected(
                operation,
                "invalid_state_operation",
                str(error),
            )
        return WorkingStateOperationResult(
            operation=operation,
            status="completed",
            entity_ids=entity_ids,
            mutation_sequence=self.service.state.mutation_sequence,
        )

    def _execute_validated(self, operation: str, value: ControlInput) -> list[str]:
        handlers = {
            "record_finding": self._record_finding,
            "refine_finding": self._refine_finding,
            "supersede_finding": self._supersede_finding,
            "record_relationship": self._record_relationship,
            "open_question": self._open_question,
            "resolve_question": self._resolve_question,
            "create_package_candidate": self._create_candidate,
            "update_package_candidate": self._update_candidate,
            "merge_package_candidates": self._merge_candidates,
            "discard_package_candidate": self._discard_candidate,
            "restore_package_candidate": self._restore_candidate,
        }
        return handlers[operation](value)

    def _record_finding(self, raw: ControlInput) -> list[str]:
        value = cast(RecordFindingInput, raw)
        sequence = self.service.next_sequence()
        finding_id = stable_id(
            "finding",
            {
                "statement": value.statement,
                "area_key": value.area_key,
                "evidence_ids": sorted(value.evidence_ids),
            },
        )
        if any(item.finding_id == finding_id for item in self.service.state.findings):
            return [finding_id]
        finding = EstablishedFinding(
            finding_id=finding_id,
            statement=value.statement,
            evidence_ids=sorted(set(value.evidence_ids)),
            area_key=value.area_key,
            confidence=value.confidence,
            created_sequence=sequence,
            updated_sequence=sequence,
        )
        self._commit(
            findings=[*self.service.state.findings, finding],
            sequence=sequence,
        )
        return [finding_id]

    def _refine_finding(self, raw: ControlInput) -> list[str]:
        value = cast(RefineFindingInput, raw)
        previous = self._finding(value.finding_id, active=True)
        sequence = self.service.next_sequence()
        finding_id = stable_id(
            "finding",
            {
                "statement": value.statement,
                "area_key": value.area_key,
                "evidence_ids": sorted(value.evidence_ids),
                "supersedes": previous.finding_id,
            },
        )
        replacement = EstablishedFinding(
            finding_id=finding_id,
            statement=value.statement,
            evidence_ids=sorted(set(value.evidence_ids)),
            area_key=value.area_key,
            confidence=value.confidence,
            supersedes=previous.finding_id,
            created_sequence=sequence,
            updated_sequence=sequence,
        )
        findings = [
            item.model_copy(
                update={
                    "status": FindingStatus.SUPERSEDED,
                    "updated_sequence": sequence,
                }
            )
            if item.finding_id == previous.finding_id
            else item
            for item in self.service.state.findings
        ]
        findings.append(replacement)
        candidates = self._replace_candidate_finding(
            previous.finding_id, finding_id, sequence
        )
        self._commit(
            findings=findings,
            package_candidates=candidates,
            sequence=sequence,
        )
        return [finding_id]

    def _supersede_finding(self, raw: ControlInput) -> list[str]:
        value = cast(SupersedeFindingInput, raw)
        previous = self._finding(value.finding_id, active=True)
        replacement = self._finding(value.replacement_finding_id, active=True)
        if previous.finding_id == replacement.finding_id:
            raise ValueError("a finding cannot supersede itself")
        sequence = self.service.next_sequence()
        findings = [
            item.model_copy(
                update={
                    "status": FindingStatus.SUPERSEDED,
                    "updated_sequence": sequence,
                }
            )
            if item.finding_id == previous.finding_id
            else item
            for item in self.service.state.findings
        ]
        candidates = self._replace_candidate_finding(
            previous.finding_id, replacement.finding_id, sequence
        )
        self._commit(
            findings=findings,
            package_candidates=candidates,
            sequence=sequence,
        )
        return [previous.finding_id, replacement.finding_id]

    def _record_relationship(self, raw: ControlInput) -> list[str]:
        value = cast(RecordRelationshipInput, raw)
        sequence = self.service.next_sequence()
        relationship_id = stable_id(
            "relationship",
            {
                "source_entity": value.source_entity,
                "relationship_type": value.relationship_type,
                "target_entity": value.target_entity,
                "evidence_ids": sorted(value.evidence_ids),
            },
        )
        if any(
            item.relationship_id == relationship_id
            for item in self.service.state.relationships
        ):
            return [relationship_id]
        relationship = RelationshipRecord(
            relationship_id=relationship_id,
            source_entity=value.source_entity,
            relationship_type=value.relationship_type,
            target_entity=value.target_entity,
            evidence_ids=sorted(set(value.evidence_ids)),
            confidence=value.confidence,
            area_key=value.area_key,
            created_sequence=sequence,
            updated_sequence=sequence,
        )
        self._commit(
            relationships=[*self.service.state.relationships, relationship],
            sequence=sequence,
        )
        return [relationship_id]

    def _open_question(self, raw: ControlInput) -> list[str]:
        value = cast(OpenQuestionInput, raw)
        sequence = self.service.next_sequence()
        question_id = stable_id(
            "question",
            {
                "question": value.question,
                "area_key": value.area_key,
                "related_evidence_ids": sorted(value.related_evidence_ids),
            },
        )
        if any(
            item.question_id == question_id
            for item in self.service.state.open_questions
        ):
            return [question_id]
        question = OpenQuestion(
            question_id=question_id,
            question=value.question,
            area_key=value.area_key,
            related_evidence_ids=sorted(set(value.related_evidence_ids)),
            priority=value.priority,
            created_sequence=sequence,
            updated_sequence=sequence,
        )
        self._commit(
            open_questions=[*self.service.state.open_questions, question],
            sequence=sequence,
        )
        return [question_id]

    def _resolve_question(self, raw: ControlInput) -> list[str]:
        value = cast(ResolveQuestionInput, raw)
        question = self._question(value.question_id)
        if question.status is not QuestionStatus.OPEN:
            raise ValueError("only open questions can be resolved")
        sequence = self.service.next_sequence()
        status = (
            QuestionStatus.RESOLVED
            if value.status == "resolved"
            else QuestionStatus.UNANSWERABLE
        )
        questions = [
            item.model_copy(
                update={
                    "status": status,
                    "resolution": value.resolution,
                    "resolution_evidence_ids": sorted(
                        set(value.resolution_evidence_ids)
                    ),
                    "updated_sequence": sequence,
                }
            )
            if item.question_id == question.question_id
            else item
            for item in self.service.state.open_questions
        ]
        self._commit(open_questions=questions, sequence=sequence)
        return [question.question_id]

    def _create_candidate(self, raw: ControlInput) -> list[str]:
        value = cast(CreatePackageCandidateInput, raw)
        sequence = self.service.next_sequence()
        candidate_id = stable_id(
            "candidate",
            {
                "title": value.title,
                "purpose": value.purpose,
                "area_keys": sorted(value.area_keys),
            },
        )
        if any(
            item.candidate_id == candidate_id
            for item in self.service.state.package_candidates
        ):
            return [candidate_id]
        candidate = PackageCandidate(
            candidate_id=candidate_id,
            title=value.title,
            purpose=value.purpose,
            target_memory_kind=value.target_memory_kind,
            area_keys=sorted(set(value.area_keys)),
            finding_ids=sorted(set(value.finding_ids)),
            evidence_ids=sorted(set(value.evidence_ids)),
            question_ids=sorted(set(value.question_ids)),
            priority=value.priority,
            created_sequence=sequence,
            updated_sequence=sequence,
        )
        self._commit(
            package_candidates=[*self.service.state.package_candidates, candidate],
            sequence=sequence,
        )
        return [candidate_id]

    def _update_candidate(self, raw: ControlInput) -> list[str]:
        value = cast(UpdatePackageCandidateInput, raw)
        candidate = self._candidate(value.candidate_id)
        if candidate.status is not PackageCandidateStatus.ACTIVE:
            raise ValueError("only active candidates can be updated")
        updates = {
            name: getattr(value, name)
            for name in (
                "title",
                "purpose",
                "target_memory_kind",
                "area_keys",
                "finding_ids",
                "evidence_ids",
                "question_ids",
                "priority",
            )
            if name in value.model_fields_set
        }
        if not updates:
            raise ValueError("candidate update contains no changed fields")
        for name in ("area_keys", "finding_ids", "evidence_ids", "question_ids"):
            if name in updates and updates[name] is not None:
                updates[name] = sorted(set(cast(list[str], updates[name])))
        if updates.get("area_keys") == []:
            raise ValueError("area_keys cannot be empty")
        sequence = self.service.next_sequence()
        updates["updated_sequence"] = sequence
        candidates = [
            item.model_copy(update=updates)
            if item.candidate_id == candidate.candidate_id
            else item
            for item in self.service.state.package_candidates
        ]
        self._commit(package_candidates=candidates, sequence=sequence)
        return [candidate.candidate_id]

    def _merge_candidates(self, raw: ControlInput) -> list[str]:
        value = cast(MergePackageCandidatesInput, raw)
        target = self._candidate(value.target_candidate_id)
        if target.status is not PackageCandidateStatus.ACTIVE:
            raise ValueError("merge target must be active")
        sources = [
            self._candidate(candidate_id)
            for candidate_id in sorted(set(value.source_candidate_ids))
            if candidate_id != target.candidate_id
        ]
        if not sources:
            raise ValueError("merge requires at least one distinct source candidate")
        if any(item.status is not PackageCandidateStatus.ACTIVE for item in sources):
            raise ValueError("merge sources must be active")
        sequence = self.service.next_sequence()
        merged = target.model_copy(
            update={
                "area_keys": sorted(
                    {area for item in [target, *sources] for area in item.area_keys}
                ),
                "finding_ids": sorted(
                    {
                        finding_id
                        for item in [target, *sources]
                        for finding_id in item.finding_ids
                    }
                ),
                "evidence_ids": sorted(
                    {
                        evidence_id
                        for item in [target, *sources]
                        for evidence_id in item.evidence_ids
                    }
                ),
                "question_ids": sorted(
                    {
                        question_id
                        for item in [target, *sources]
                        for question_id in item.question_ids
                    }
                ),
                "priority": min(item.priority for item in [target, *sources]),
                "updated_sequence": sequence,
            }
        )
        source_ids = {item.candidate_id for item in sources}
        candidates = []
        for item in self.service.state.package_candidates:
            if item.candidate_id == target.candidate_id:
                candidates.append(merged)
            elif item.candidate_id in source_ids:
                candidates.append(
                    item.model_copy(
                        update={
                            "status": PackageCandidateStatus.MERGED,
                            "merged_into": target.candidate_id,
                            "updated_sequence": sequence,
                        }
                    )
                )
            else:
                candidates.append(item)
        self._commit(package_candidates=candidates, sequence=sequence)
        return [target.candidate_id, *sorted(source_ids)]

    def _discard_candidate(self, raw: ControlInput) -> list[str]:
        value = cast(CandidateIdInput, raw)
        candidate = self._candidate(value.candidate_id)
        if candidate.status is not PackageCandidateStatus.ACTIVE:
            raise ValueError("only active candidates can be discarded")
        return self._set_candidate_status(candidate, PackageCandidateStatus.DISCARDED)

    def _restore_candidate(self, raw: ControlInput) -> list[str]:
        value = cast(CandidateIdInput, raw)
        candidate = self._candidate(value.candidate_id)
        if candidate.status is not PackageCandidateStatus.DISCARDED:
            raise ValueError("only discarded candidates can be restored")
        return self._set_candidate_status(candidate, PackageCandidateStatus.ACTIVE)

    def _set_candidate_status(
        self,
        candidate: PackageCandidate,
        status: PackageCandidateStatus,
    ) -> list[str]:
        sequence = self.service.next_sequence()
        candidates = [
            item.model_copy(update={"status": status, "updated_sequence": sequence})
            if item.candidate_id == candidate.candidate_id
            else item
            for item in self.service.state.package_candidates
        ]
        self._commit(package_candidates=candidates, sequence=sequence)
        return [candidate.candidate_id]

    def _replace_candidate_finding(
        self, previous_id: str, replacement_id: str, sequence: int
    ) -> list[PackageCandidate]:
        candidates: list[PackageCandidate] = []
        for item in self.service.state.package_candidates:
            if (
                item.status is PackageCandidateStatus.ACTIVE
                and previous_id in item.finding_ids
            ):
                finding_ids = {
                    replacement_id if value == previous_id else value
                    for value in item.finding_ids
                }
                candidates.append(
                    item.model_copy(
                        update={
                            "finding_ids": sorted(finding_ids),
                            "updated_sequence": sequence,
                        }
                    )
                )
            else:
                candidates.append(item)
        return candidates

    def _finding(self, finding_id: str, *, active: bool = False) -> EstablishedFinding:
        finding = next(
            (
                item
                for item in self.service.state.findings
                if item.finding_id == finding_id
            ),
            None,
        )
        if finding is None:
            raise ValueError(f"finding does not exist: {finding_id}")
        if active and finding.status is not FindingStatus.ACTIVE:
            raise ValueError(f"finding is not active: {finding_id}")
        return finding

    def _question(self, question_id: str) -> OpenQuestion:
        question = next(
            (
                item
                for item in self.service.state.open_questions
                if item.question_id == question_id
            ),
            None,
        )
        if question is None:
            raise ValueError(f"question does not exist: {question_id}")
        return question

    def _candidate(self, candidate_id: str) -> PackageCandidate:
        candidate = next(
            (
                item
                for item in self.service.state.package_candidates
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise ValueError(f"candidate does not exist: {candidate_id}")
        return candidate

    def _commit(self, *, sequence: int, **updates: object) -> None:
        candidate = self.service.state.model_copy(
            update={
                **updates,
                "mutation_sequence": sequence,
                "updated_at": datetime.now(UTC),
            }
        )
        self.service.commit(candidate)

    def _rejected(
        self,
        operation: str,
        code: str,
        message: str,
        context: dict[str, JsonValue] | None = None,
    ) -> WorkingStateOperationResult:
        return WorkingStateOperationResult(
            operation=operation or "unknown_operation",
            status="rejected",
            mutation_sequence=self.service.state.mutation_sequence,
            issues=[
                ContextPlanValidationIssue(
                    code=code,
                    location=["arguments"],
                    message=message,
                    context=context or {},
                )
            ],
        )
