"""Hybrid retrieval and deterministic reads over one published Repository Brain."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

import numpy as np

from bridger.contracts._legacy_consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    IntelligenceResult,
    Lens,
    Provenance,
    ReadExpansion,
    ResultOperation,
    ScopeKind,
    Substrate,
)
from bridger.contracts.consumption import BrainContext
from bridger.repository_brain.embeddings import resolve_embedding_provider

if TYPE_CHECKING:
    from bridger.repository_brain.embeddings import EmbeddingProvider
    from bridger.repository_brain.loader import BrainDocument, LoadedRepositoryBrain

BM25_CANDIDATE_LIMIT = 30
DENSE_CANDIDATE_LIMIT = 30
DEFAULT_BRAIN_RESULT_LIMIT = 5
MAX_BRAIN_RESULT_LIMIT = 20
RRF_K = 60

_BM25_TITLE_WEIGHT = 10.0
_BM25_HEADING_WEIGHT = 5.0
_BM25_SEMANTIC_OWNER_WEIGHT = 1.5
_BM25_BODY_WEIGHT = 1.0

_GUARDRAIL_OWNERS = (
    "business-logic",
    "data-and-state",
    "interfaces-and-integrations",
    "conventions",
    "testing",
)
_DENSE_FAILURES = (RuntimeError, TypeError, ValueError)
_FTS_TOKEN = re.compile(r"\w+", re.UNICODE)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ChunkRecord:
    chunk_id: str
    document_id: str
    ordinal: int
    start_line: int
    end_line: int
    heading_path: str | None
    semantic_owner: str
    relative_path: str


@dataclass(frozen=True)
class _Candidate:
    chunk: _ChunkRecord
    bm25_score: float | None = None
    bm25_rank: int | None = None
    dense_rank: int | None = None
    fused_score: float | None = None


@dataclass(frozen=True)
class _Passage:
    document_id: str
    start_line: int
    end_line: int
    heading_path: str | None
    best_candidate: _Candidate


@dataclass(frozen=True)
class _BrainConstraint:
    document_id: str
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class BrainSearchResult:
    contexts: tuple[BrainContext, ...]
    truncated: bool
    warnings: tuple[str, ...] = ()


class BrainNavigator:
    """Read-only semantic navigation over one exact Repository Brain publication."""

    def __init__(
        self,
        publication_path: Path,
        *,
        repository_root: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        brain = _load_repository_brain(publication_path)
        provider, runtime_available = resolve_embedding_provider(embedding_provider)
        cache_root = Path(brain.manifest.memory_output_root).resolve().parent / "cache"
        index_path = _require_brain_index(brain, cache_root, provider)

        self._brain = brain
        self._repository_root = repository_root.resolve()
        self._repository_revision = brain.manifest.repository_revision
        self._documents = {
            document.document_id: document for document in brain.documents
        }
        self._embedding_provider = provider
        self._connection = sqlite3.connect(
            f"{index_path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        self._connection.row_factory = sqlite3.Row
        self._chunks = self._load_chunks()
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in self._chunks}
        self._chunks_by_document = _group_chunks(self._chunks)
        self._document_titles = dict(
            self._connection.execute("SELECT document_id, title FROM documents")
        )
        self._dense_available = runtime_available and self._index_has_dense_vectors()
        self._dense_chunk_ids: tuple[str, ...] | None = None
        self._dense_matrix: np.ndarray | None = None

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> BrainNavigator:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def repository_revision(self) -> str:
        """Return the immutable repository revision bound to this Brain."""
        return self._repository_revision

    def search_hybrid(
        self,
        query: str,
        *,
        limit: int = DEFAULT_BRAIN_RESULT_LIMIT,
    ) -> BrainSearchResult:
        """Retrieve bounded Brain context with lexical and dense ranking."""
        query = query.strip()
        if not query:
            raise ValueError("Brain search query must be non-empty")
        _validate_result_limit(limit)

        bm25_candidates = self._bm25_candidates(query, None)
        dense_candidates = self._dense_candidates(query, None)
        warnings = (
            ("dense Brain retrieval unavailable; used BM25 only",)
            if dense_candidates is None
            else ()
        )
        ranked = self._rank_candidates(
            bm25_candidates,
            dense_candidates or [],
            Lens.UNDERSTAND,
            hybrid=bool(dense_candidates),
        )
        passages = self._collapse_candidates(
            ranked,
            Lens.UNDERSTAND,
            hybrid=bool(dense_candidates),
            constraint=None,
        )
        return BrainSearchResult(
            contexts=tuple(self._brain_context(item) for item in passages[:limit]),
            truncated=len(passages) > limit,
            warnings=warnings,
        )

    def search_lexical(
        self,
        identifiers: Sequence[str],
        *,
        limit: int = DEFAULT_BRAIN_RESULT_LIMIT,
    ) -> BrainSearchResult:
        """Retrieve Brain context mentioning concrete repository identifiers."""
        _validate_result_limit(limit)
        expression = _fts_identifier_query(identifiers)
        if expression is None:
            return BrainSearchResult(contexts=(), truncated=False)

        candidates = self._bm25_expression_candidates(expression, None)
        ranked = self._rank_candidates(
            candidates,
            [],
            Lens.UNDERSTAND,
            hybrid=False,
        )
        passages = self._collapse_candidates(
            ranked,
            Lens.UNDERSTAND,
            hybrid=False,
            constraint=None,
        )
        return BrainSearchResult(
            contexts=tuple(self._brain_context(item) for item in passages[:limit]),
            truncated=len(passages) > limit,
        )

    def search(self, request: IntelligenceQueryRequest) -> IntelligenceResult:
        """Retrieve bounded contextual Brain passages for one consumption request."""
        limit = request.limit or DEFAULT_BRAIN_RESULT_LIMIT
        if limit > MAX_BRAIN_RESULT_LIMIT:
            raise ValueError(
                f"Brain result limit must be at most {MAX_BRAIN_RESULT_LIMIT}"
            )

        retrieval_text, constraint = self._retrieval_behavior(request)
        if request.query is None and request.scope is not None:
            if request.scope.kind is ScopeKind.BRAIN_REF:
                items = self._materialize_brain_scope(constraint)
                return self._search_result(request, items[:limit], len(items) > limit)
            if request.scope.kind is ScopeKind.REPOSITORY:
                passages, more_available = self._repository_passages(request.lens)
                items = [self._passage_item(passage) for passage in passages[:limit]]
                return self._search_result(
                    request,
                    items,
                    more_available or len(passages) > limit,
                )

        if not retrieval_text:
            return self._search_result(request, [], False)

        bm25_candidates = self._bm25_candidates(retrieval_text, constraint)
        dense_candidates = self._dense_candidates(retrieval_text, constraint)
        hybrid = bool(dense_candidates)
        ranked = self._rank_candidates(
            bm25_candidates,
            dense_candidates or [],
            request.lens,
            hybrid=hybrid,
        )
        passages = self._collapse_candidates(
            ranked,
            request.lens,
            hybrid=hybrid,
            constraint=constraint,
        )
        items = [self._passage_item(passage) for passage in passages[:limit]]
        return self._search_result(request, items, len(passages) > limit)

    def read(self, request: IntelligenceReadRequest) -> IntelligenceResult:
        """Resolve or deterministically expand an already addressed Brain object."""
        ref = request.ref
        self._require_revision(ref)
        if ref.kind is BridgerRefKind.BRAIN_CLAIM:
            raise NotImplementedError(
                "BRAIN_CLAIM is not supported by BrainNavigator V0"
            )
        if ref.kind not in {
            BridgerRefKind.BRAIN_CONTEXT,
            BridgerRefKind.BRAIN_DOCUMENT,
        }:
            raise ValueError("BrainNavigator can only read Brain refs")
        if request.expand in {ReadExpansion.CLAIM, ReadExpansion.EVIDENCE}:
            raise NotImplementedError(
                f"{request.expand.value.upper()} expansion is not supported "
                "for Brain refs"
            )

        if ref.kind is BridgerRefKind.BRAIN_DOCUMENT:
            document_id = self._document_target(ref)
            if request.expand is ReadExpansion.CONTEXT:
                raise ValueError("CONTEXT expansion requires a BRAIN_CONTEXT ref")
            item = self._document_item(document_id)
        else:
            document_id, start_line, end_line = self._context_target(ref)
            if request.expand is ReadExpansion.DOCUMENT:
                item = self._document_item(document_id)
            else:
                if request.expand is ReadExpansion.CONTEXT:
                    start_line, end_line = self._expanded_context_range(
                        document_id,
                        start_line,
                        end_line,
                    )
                item = self._context_item(document_id, start_line, end_line)

        return IntelligenceResult(
            operation=ResultOperation.READ,
            repository_revision=self._repository_revision,
            items=[item],
            completeness=Completeness(returned_count=1),
        )

    def expand(
        self,
        ref: BridgerRef,
        expansion: ReadExpansion,
    ) -> IntelligenceResult:
        """Delegate expansion to the single READ implementation."""
        return self.read(IntelligenceReadRequest(ref=ref, expand=expansion))

    def _retrieval_behavior(
        self,
        request: IntelligenceQueryRequest,
    ) -> tuple[str | None, _BrainConstraint | None]:
        query = request.query.strip() if request.query is not None else None
        scope = request.scope
        if scope is None or scope.kind is ScopeKind.REPOSITORY:
            return query, None
        if scope.kind is ScopeKind.BRAIN_REF:
            if not isinstance(scope.value, BridgerRef):
                raise ValueError("brain_ref scope requires a Brain ref")
            constraint = self._constraint_from_ref(scope.value)
            return query, constraint
        if scope.kind in {ScopeKind.PATH, ScopeKind.SYMBOL}:
            hint = str(scope.value)
        elif scope.kind is ScopeKind.GRAPH_ENTITY:
            value = (
                scope.value.target_ref
                if isinstance(scope.value, BridgerRef)
                else scope.value
            )
            hint = _stable_scope_text(value)
        else:
            raise ValueError("unsupported Brain retrieval scope")
        if query is None:
            return hint, None
        return f"{query} {hint}", None

    def _constraint_from_ref(self, ref: BridgerRef) -> _BrainConstraint:
        self._require_revision(ref)
        if ref.kind is BridgerRefKind.BRAIN_CLAIM:
            raise NotImplementedError(
                "BRAIN_CLAIM is not supported by BrainNavigator V0"
            )
        if ref.kind is BridgerRefKind.BRAIN_DOCUMENT:
            document_id = self._document_target(ref)
            return _BrainConstraint(document_id=document_id)
        if ref.kind is BridgerRefKind.BRAIN_CONTEXT:
            document_id, start_line, end_line = self._context_target(ref)
            return _BrainConstraint(document_id, start_line, end_line)
        raise ValueError("brain_ref scope requires a Brain ref")

    def _bm25_candidates(
        self,
        retrieval_text: str,
        constraint: _BrainConstraint | None,
    ) -> list[_Candidate]:
        expression = _fts_query(retrieval_text)
        if expression is None:
            return []
        return self._bm25_expression_candidates(expression, constraint)

    def _bm25_expression_candidates(
        self,
        expression: str,
        constraint: _BrainConstraint | None,
    ) -> list[_Candidate]:
        sql = f"""
            SELECT
                chunks_fts.chunk_id,
                bm25(
                    chunks_fts,
                    0.0,
                    0.0,
                    {_BM25_TITLE_WEIGHT},
                    {_BM25_HEADING_WEIGHT},
                    {_BM25_SEMANTIC_OWNER_WEIGHT},
                    {_BM25_BODY_WEIGHT}
                ) AS relevance
            FROM chunks_fts
            JOIN chunks ON chunks.chunk_id = chunks_fts.chunk_id
            JOIN documents ON documents.document_id = chunks.document_id
            WHERE chunks_fts MATCH ?
        """
        parameters: list[object] = [expression]
        if constraint is not None:
            sql += " AND chunks.document_id = ?"
            parameters.append(constraint.document_id)
            if constraint.start_line is not None and constraint.end_line is not None:
                sql += " AND chunks.start_line <= ? AND chunks.end_line >= ?"
                parameters.extend([constraint.end_line, constraint.start_line])
        sql += " ORDER BY relevance, documents.relative_path, chunks.ordinal LIMIT ?"
        parameters.append(BM25_CANDIDATE_LIMIT)
        rows = self._connection.execute(sql, parameters).fetchall()
        return [
            _Candidate(
                chunk=self._chunks_by_id[row["chunk_id"]],
                bm25_score=float(row["relevance"]),
                bm25_rank=rank,
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def _dense_candidates(
        self,
        retrieval_text: str,
        constraint: _BrainConstraint | None,
    ) -> list[_Candidate] | None:
        if not self._dense_available:
            return None
        try:
            query = np.asarray(
                self._embedding_provider.embed_query(retrieval_text),
                dtype=np.float32,
            )
            if query.shape != (_embedding_dimension(),):
                raise ValueError("query embedding must have 512 dimensions")
            if not np.isfinite(query).all() or not np.isclose(
                np.linalg.norm(query),
                1.0,
                rtol=1e-4,
                atol=1e-5,
            ):
                raise ValueError("query embedding must be finite and L2 normalized")
            chunk_ids, matrix = self._dense_vectors()
            similarities = matrix @ query
        except _DENSE_FAILURES:
            _LOGGER.warning(
                "dense Brain retrieval unavailable; continuing with BM25",
                exc_info=True,
            )
            self._dense_available = False
            self._dense_chunk_ids = None
            self._dense_matrix = None
            return None

        eligible = []
        for index, chunk_id in enumerate(chunk_ids):
            chunk = self._chunks_by_id[chunk_id]
            if not _matches_constraint(chunk, constraint):
                continue
            eligible.append((float(similarities[index]), chunk))
        eligible.sort(
            key=lambda item: (-item[0], item[1].relative_path, item[1].ordinal)
        )
        return [
            _Candidate(chunk=chunk, dense_rank=rank)
            for rank, (_similarity, chunk) in enumerate(
                eligible[:DENSE_CANDIDATE_LIMIT],
                start=1,
            )
        ]

    def _dense_vectors(self) -> tuple[tuple[str, ...], np.ndarray]:
        if self._dense_chunk_ids is not None and self._dense_matrix is not None:
            return self._dense_chunk_ids, self._dense_matrix
        rows = self._connection.execute("""
            SELECT chunk_id, embedding
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY document_id, ordinal
            """).fetchall()
        chunk_ids: list[str] = []
        vectors: list[np.ndarray] = []
        for row in rows:
            vector = np.frombuffer(row["embedding"], dtype=np.float32)
            if vector.shape != (_embedding_dimension(),):
                raise ValueError("stored Brain embedding must have 512 dimensions")
            if not np.isfinite(vector).all() or not np.isclose(
                np.linalg.norm(vector),
                1.0,
                rtol=1e-4,
                atol=1e-5,
            ):
                raise ValueError("stored Brain embedding must be L2 normalized")
            chunk_ids.append(row["chunk_id"])
            vectors.append(vector)
        if not vectors:
            raise ValueError("Brain index does not contain dense vectors")
        self._dense_chunk_ids = tuple(chunk_ids)
        self._dense_matrix = np.ascontiguousarray(np.stack(vectors), dtype=np.float32)
        return self._dense_chunk_ids, self._dense_matrix

    def _rank_candidates(
        self,
        bm25: list[_Candidate],
        dense: list[_Candidate],
        lens: Lens,
        *,
        hybrid: bool,
    ) -> list[_Candidate]:
        bm25_by_id = {candidate.chunk.chunk_id: candidate for candidate in bm25}
        dense_by_id = {candidate.chunk.chunk_id: candidate for candidate in dense}
        chunk_ids = list(bm25_by_id)
        chunk_ids.extend(
            chunk_id for chunk_id in dense_by_id if chunk_id not in bm25_by_id
        )
        candidates: list[_Candidate] = []
        for chunk_id in chunk_ids:
            lexical = bm25_by_id.get(chunk_id)
            semantic = dense_by_id.get(chunk_id)
            candidate = lexical or semantic
            assert candidate is not None
            bm25_rank = lexical.bm25_rank if lexical is not None else None
            dense_rank = semantic.dense_rank if semantic is not None else None
            fused_score = None
            if hybrid:
                fused_score = (
                    1 / (RRF_K + bm25_rank) if bm25_rank is not None else 0
                ) + (1 / (RRF_K + dense_rank) if dense_rank is not None else 0)
            candidates.append(
                replace(
                    candidate,
                    bm25_score=lexical.bm25_score if lexical is not None else None,
                    bm25_rank=bm25_rank,
                    dense_rank=dense_rank,
                    fused_score=fused_score,
                )
            )
        candidates.sort(key=lambda item: _candidate_key(item, lens, hybrid=hybrid))
        return candidates

    def _collapse_candidates(
        self,
        candidates: list[_Candidate],
        lens: Lens,
        *,
        hybrid: bool,
        constraint: _BrainConstraint | None,
    ) -> list[_Passage]:
        by_document: dict[str, list[_Candidate]] = {}
        for candidate in candidates:
            by_document.setdefault(candidate.chunk.document_id, []).append(candidate)

        passages: list[_Passage] = []
        for document_candidates in by_document.values():
            ordered = sorted(document_candidates, key=lambda item: item.chunk.ordinal)
            groups: list[list[_Candidate]] = []
            for candidate in ordered:
                if not groups:
                    groups.append([candidate])
                    continue
                previous = groups[-1][-1].chunk
                current = candidate.chunk
                if (
                    current.ordinal <= previous.ordinal + 1
                    or current.start_line <= previous.end_line
                ):
                    groups[-1].append(candidate)
                else:
                    groups.append([candidate])
            for group in groups:
                best = min(
                    group,
                    key=lambda item: _candidate_key(item, lens, hybrid=hybrid),
                )
                start_line = min(item.chunk.start_line for item in group)
                end_line = max(item.chunk.end_line for item in group)
                if constraint is not None and constraint.start_line is not None:
                    start_line = max(start_line, constraint.start_line)
                    end_line = min(end_line, constraint.end_line or end_line)
                passages.append(
                    _Passage(
                        document_id=best.chunk.document_id,
                        start_line=start_line,
                        end_line=end_line,
                        heading_path=best.chunk.heading_path,
                        best_candidate=best,
                    )
                )
        passages.sort(
            key=lambda passage: (
                _candidate_key(passage.best_candidate, lens, hybrid=hybrid),
                passage.start_line,
            )
        )
        return passages

    def _repository_passages(self, lens: Lens) -> tuple[list[_Passage], bool]:
        representatives = [
            chunks[0] for chunks in self._chunks_by_document.values() if chunks
        ]
        if lens is Lens.UNDERSTAND:
            representatives.sort(
                key=lambda chunk: (
                    chunk.semantic_owner != "repository",
                    chunk.relative_path,
                    chunk.ordinal,
                )
            )
        elif lens is Lens.GUARDRAILS:
            representatives.sort(
                key=lambda chunk: (
                    _owner_priority(chunk.semantic_owner, lens),
                    chunk.relative_path,
                    chunk.ordinal,
                )
            )
        else:
            representatives.sort(key=lambda chunk: (chunk.relative_path, chunk.ordinal))
        more_available = len(representatives) > BM25_CANDIDATE_LIMIT
        passages = [
            _Passage(
                document_id=chunk.document_id,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                heading_path=chunk.heading_path,
                best_candidate=_Candidate(chunk=chunk),
            )
            for chunk in representatives[:BM25_CANDIDATE_LIMIT]
        ]
        return passages, more_available

    def _materialize_brain_scope(
        self,
        constraint: _BrainConstraint | None,
    ) -> list[IntelligenceItem]:
        if constraint is None:
            return []
        if constraint.start_line is not None and constraint.end_line is not None:
            return [
                self._context_item(
                    constraint.document_id,
                    constraint.start_line,
                    constraint.end_line,
                )
            ]
        chunks = self._chunks_by_document.get(constraint.document_id, [])
        if not chunks:
            return []
        chunk = chunks[0]
        return [
            self._context_item(
                chunk.document_id,
                chunk.start_line,
                chunk.end_line,
                heading_path=chunk.heading_path,
            )
        ]

    def _passage_item(self, passage: _Passage) -> IntelligenceItem:
        return self._context_item(
            passage.document_id,
            passage.start_line,
            passage.end_line,
            heading_path=passage.heading_path,
        )

    def _brain_context(self, passage: _Passage) -> BrainContext:
        document = self._require_document(passage.document_id)
        document_path = (
            Path(self._brain.manifest.memory_output_root) / document.relative_path
        ).resolve()
        try:
            path = document_path.relative_to(self._repository_root).as_posix()
        except ValueError:
            raise ValueError(
                "Brain artifact is outside the repository root: " f"{document_path}"
            ) from None
        heading = passage.heading_path or self._heading_for_range(
            passage.document_id,
            passage.start_line,
            passage.end_line,
        )
        return BrainContext(
            path=path,
            heading=heading,
            start_line=passage.start_line,
            end_line=passage.end_line,
            excerpt=_canonical_range(
                document,
                passage.start_line,
                passage.end_line,
            ),
            semantic_owner=document.semantic_owner,
        )

    def _context_item(
        self,
        document_id: str,
        start_line: int,
        end_line: int,
        *,
        heading_path: str | None = None,
    ) -> IntelligenceItem:
        document = self._require_document(document_id)
        content = _canonical_range(document, start_line, end_line)
        document_ref = self._document_ref(document_id)
        context_ref = self._context_ref(document_id, start_line, end_line)
        heading = heading_path or self._heading_for_range(
            document_id,
            start_line,
            end_line,
        )
        title = (
            heading.rsplit(" > ", 1)[-1]
            if heading
            else self._document_titles[document_id]
        )
        return IntelligenceItem(
            ref=context_ref,
            kind=BridgerRefKind.BRAIN_CONTEXT,
            title=title,
            content=content,
            document_ref=document_ref,
            context_ref=context_ref,
            matched_claim_refs=[],
            evidence_refs=[],
            related_refs=[],
            semantic_owner=document.semantic_owner,
            provenance=self._provenance(),
        )

    def _document_item(self, document_id: str) -> IntelligenceItem:
        document = self._require_document(document_id)
        document_ref = self._document_ref(document_id)
        return IntelligenceItem(
            ref=document_ref,
            kind=BridgerRefKind.BRAIN_DOCUMENT,
            title=self._document_titles[document_id],
            content=document.content,
            document_ref=document_ref,
            matched_claim_refs=[],
            evidence_refs=[],
            related_refs=[],
            semantic_owner=document.semantic_owner,
            provenance=self._provenance(),
        )

    def _expanded_context_range(
        self,
        document_id: str,
        start_line: int,
        end_line: int,
    ) -> tuple[int, int]:
        chunks = self._chunks_by_document.get(document_id, [])
        overlapping = [
            index
            for index, chunk in enumerate(chunks)
            if chunk.start_line <= end_line and chunk.end_line >= start_line
        ]
        if not overlapping:
            return start_line, end_line
        first = max(0, min(overlapping) - 1)
        last = min(len(chunks) - 1, max(overlapping) + 1)
        return (
            min(start_line, chunks[first].start_line),
            max(end_line, chunks[last].end_line),
        )

    def _heading_for_range(
        self,
        document_id: str,
        start_line: int,
        end_line: int,
    ) -> str | None:
        return next(
            (
                chunk.heading_path
                for chunk in self._chunks_by_document.get(document_id, [])
                if chunk.start_line <= end_line
                and chunk.end_line >= start_line
                and chunk.heading_path
            ),
            None,
        )

    def _document_target(self, ref: BridgerRef) -> str:
        target = ref.target_ref
        if not isinstance(target, dict) or set(target) != {"document_id"}:
            raise ValueError("BRAIN_DOCUMENT ref requires only document_id")
        document_id = target["document_id"]
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("BRAIN_DOCUMENT document_id must be non-empty")
        self._require_document(document_id)
        return document_id

    def _context_target(self, ref: BridgerRef) -> tuple[str, int, int]:
        target = ref.target_ref
        if not isinstance(target, dict) or set(target) != {
            "document_id",
            "start_line",
            "end_line",
        }:
            raise ValueError(
                "BRAIN_CONTEXT ref requires document_id, start_line, and end_line"
            )
        document_id = target["document_id"]
        start_line = target["start_line"]
        end_line = target["end_line"]
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("BRAIN_CONTEXT document_id must be non-empty")
        if (
            not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
        ):
            raise ValueError("BRAIN_CONTEXT lines must be integers")
        document = self._require_document(document_id)
        _canonical_range(document, start_line, end_line)
        return document_id, start_line, end_line

    def _require_document(self, document_id: str) -> BrainDocument:
        try:
            return self._documents[document_id]
        except KeyError:
            raise KeyError(f"unknown Brain document: {document_id}") from None

    def _require_revision(self, ref: BridgerRef) -> None:
        if ref.repository_revision != self._repository_revision:
            raise ValueError("Brain ref belongs to a different repository revision")

    def _document_ref(self, document_id: str) -> BridgerRef:
        return BridgerRef(
            kind=BridgerRefKind.BRAIN_DOCUMENT,
            target_ref={"document_id": document_id},
            repository_revision=self._repository_revision,
        )

    def _context_ref(
        self,
        document_id: str,
        start_line: int,
        end_line: int,
    ) -> BridgerRef:
        return BridgerRef(
            kind=BridgerRefKind.BRAIN_CONTEXT,
            target_ref={
                "document_id": document_id,
                "start_line": start_line,
                "end_line": end_line,
            },
            repository_revision=self._repository_revision,
        )

    def _provenance(self) -> Provenance:
        return Provenance(
            repository_revision=self._repository_revision,
            substrate=Substrate.BRAIN,
            authority=Authority.DERIVED,
        )

    def _search_result(
        self,
        request: IntelligenceQueryRequest,
        items: list[IntelligenceItem],
        more_available: bool,
    ) -> IntelligenceResult:
        return IntelligenceResult(
            operation=ResultOperation.QUERY,
            repository_revision=self._repository_revision,
            lens=request.lens,
            query=request.query,
            scope=request.scope,
            items=items,
            completeness=Completeness(
                returned_count=len(items),
                truncated=more_available,
                more_available=more_available,
            ),
        )

    def _load_chunks(self) -> tuple[_ChunkRecord, ...]:
        rows = self._connection.execute("""
            SELECT
                chunks.chunk_id,
                chunks.document_id,
                chunks.ordinal,
                chunks.start_line,
                chunks.end_line,
                chunks.heading_path,
                documents.semantic_owner,
                documents.relative_path
            FROM chunks
            JOIN documents ON documents.document_id = chunks.document_id
            ORDER BY documents.relative_path, chunks.ordinal
            """).fetchall()
        return tuple(_ChunkRecord(**dict(row)) for row in rows)

    def _index_has_dense_vectors(self) -> bool:
        metadata = dict(self._connection.execute("SELECT key, value FROM metadata"))
        expected_dimension = _embedding_dimension()
        try:
            provider_model = self._embedding_provider.model_id
            provider_dimension = self._embedding_provider.dimension
        except _DENSE_FAILURES:
            return False
        if (
            provider_dimension != expected_dimension
            or metadata.get("embedding_model_id") != provider_model
            or metadata.get("embedding_dimension") != str(expected_dimension)
        ):
            return False
        return (
            self._connection.execute(
                "SELECT 1 FROM chunks WHERE embedding IS NOT NULL LIMIT 1"
            ).fetchone()
            is not None
        )


def _fts_query(retrieval_text: str) -> str | None:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _FTS_TOKEN.finditer(retrieval_text):
        token = match.group(0)
        identity = token.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        tokens.append(token.replace('"', '""'))
    if not tokens:
        return None
    return " OR ".join(f'"{token}"' for token in tokens)


def _fts_identifier_query(identifiers: Sequence[str]) -> str | None:
    phrases: list[str] = []
    seen: set[str] = set()
    for identifier in identifiers:
        tokens = [match.group(0) for match in _FTS_TOKEN.finditer(identifier.strip())]
        if not tokens:
            continue
        phrase = " ".join(tokens)
        identity = phrase.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        phrases.append(phrase.replace('"', '""'))
    if not phrases:
        return None
    return " OR ".join(f'"{phrase}"' for phrase in phrases)


def _validate_result_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Brain result limit must be a positive integer")
    if limit > MAX_BRAIN_RESULT_LIMIT:
        raise ValueError(f"Brain result limit must be at most {MAX_BRAIN_RESULT_LIMIT}")


def _stable_scope_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _candidate_key(
    candidate: _Candidate,
    lens: Lens,
    *,
    hybrid: bool,
) -> tuple[object, ...]:
    owner = _owner_priority(candidate.chunk.semantic_owner, lens)
    bm25_rank = candidate.bm25_rank or BM25_CANDIDATE_LIMIT + 1
    dense_rank = candidate.dense_rank or DENSE_CANDIDATE_LIMIT + 1
    if hybrid:
        relevance: tuple[object, ...] = (-float(candidate.fused_score or 0), owner)
    else:
        relevance = (
            candidate.bm25_score if candidate.bm25_score is not None else float("inf"),
            owner,
        )
    return (
        *relevance,
        bm25_rank,
        dense_rank,
        candidate.chunk.relative_path,
        candidate.chunk.ordinal,
    )


def _owner_priority(semantic_owner: str, lens: Lens) -> int:
    if lens is not Lens.GUARDRAILS:
        return 0
    try:
        return _GUARDRAIL_OWNERS.index(semantic_owner)
    except ValueError:
        return len(_GUARDRAIL_OWNERS)


def _matches_constraint(
    chunk: _ChunkRecord,
    constraint: _BrainConstraint | None,
) -> bool:
    if constraint is None:
        return True
    if chunk.document_id != constraint.document_id:
        return False
    if constraint.start_line is None or constraint.end_line is None:
        return True
    return (
        chunk.start_line <= constraint.end_line
        and chunk.end_line >= constraint.start_line
    )


def _group_chunks(
    chunks: tuple[_ChunkRecord, ...],
) -> dict[str, list[_ChunkRecord]]:
    grouped: dict[str, list[_ChunkRecord]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.document_id, []).append(chunk)
    for document_chunks in grouped.values():
        document_chunks.sort(key=lambda chunk: chunk.ordinal)
    return grouped


def _canonical_range(
    document: BrainDocument,
    start_line: int,
    end_line: int,
) -> str:
    lines = document.content.splitlines(keepends=True)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError("Brain context range is outside the canonical document")
    return "".join(lines[start_line - 1 : end_line])


def _embedding_dimension() -> int:
    from bridger.repository_brain.embeddings import EMBEDDING_DIMENSION

    return EMBEDDING_DIMENSION


def _load_repository_brain(publication_path: Path) -> LoadedRepositoryBrain:
    from bridger.repository_brain.loader import load_repository_brain

    return load_repository_brain(publication_path)


def _require_brain_index(
    brain: LoadedRepositoryBrain,
    cache_root: Path,
    provider: EmbeddingProvider,
) -> Path:
    from bridger.repository_brain.index import require_brain_index

    return require_brain_index(brain, cache_root, provider)


__all__ = ["BrainNavigator", "BrainSearchResult"]
