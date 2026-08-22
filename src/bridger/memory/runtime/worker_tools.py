"""Controlled Stage 4 mutation and repository tool surfaces."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import uuid4

import orjson
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from bridger.contracts.enrichment import EnrichmentTargetType
from bridger.contracts.memory.core import (
    CandidateArtifactRef,
    CompletionItemState,
    CompletionStatus,
    ObligationApplicability,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.hydration import PermissionProfile, WorkerContext
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    EvidenceLocator,
    EvidenceReference,
    FileEvidenceLocator,
    GraphEntityEvidenceLocator,
    OpenQuestion,
    SourceRangeEvidenceLocator,
    SymbolEvidenceLocator,
)
from bridger.llm.models import (
    LLMToolCall,
    LLMToolDefinition,
    LLMToolError,
    LLMToolResult,
)
from bridger.llm.tools import LLMTool, ToolExecutor
from bridger.memory.persistence.durability import FleetRuntimeStore
from bridger.navigation.navigator import MAX_RANGE_LINES, RepositoryNavigator
from bridger.navigation.tools import (
    _CommunityTargetReference,
    _EdgeTargetReference,
    build_navigation_tools,
)
from bridger.repository.errors import RepositoryError

MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_ARTIFACT_READ_BYTES = 64 * 1024
MAX_WORKING_SUMMARY_CHARS = 8_000
MAX_QUESTION_CHARS = 1_000
MAX_OPEN_QUESTIONS = 20
MAX_RESOLUTION_NOTE_CHARS = 4_000

REPOSITORY_TOOL_IDS = (
    "search_repository",
    "get_graph_entity",
    "get_graph_neighbors",
    "get_graph_path",
    "get_graph_community",
    "list_files",
    "get_file_overview",
    "search_symbols",
    "search_source_content",
    "read_symbol_excerpt",
    "read_file_ranges",
)
TARGET_TOOL_IDS = (
    "list_target_artifacts",
    "read_target_artifact",
    "write_target_artifact",
    "edit_target_artifact_range",
    "delete_target_artifact",
    "move_target_artifact",
    "record_evidence",
    "update_completion_item",
    "update_progress",
)
FINALIZATION_TOOL_ID = "request_finalization"
YIELD_CYCLE_TOOL_ID = "yield_cycle"
WORKER_TOOL_IDS = (*REPOSITORY_TOOL_IDS, *TARGET_TOOL_IDS)


def _target_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or path.as_posix() != value
        or value in {".", ".."}
        or ".." in path.parts
        or path.suffix.lower() != ".md"
    ):
        raise ValueError("path must be normalized target-relative Markdown")
    return value


TargetRelativePath = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_target_relative_path),
]


class TargetWorkspace:
    """Constrained candidate-Markdown storage for one target task."""

    def __init__(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        persistence: FleetRuntimeStore | None = None,
    ) -> None:
        self._spec = target_spec
        self._state = target_state
        self._persistence = persistence
        configured_root = Path(target_spec.target_workspace)
        if configured_root.is_symlink():
            raise ValueError("target workspace cannot be a symlink")
        self._root = configured_root.resolve()
        if not self._root.is_dir():
            raise ValueError("target workspace must be an existing real directory")

    def list_target_artifacts(self) -> list[CandidateArtifactRef]:
        """Return the complete authoritative current artifact inventory."""
        return sorted(
            self._state.artifact_refs,
            key=lambda item: (item.relative_path, item.artifact_id),
        )

    def read_target_artifact(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, object]:
        """Read one bounded current artifact or line range."""
        reference = self._reference_for_path(path)
        if (start_line is None) != (end_line is None):
            raise ValueError("start_line and end_line must be supplied together")
        if start_line is not None and end_line is not None:
            if start_line < 1 or end_line < start_line:
                raise ValueError("artifact range must be positive and non-inverted")
            if end_line - start_line + 1 > MAX_RANGE_LINES:
                raise ValueError(
                    f"artifact range is limited to {MAX_RANGE_LINES} lines"
                )
        content = self._read_current(reference)
        lines = content.splitlines()
        if start_line is None or end_line is None:
            selected = content
            selected_start = 1
            selected_end = max(1, len(lines))
        else:
            if start_line > len(lines):
                raise ValueError("start_line is beyond the artifact")
            selected = "\n".join(lines[start_line - 1 : end_line])
            selected_start = start_line
            selected_end = min(end_line, len(lines))
        encoded = selected.encode()
        truncated = len(encoded) > MAX_ARTIFACT_READ_BYTES
        if truncated:
            selected = encoded[:MAX_ARTIFACT_READ_BYTES].decode(
                "utf-8", errors="ignore"
            )
        return {
            "artifact": reference,
            "content": selected,
            "start_line": selected_start,
            "end_line": selected_end,
            "truncated": truncated,
        }

    def write_target_artifact(
        self,
        path: str,
        content: str,
        *,
        expected_revision: int | None = None,
    ) -> CandidateArtifactRef:
        """Create or whole-file replace one candidate artifact."""
        _require_working_phase(self._state)
        destination = self._resolve_path(path)
        encoded = content.encode()
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise ValueError("candidate artifact exceeds the V0 size limit")
        existing = self._optional_reference_for_path(path)
        if existing is None:
            if expected_revision is not None:
                raise ValueError("new artifact cannot declare expected_revision")
            if destination.exists() or destination.is_symlink():
                raise ValueError("untracked workspace path already exists")
            artifact_id = f"artifact-{uuid4().hex}"
            revision = 1
        else:
            self._require_revision(existing, expected_revision)
            self._read_current(existing)
            artifact_id = existing.artifact_id
            revision = existing.revision + 1
        self._require_within_root(destination)
        reference = CandidateArtifactRef(
            artifact_id=artifact_id,
            relative_path=path,
            revision=revision,
            digest=hashlib.sha256(encoded).hexdigest(),
        )
        if self._persistence is None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(encoded)
            self._replace_reference(existing, reference)
        else:
            after_state = self._state_with_reference(existing, reference)
            self._persistence.commit_artifact_mutation(
                self._spec,
                self._state,
                after_state,
                writes={destination: encoded},
                action="write",
                artifact_id=reference.artifact_id,
            )
        return reference

    def edit_target_artifact_range(
        self,
        path: str,
        *,
        expected_revision: int,
        start_line: int,
        end_line: int,
        replacement: str,
    ) -> CandidateArtifactRef:
        """Replace one inclusive line range using optimistic revision control."""
        _require_working_phase(self._state)
        reference = self._reference_for_path(path)
        self._require_revision(reference, expected_revision)
        if start_line < 1 or end_line < start_line:
            raise ValueError("artifact range must be positive and non-inverted")
        if end_line - start_line + 1 > MAX_RANGE_LINES:
            raise ValueError(f"artifact range is limited to {MAX_RANGE_LINES} lines")
        content = self._read_current(reference)
        lines = content.splitlines(keepends=True)
        if end_line > len(lines):
            raise ValueError("end_line is beyond the artifact")
        replacement_lines = replacement.splitlines(keepends=True)
        updated = "".join(
            [*lines[: start_line - 1], *replacement_lines, *lines[end_line:]]
        )
        return self.write_target_artifact(
            path,
            updated,
            expected_revision=expected_revision,
        )

    def delete_target_artifact(
        self,
        path: str,
        *,
        expected_revision: int,
    ) -> CandidateArtifactRef:
        """Delete one current artifact and remove its authoritative reference."""
        _require_working_phase(self._state)
        reference = self._reference_for_path(path)
        self._require_revision(reference, expected_revision)
        source = self._resolve_path(path)
        self._read_current(reference)
        after_state = self._state.model_copy(deep=True)
        after_state.artifact_refs = [
            item
            for item in after_state.artifact_refs
            if item.artifact_id != reference.artifact_id
        ]
        if self._persistence is None:
            source.unlink()
            self._state.artifact_refs = after_state.artifact_refs
        else:
            self._persistence.commit_artifact_mutation(
                self._spec,
                self._state,
                after_state,
                writes={},
                deletions=[source],
                action="delete",
                artifact_id=reference.artifact_id,
            )
        return reference

    def move_target_artifact(
        self,
        source_path: str,
        destination_path: str,
        *,
        expected_revision: int,
    ) -> CandidateArtifactRef:
        """Move one artifact without changing its identity."""
        _require_working_phase(self._state)
        reference = self._reference_for_path(source_path)
        self._require_revision(reference, expected_revision)
        source = self._resolve_path(source_path)
        destination = self._resolve_path(destination_path)
        self._read_current(reference)
        if self._optional_reference_for_path(destination_path) is not None:
            raise ValueError("destination artifact already exists")
        if destination.exists() or destination.is_symlink():
            raise ValueError("destination workspace path already exists")
        self._require_within_root(destination)
        content = source.read_bytes()
        moved = reference.model_copy(
            update={
                "relative_path": destination_path,
                "revision": reference.revision + 1,
            }
        )
        if self._persistence is None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            self._replace_reference(reference, moved)
        else:
            after_state = self._state_with_reference(reference, moved)
            self._persistence.commit_artifact_mutation(
                self._spec,
                self._state,
                after_state,
                writes={destination: content},
                deletions=[source],
                action="move",
                artifact_id=reference.artifact_id,
            )
        return moved

    def _reference_for_path(self, path: str) -> CandidateArtifactRef:
        reference = self._optional_reference_for_path(path)
        if reference is None:
            raise KeyError(f"unknown target artifact: {path}")
        return reference

    def _optional_reference_for_path(self, path: str) -> CandidateArtifactRef | None:
        _target_relative_path(path)
        matches = [
            item for item in self._state.artifact_refs if item.relative_path == path
        ]
        if len(matches) > 1:
            raise ValueError("duplicate authoritative artifact path")
        return matches[0] if matches else None

    def _resolve_path(self, path: str) -> Path:
        _target_relative_path(path)
        configured = self._root / path
        current = self._root
        for part in PurePosixPath(path).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("artifact path cannot traverse a symlink")
        resolved = configured.resolve()
        self._require_within_root(resolved)
        return resolved

    def _require_within_root(self, path: Path) -> None:
        if path == self._root or not path.is_relative_to(self._root):
            raise ValueError("artifact path escapes the exact target workspace")

    def _read_current(self, reference: CandidateArtifactRef) -> str:
        source = self._resolve_path(reference.relative_path)
        if source.is_symlink() or not source.is_file():
            raise ValueError("authoritative artifact file is missing or unsafe")
        content = source.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode()).hexdigest()
        if digest != reference.digest:
            raise ValueError("artifact content does not match authoritative digest")
        return content

    @staticmethod
    def _require_revision(
        reference: CandidateArtifactRef,
        expected_revision: int | None,
    ) -> None:
        if expected_revision is None or expected_revision != reference.revision:
            raise ValueError(
                "stale expected_revision; read the current artifact revision"
            )

    def _replace_reference(
        self,
        previous: CandidateArtifactRef | None,
        current: CandidateArtifactRef,
    ) -> None:
        references = [
            item
            for item in self._state.artifact_refs
            if previous is None or item.artifact_id != previous.artifact_id
        ]
        references.append(current)
        self._state.artifact_refs = sorted(
            references,
            key=lambda item: (item.relative_path, item.artifact_id),
        )

    def _state_with_reference(
        self,
        previous: CandidateArtifactRef | None,
        current: CandidateArtifactRef,
    ) -> TargetTaskState:
        after_state = self._state.model_copy(deep=True)
        references = [
            item
            for item in after_state.artifact_refs
            if previous is None or item.artifact_id != previous.artifact_id
        ]
        references.append(current)
        after_state.artifact_refs = sorted(
            references,
            key=lambda item: (item.relative_path, item.artifact_id),
        )
        return after_state


class EvidenceRecorder:
    """Validate, create, and target-deduplicate durable evidence references."""

    def __init__(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        navigator: RepositoryNavigator,
        evidence: MutableMapping[str, EvidenceReference],
        persistence: FleetRuntimeStore | None = None,
    ) -> None:
        self._spec = target_spec
        self._state = target_state
        self._navigator = navigator
        self._evidence = evidence
        self._persistence = persistence
        expected_source = (
            target_spec.source.repository_id,
            target_spec.source.repository_revision,
            target_spec.source.graph_snapshot_id,
            target_spec.source.enrichment_overlay_id,
        )
        if navigator.source_identity != expected_source:
            raise ValueError("RepositoryNavigator does not match the target source")

    def record_evidence(
        self,
        kind: EvidenceKind,
        locator: EvidenceLocator,
    ) -> EvidenceReference:
        """Create or reuse one mechanically validated evidence reference."""
        _require_working_phase(self._state)
        self._validate_locator(kind, locator)
        key = self._canonical_key(kind, locator)
        for reference in self._evidence.values():
            if (
                reference.target_task_id == self._spec.target_task_id
                and reference.source == self._spec.source
                and self._canonical_key(reference.kind, reference.locator) == key
            ):
                if reference.evidence_id not in self._state.evidence_refs:
                    if self._persistence is None:
                        self._add_state_reference(reference.evidence_id)
                    else:
                        self._persistence.commit_evidence(
                            self._spec, self._state, reference
                        )
                return reference
        reference = EvidenceReference(
            evidence_id=f"evidence-{uuid4().hex}",
            target_task_id=self._spec.target_task_id,
            source=self._spec.source,
            kind=kind,
            locator=locator,
        )
        if self._persistence is None:
            self._evidence[reference.evidence_id] = reference
            self._add_state_reference(reference.evidence_id)
        else:
            self._persistence.commit_evidence(self._spec, self._state, reference)
            self._evidence[reference.evidence_id] = reference
        return reference

    def _validate_locator(self, kind: EvidenceKind, locator: EvidenceLocator) -> None:
        expected = {
            EvidenceKind.FILE: FileEvidenceLocator,
            EvidenceKind.SOURCE_RANGE: SourceRangeEvidenceLocator,
            EvidenceKind.SYMBOL: SymbolEvidenceLocator,
            EvidenceKind.GRAPH_ENTITY: GraphEntityEvidenceLocator,
        }[kind]
        if not isinstance(locator, expected):
            raise ValueError("evidence kind does not match locator")
        if isinstance(locator, FileEvidenceLocator):
            overview = self._navigator.get_file_overview(locator.path)
            if overview.file.disposition.read_mode == "denied":
                raise ValueError("repository read policy denies this evidence")
        elif isinstance(locator, SourceRangeEvidenceLocator):
            result = self._navigator.read_file_ranges(
                locator.path,
                [(locator.start_line, locator.end_line)],
            )[0]
            if (
                result.revision != self._spec.source.repository_revision
                or result.start_line != locator.start_line
                or result.end_line != locator.end_line
                or result.content_digest != locator.content_digest
            ):
                raise ValueError("source-range evidence does not resolve exactly")
        elif isinstance(locator, SymbolEvidenceLocator):
            result = self._navigator.read_symbol_excerpt(
                locator.symbol_id,
                context_lines=0,
            )
            if result.revision != self._spec.source.repository_revision:
                raise ValueError("symbol evidence belongs to another revision")
        else:
            self._navigator.get_graph_entity(
                locator.target_type,
                locator.target_ref,
            )

    def _canonical_key(
        self,
        kind: EvidenceKind,
        locator: EvidenceLocator,
    ) -> bytes:
        return orjson.dumps(
            {
                "source": self._spec.source.model_dump(mode="json"),
                "kind": kind.value,
                "locator": locator.model_dump(mode="json"),
            },
            option=orjson.OPT_SORT_KEYS,
        )

    def _add_state_reference(self, evidence_id: str) -> None:
        if evidence_id not in self._state.evidence_refs:
            self._state.evidence_refs = [*self._state.evidence_refs, evidence_id]


class CompletionStateUpdater:
    """Apply mechanically valid worker completion proposals."""

    def __init__(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        completion_state: TargetCompletionState,
        target_definition: TargetDefinition,
        evidence: Mapping[str, EvidenceReference],
        persistence: FleetRuntimeStore | None = None,
    ) -> None:
        self._spec = target_spec
        self._target_state = target_state
        self._state = completion_state
        self._definition = target_definition
        self._evidence = evidence
        self._persistence = persistence
        if completion_state.target_task_id != target_spec.target_task_id:
            raise ValueError("completion state belongs to another target")
        if target_state.target_task_id != target_spec.target_task_id:
            raise ValueError("target state belongs to another target")
        if (
            target_definition.target_id != target_spec.target_id
            or target_definition.target_contract_version
            != target_spec.target_contract_version
        ):
            raise ValueError("target definition does not match the target task")
        expected_obligations = {
            item.obligation_id for item in target_definition.completion_obligations
        }
        actual_obligations = {item.obligation_id for item in completion_state.items}
        if actual_obligations != expected_obligations:
            raise ValueError("completion state does not match target obligations")

    def update_completion_item(
        self,
        obligation_id: str,
        status: CompletionStatus,
        resolution_note: str,
        evidence_refs: Sequence[str],
    ) -> CompletionItemState:
        """Replace one obligation's mutable resolution fields atomically."""
        _require_working_phase(self._target_state)
        if status is CompletionStatus.UNINVESTIGATED:
            raise ValueError("worker cannot restore uninvestigated")
        note = resolution_note.strip()
        if not note:
            raise ValueError("resolution_note must be non-empty")
        if len(note) > MAX_RESOLUTION_NOTE_CHARS:
            raise ValueError("resolution_note exceeds the V0 size limit")
        obligations = {
            item.obligation_id: item for item in self._definition.completion_obligations
        }
        obligation = obligations.get(obligation_id)
        if obligation is None:
            raise KeyError(f"unknown completion obligation: {obligation_id}")
        if (
            status is CompletionStatus.NOT_APPLICABLE
            and obligation.applicability is not ObligationApplicability.CONDITIONAL
        ):
            raise ValueError("not-applicable requires a conditional obligation")
        unique_refs = list(dict.fromkeys(evidence_refs))
        for evidence_id in unique_refs:
            reference = self._evidence.get(evidence_id)
            if reference is None:
                raise KeyError(f"unknown evidence reference: {evidence_id}")
            if (
                reference.target_task_id != self._spec.target_task_id
                or reference.source != self._spec.source
            ):
                raise ValueError("completion evidence belongs to another target/source")
        items = {item.obligation_id: item for item in self._state.items}
        if obligation_id not in items:
            raise KeyError(f"completion state is missing obligation: {obligation_id}")
        replacement = CompletionItemState(
            obligation_id=obligation_id,
            status=status,
            resolution_note=note,
            evidence_refs=unique_refs,
        )
        after_state = self._state.model_copy(deep=True)
        after_state.items = [
            replacement if item.obligation_id == obligation_id else item
            for item in after_state.items
        ]
        if self._persistence is None:
            self._state.items = after_state.items
        else:
            self._persistence.persist_completion_state(
                self._spec,
                self._target_state,
                after_state,
                obligation_id=obligation_id,
            )
            self._state.items = after_state.items
        return replacement


class ProgressUpdater:
    """Maintain compact continuation state and the current open-question set."""

    def __init__(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        questions: MutableMapping[str, OpenQuestion],
        persistence: FleetRuntimeStore | None = None,
    ) -> None:
        self._spec = target_spec
        self._state = target_state
        self._questions = questions
        self._persistence = persistence

    def update_progress(
        self,
        *,
        working_summary: str | None = None,
        questions_to_open: Sequence[str] = (),
        question_refs_to_resolve: Sequence[str] = (),
    ) -> dict[str, object]:
        """Replace supplied summary state, open questions, and resolve current refs."""
        _require_working_phase(self._state)
        updated_summary = self._state.working_summary
        if working_summary is not None:
            summary = working_summary.strip()
            if not summary:
                raise ValueError("working_summary must be non-empty when supplied")
            if len(summary) > MAX_WORKING_SUMMARY_CHARS:
                raise ValueError("working_summary exceeds the V0 size limit")
            updated_summary = summary
        if len(self._state.open_question_refs) != len(
            set(self._state.open_question_refs)
        ):
            raise ValueError("open question references must be unique")
        for question_id in self._state.open_question_refs:
            question = self._questions.get(question_id)
            if question is None or question.target_task_id != self._spec.target_task_id:
                raise ValueError("current open question state is invalid")
        resolve_refs = list(dict.fromkeys(question_refs_to_resolve))
        unknown = [
            question_id
            for question_id in resolve_refs
            if question_id not in self._state.open_question_refs
        ]
        if unknown:
            raise KeyError(f"question is not currently open: {unknown[0]}")
        remaining_refs = [
            question_id
            for question_id in self._state.open_question_refs
            if question_id not in resolve_refs
        ]
        opened: list[OpenQuestion] = []
        for text in questions_to_open:
            normalized = text.strip()
            if not normalized:
                raise ValueError("open question text must be non-empty")
            if len(normalized) > MAX_QUESTION_CHARS:
                raise ValueError("open question exceeds the V0 size limit")
            question = OpenQuestion(
                question_id=f"question-{uuid4().hex}",
                target_task_id=self._spec.target_task_id,
                text=normalized,
            )
            opened.append(question)
        if len(remaining_refs) + len(opened) > MAX_OPEN_QUESTIONS:
            raise ValueError("too many simultaneously open questions")
        after_state = self._state.model_copy(deep=True)
        after_state.working_summary = updated_summary
        for question in opened:
            remaining_refs.append(question.question_id)
        after_state.open_question_refs = remaining_refs
        if self._persistence is None:
            self._state.working_summary = after_state.working_summary
            self._state.open_question_refs = after_state.open_question_refs
        else:
            self._persistence.commit_progress(
                self._spec,
                self._state,
                after_state,
                opened,
                resolve_refs,
            )
        for question in opened:
            self._questions[question.question_id] = question
        return {
            "working_summary": self._state.working_summary,
            "opened_questions": opened,
            "resolved_question_refs": resolve_refs,
            "open_question_refs": self._state.open_question_refs,
        }


def _require_working_phase(target_state: TargetTaskState) -> None:
    if target_state.phase is not TargetPhase.WORKING:
        raise ValueError("worker mutation requires a WORKING target")


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _EmptyArguments(_Arguments):
    pass


class _ReadArtifactArguments(_Arguments):
    path: TargetRelativePath
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class _WriteArtifactArguments(_Arguments):
    path: TargetRelativePath
    content: str
    expected_revision: int | None = Field(default=None, ge=1)


class _EditArtifactArguments(_Arguments):
    path: TargetRelativePath
    expected_revision: int = Field(ge=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    replacement: str


class _DeleteArtifactArguments(_Arguments):
    path: TargetRelativePath
    expected_revision: int = Field(ge=1)


class _MoveArtifactArguments(_Arguments):
    source_path: TargetRelativePath
    destination_path: TargetRelativePath
    expected_revision: int = Field(ge=1)


class _GraphEntityEvidenceLocatorArguments(_Arguments):
    target_type: EnrichmentTargetType
    target_ref: str | _EdgeTargetReference | _CommunityTargetReference


class _RecordEvidenceArguments(_Arguments):
    kind: EvidenceKind
    locator: (
        FileEvidenceLocator
        | SourceRangeEvidenceLocator
        | SymbolEvidenceLocator
        | _GraphEntityEvidenceLocatorArguments
    )

    @model_validator(mode="after")
    def validate_kind(self) -> _RecordEvidenceArguments:
        expected = {
            EvidenceKind.FILE: FileEvidenceLocator,
            EvidenceKind.SOURCE_RANGE: SourceRangeEvidenceLocator,
            EvidenceKind.SYMBOL: SymbolEvidenceLocator,
            EvidenceKind.GRAPH_ENTITY: _GraphEntityEvidenceLocatorArguments,
        }[self.kind]
        if not isinstance(self.locator, expected):
            raise ValueError("evidence kind does not match locator")
        return self


def _persisted_evidence_locator(locator: object) -> EvidenceLocator:
    if isinstance(locator, _GraphEntityEvidenceLocatorArguments):
        target_ref = (
            locator.target_ref.model_dump()
            if isinstance(locator.target_ref, BaseModel)
            else locator.target_ref
        )
        return GraphEntityEvidenceLocator(
            target_type=locator.target_type,
            target_ref=target_ref,
        )
    assert isinstance(
        locator,
        (FileEvidenceLocator, SourceRangeEvidenceLocator, SymbolEvidenceLocator),
    )
    return locator


class _UpdateCompletionArguments(_Arguments):
    obligation_id: str = Field(min_length=1)
    status: CompletionStatus
    resolution_note: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class _UpdateProgressArguments(_Arguments):
    working_summary: str | None = None
    questions_to_open: list[str] = Field(default_factory=list)
    question_refs_to_resolve: list[str] = Field(default_factory=list)


class WorkerToolRuntime:
    """Resolve and independently enforce one worker's concrete tool surface."""

    def __init__(
        self,
        context: WorkerContext,
        permission_profile: PermissionProfile,
        navigator: RepositoryNavigator,
        workspace: TargetWorkspace,
        evidence_recorder: EvidenceRecorder,
        completion_updater: CompletionStateUpdater,
        progress_updater: ProgressUpdater,
    ) -> None:
        if permission_profile.profile_id != context.permission_profile_id:
            raise ValueError("permission profile does not match WorkerContext")
        if permission_profile.allowed_tool_ids != context.allowed_tool_ids:
            raise ValueError("permission tools do not match WorkerContext")
        unknown = set(context.allowed_tool_ids) - set(WORKER_TOOL_IDS)
        if unknown:
            raise ValueError(f"unknown configured worker tool: {sorted(unknown)[0]}")
        self._allowed = set(context.allowed_tool_ids)
        self._navigation = build_navigation_tools(navigator)
        self._local = _build_local_tools(
            workspace,
            evidence_recorder,
            completion_updater,
            progress_updater,
        )
        definitions = {
            definition.name: definition
            for definition in [
                *self._navigation.definitions,
                *self._local.definitions,
            ]
        }
        self._definitions = [
            definitions[tool_id]
            for tool_id in WORKER_TOOL_IDS
            if tool_id in self._allowed
        ]
        self._definitions.append(_yield_cycle_definition())
        self._definitions.append(_finalization_definition())

    @property
    def definitions(self) -> list[LLMToolDefinition]:
        """Return the stable exposed definitions after permission filtering."""
        return list(self._definitions)

    async def execute_operational(self, call: LLMToolCall) -> LLMToolResult:
        """Enforce permission again and dispatch one operational call."""
        if call.name not in self._allowed:
            return LLMToolResult(
                call_id=call.id,
                name=call.name,
                error=LLMToolError(
                    code="permission_denied",
                    message=f"Tool is not allowed for this worker: {call.name}",
                ),
            )
        if call.name in REPOSITORY_TOOL_IDS:
            return await self._navigation.execute(call)
        return await self._local.execute(call)


def _build_local_tools(
    workspace: TargetWorkspace,
    evidence_recorder: EvidenceRecorder,
    completion_updater: CompletionStateUpdater,
    progress_updater: ProgressUpdater,
) -> ToolExecutor:
    tools = [
        LLMTool.bind(
            name="list_target_artifacts",
            description="List the complete current target-local Markdown inventory.",
            arguments_type=_EmptyArguments,
            handler=lambda _: workspace.list_target_artifacts(),
        ),
        LLMTool.bind(
            name="read_target_artifact",
            description="Read one bounded current target-local Markdown artifact.",
            arguments_type=_ReadArtifactArguments,
            handler=lambda value: workspace.read_target_artifact(
                value.path,
                start_line=value.start_line,
                end_line=value.end_line,
            ),
        ),
        LLMTool.bind(
            name="write_target_artifact",
            description="Create or whole-file replace target-local Markdown.",
            arguments_type=_WriteArtifactArguments,
            handler=lambda value: workspace.write_target_artifact(
                value.path,
                value.content,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="edit_target_artifact_range",
            description="Replace an inclusive line range in current Markdown.",
            arguments_type=_EditArtifactArguments,
            handler=lambda value: workspace.edit_target_artifact_range(
                value.path,
                expected_revision=value.expected_revision,
                start_line=value.start_line,
                end_line=value.end_line,
                replacement=value.replacement,
            ),
        ),
        LLMTool.bind(
            name="delete_target_artifact",
            description="Delete one target-local Markdown artifact by revision.",
            arguments_type=_DeleteArtifactArguments,
            handler=lambda value: workspace.delete_target_artifact(
                value.path,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="move_target_artifact",
            description="Move one target-local Markdown artifact by revision.",
            arguments_type=_MoveArtifactArguments,
            handler=lambda value: workspace.move_target_artifact(
                value.source_path,
                value.destination_path,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="record_evidence",
            description="Validate and record one durable repository evidence locator.",
            arguments_type=_RecordEvidenceArguments,
            handler=lambda value: evidence_recorder.record_evidence(
                value.kind,
                _persisted_evidence_locator(value.locator),
            ),
        ),
        LLMTool.bind(
            name="update_completion_item",
            description="Replace one completion obligation's resolution fields.",
            arguments_type=_UpdateCompletionArguments,
            handler=lambda value: completion_updater.update_completion_item(
                value.obligation_id,
                value.status,
                value.resolution_note,
                value.evidence_refs,
            ),
        ),
        LLMTool.bind(
            name="update_progress",
            description="Replace compact continuation state and manage open questions.",
            arguments_type=_UpdateProgressArguments,
            handler=lambda value: progress_updater.update_progress(
                working_summary=value.working_summary,
                questions_to_open=value.questions_to_open,
                question_refs_to_resolve=value.question_refs_to_resolve,
            ),
        ),
    ]
    return ToolExecutor(
        tools,
        handled_errors=(ValueError, KeyError, RepositoryError),
    )


def _finalization_definition() -> LLMToolDefinition:
    tool = LLMTool.bind(
        name=FINALIZATION_TOOL_ID,
        description=(
            "Stop Stage 4 and transfer control to finalization. This must be the "
            "only tool call in the response."
        ),
        arguments_type=_EmptyArguments,
        handler=lambda _: None,
    )
    return tool.definition


def _yield_cycle_definition() -> LLMToolDefinition:
    tool = LLMTool.bind(
        name=YIELD_CYCLE_TOOL_ID,
        description=(
            "End the current bounded worker cycle after preserving useful progress. "
            "Use this when the current cycle objective is complete, or when a fresh "
            "hydrated context should continue it. This must be the only tool call in "
            "the response."
        ),
        arguments_type=_EmptyArguments,
        handler=lambda _: None,
    )
    return tool.definition


__all__ = [
    "FINALIZATION_TOOL_ID",
    "REPOSITORY_TOOL_IDS",
    "TARGET_TOOL_IDS",
    "WORKER_TOOL_IDS",
    "YIELD_CYCLE_TOOL_ID",
    "CompletionStateUpdater",
    "EvidenceRecorder",
    "ProgressUpdater",
    "TargetWorkspace",
    "WorkerToolRuntime",
]
