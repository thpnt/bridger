"""Deterministic SQLite index derived from a loaded Repository Brain."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import numpy as np

from bridger.repository_brain.embeddings import EmbeddingProvider
from bridger.repository_brain.loader import BrainDocument, LoadedRepositoryBrain

BRAIN_INDEX_SCHEMA_VERSION = 1
BRAIN_CHUNK_TARGET_TOKENS = 512
BRAIN_CHUNK_OVERLAP_TOKENS = 64

_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_H1_PATTERN = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_LOGGER = logging.getLogger(__name__)


class BrainIndexError(RuntimeError):
    """A Repository Brain index could not be built or validated."""


@dataclass(frozen=True)
class _SourceLine:
    number: int
    text: str
    heading_path: str | None


@dataclass(frozen=True)
class _Block:
    lines: tuple[_SourceLine, ...]
    starts_heading: bool = False


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    document_id: str
    ordinal: int
    start_line: int
    end_line: int
    heading_path: str | None
    text: str


def build_brain_index(
    brain: LoadedRepositoryBrain,
    cache_root: Path,
    embedding_provider: EmbeddingProvider,
) -> Path:
    """Build and atomically publish one complete derived Brain index."""
    destination = _index_path(brain, cache_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp-{uuid4().hex}")
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                _create_schema(connection)
                _populate_index(connection, brain, embedding_provider)
                _validate_index(connection, len(brain.documents))
        finally:
            connection.close()
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(destination)
        _fsync_directory(destination.parent)
        return destination
    except BrainIndexError:
        raise
    except Exception as error:
        raise BrainIndexError("could not build Repository Brain index") from error
    finally:
        temporary.unlink(missing_ok=True)


def ensure_brain_index(
    brain: LoadedRepositoryBrain,
    cache_root: Path,
    embedding_provider: EmbeddingProvider,
) -> Path:
    """Reuse an identity-matching index, otherwise rebuild it completely."""
    destination = _index_path(brain, cache_root)
    if destination.is_file() and _metadata_matches(
        destination,
        brain,
        embedding_provider,
    ):
        return destination
    return build_brain_index(brain, cache_root, embedding_provider)


def _index_path(brain: LoadedRepositoryBrain, cache_root: Path) -> Path:
    if (
        not brain.publication_id
        or Path(brain.publication_id).name != brain.publication_id
    ):
        raise BrainIndexError("invalid Repository Brain publication identity")
    return cache_root / "brain" / brain.publication_id / "brain.sqlite3"


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY,
            semantic_owner TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            artifact_revision INTEGER NOT NULL,
            digest TEXT NOT NULL
        );

        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            heading_path TEXT,
            text TEXT NOT NULL,
            embedding BLOB,
            UNIQUE(document_id, ordinal),
            FOREIGN KEY(document_id) REFERENCES documents(document_id)
        );

        CREATE TABLE links (
            source_document_id TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            target_document_id TEXT NOT NULL,
            target_anchor TEXT,
            PRIMARY KEY (
                source_document_id,
                source_line,
                target_document_id,
                target_anchor
            ),
            FOREIGN KEY(source_document_id) REFERENCES documents(document_id),
            FOREIGN KEY(target_document_id) REFERENCES documents(document_id)
        );

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            title,
            heading_path,
            semantic_owner,
            text
        );
        """)


def _populate_index(
    connection: sqlite3.Connection,
    brain: LoadedRepositoryBrain,
    embedding_provider: EmbeddingProvider,
) -> None:
    metadata = _base_metadata(brain)
    chunks: list[_Chunk] = []
    titles: dict[str, str] = {}
    documents_by_id = {document.document_id: document for document in brain.documents}
    for document in brain.documents:
        title = _document_title(document)
        titles[document.document_id] = title
        connection.execute(
            """
            INSERT INTO documents (
                document_id,
                semantic_owner,
                relative_path,
                title,
                artifact_revision,
                digest
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document.document_id,
                document.semantic_owner,
                document.relative_path,
                title,
                document.artifact_revision,
                document.digest,
            ),
        )
        chunks.extend(_chunk_document(document, embedding_provider))

    embeddings: np.ndarray | None = None
    if chunks:
        try:
            candidate = np.asarray(
                embedding_provider.embed_documents([chunk.text for chunk in chunks]),
                dtype=np.float32,
            )
            expected_shape = (len(chunks), embedding_provider.dimension)
            if candidate.shape != expected_shape:
                raise ValueError(
                    f"embedding shape {candidate.shape} does not match {expected_shape}"
                )
            if not np.isfinite(candidate).all():
                raise ValueError("embeddings contain non-finite values")
            embeddings = np.ascontiguousarray(candidate, dtype=np.float32)
            metadata["embedding_model_id"] = embedding_provider.model_id
            metadata["embedding_dimension"] = str(embedding_provider.dimension)
        except Exception:
            _LOGGER.warning(
                "dense Repository Brain indexing unavailable; retaining lexical index",
                exc_info=True,
            )

    for index, chunk in enumerate(chunks):
        embedding = None
        if embeddings is not None:
            vector = embeddings[index]
            if vector.shape != (embedding_provider.dimension,):
                raise BrainIndexError("embedding dimension changed during persistence")
            embedding = vector.tobytes(order="C")
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id,
                document_id,
                ordinal,
                start_line,
                end_line,
                heading_path,
                text,
                embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                chunk.document_id,
                chunk.ordinal,
                chunk.start_line,
                chunk.end_line,
                chunk.heading_path,
                chunk.text,
                embedding,
            ),
        )
        document = documents_by_id[chunk.document_id]
        connection.execute(
            """
            INSERT INTO chunks_fts (
                chunk_id,
                document_id,
                title,
                heading_path,
                semantic_owner,
                text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                chunk.document_id,
                titles[chunk.document_id],
                chunk.heading_path,
                document.semantic_owner,
                chunk.text,
            ),
        )

    _insert_links(connection, brain)
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


def _base_metadata(brain: LoadedRepositoryBrain) -> dict[str, str]:
    encoded_manifest = json.dumps(
        brain.manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "index_schema_version": str(BRAIN_INDEX_SCHEMA_VERSION),
        "publication_id": brain.publication_id,
        "repository_revision": brain.manifest.repository_revision,
        "manifest_digest": hashlib.sha256(encoded_manifest).hexdigest(),
        "chunk_target_tokens": str(BRAIN_CHUNK_TARGET_TOKENS),
        "chunk_overlap_tokens": str(BRAIN_CHUNK_OVERLAP_TOKENS),
    }


def _metadata_matches(
    index_path: Path,
    brain: LoadedRepositoryBrain,
    embedding_provider: EmbeddingProvider,
) -> bool:
    try:
        connection = sqlite3.connect(index_path)
        try:
            existing = dict(connection.execute("SELECT key, value FROM metadata"))
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return False
    expected = _base_metadata(brain)
    if any(existing.get(key) != value for key, value in expected.items()):
        return False
    model_id = existing.get("embedding_model_id")
    dimension = existing.get("embedding_dimension")
    if model_id is None and dimension is None:
        return True
    return model_id == embedding_provider.model_id and dimension == str(
        embedding_provider.dimension
    )


def _chunk_document(
    document: BrainDocument,
    embedding_provider: EmbeddingProvider,
) -> list[_Chunk]:
    blocks = _markdown_blocks(document.content)
    chunks: list[_Chunk] = []
    buffered: list[_SourceLine] = []

    def emit(lines: list[_SourceLine]) -> None:
        text = _render_lines(lines).strip()
        if not text:
            return
        ordinal = len(chunks)
        chunks.append(
            _Chunk(
                chunk_id=f"{document.document_id}:{ordinal}",
                document_id=document.document_id,
                ordinal=ordinal,
                start_line=lines[0].number,
                end_line=lines[-1].number,
                heading_path=next(
                    (line.heading_path for line in lines if line.text.strip()),
                    None,
                ),
                text=text,
            )
        )

    def add_unit(lines: list[_SourceLine]) -> None:
        nonlocal buffered
        unit_tokens = embedding_provider.count_tokens(_render_lines(lines))
        if unit_tokens > BRAIN_CHUNK_TARGET_TOKENS:
            if len(lines) > 1:
                for line in lines:
                    add_unit([line])
                return
            if buffered:
                emit(buffered)
                buffered = []
            emit(lines)
            return
        candidate = [*buffered, *lines]
        if buffered and (
            embedding_provider.count_tokens(_render_lines(candidate))
            > BRAIN_CHUNK_TARGET_TOKENS
        ):
            emitted = buffered
            emit(emitted)
            overlap_limit = min(
                BRAIN_CHUNK_OVERLAP_TOKENS,
                max(0, BRAIN_CHUNK_TARGET_TOKENS - unit_tokens),
            )
            buffered = _trailing_overlap(
                emitted,
                overlap_limit,
                embedding_provider,
            )
        buffered.extend(lines)

    for block in blocks:
        if block.starts_heading and buffered:
            emit(buffered)
            buffered = []
        add_unit(list(block.lines))
    if buffered:
        emit(buffered)
    return chunks


def _markdown_blocks(content: str) -> list[_Block]:
    headings: list[str | None] = [None] * 6
    blocks: list[_Block] = []
    paragraph: list[_SourceLine] = []

    def finish_paragraph() -> None:
        if paragraph:
            blocks.append(_Block(lines=tuple(paragraph)))
            paragraph.clear()

    for number, text in enumerate(content.splitlines(), start=1):
        heading = _HEADING_PATTERN.match(text)
        if heading:
            finish_paragraph()
            level = len(heading.group(1))
            headings[level - 1] = heading.group(2).strip()
            for index in range(level, len(headings)):
                headings[index] = None
            path = " > ".join(item for item in headings[:level] if item)
            blocks.append(
                _Block(
                    lines=(_SourceLine(number, text, path or None),),
                    starts_heading=True,
                )
            )
            continue
        if not text.strip():
            finish_paragraph()
            continue
        path = " > ".join(item for item in headings if item)
        paragraph.append(_SourceLine(number, text, path or None))
    finish_paragraph()
    return blocks


def _trailing_overlap(
    lines: list[_SourceLine],
    token_limit: int,
    embedding_provider: EmbeddingProvider,
) -> list[_SourceLine]:
    if token_limit <= 0:
        return []
    selected: list[_SourceLine] = []
    for line in reversed(lines):
        candidate = [line, *selected]
        if embedding_provider.count_tokens(_render_lines(candidate)) > token_limit:
            break
        selected = candidate
    return selected


def _render_lines(lines: list[_SourceLine]) -> str:
    if not lines:
        return ""
    parts = [lines[0].text]
    for previous, current in zip(lines, lines[1:]):
        parts.append("\n" * max(1, current.number - previous.number))
        parts.append(current.text)
    return "".join(parts)


def _document_title(document: BrainDocument) -> str:
    for line in document.content.splitlines():
        match = _H1_PATTERN.match(line)
        if match:
            return match.group(1).strip()
    return PurePosixPath(document.relative_path).stem


def _insert_links(
    connection: sqlite3.Connection,
    brain: LoadedRepositoryBrain,
) -> None:
    documents_by_path = {
        document.relative_path: document.document_id for document in brain.documents
    }
    inserted: set[tuple[str, int, str, str | None]] = set()
    for document in brain.documents:
        for line_number, line in enumerate(document.content.splitlines(), start=1):
            for match in _LINK_PATTERN.finditer(line):
                target = _resolve_link(document.relative_path, match.group(1))
                if target is None:
                    continue
                target_path, anchor = target
                target_document_id = documents_by_path.get(target_path)
                if target_document_id is None:
                    continue
                identity = (
                    document.document_id,
                    line_number,
                    target_document_id,
                    anchor,
                )
                if identity in inserted:
                    continue
                inserted.add(identity)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO links (
                        source_document_id,
                        source_line,
                        target_document_id,
                        target_anchor
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        document.document_id,
                        line_number,
                        target_document_id,
                        anchor,
                    ),
                )


def _resolve_link(
    source_relative_path: str,
    raw_target: str,
) -> tuple[str, str | None] | None:
    destination = raw_target.strip().split(maxsplit=1)[0].strip("<>")
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc or parsed.query:
        return None
    path = unquote(parsed.path)
    if not path:
        resolved = source_relative_path
    elif path.startswith("/"):
        resolved = posixpath.normpath(path.lstrip("/"))
    else:
        parent = str(PurePosixPath(source_relative_path).parent)
        resolved = posixpath.normpath(posixpath.join(parent, path))
    if resolved == ".." or resolved.startswith("../") or not resolved.endswith(".md"):
        return None
    return resolved, unquote(parsed.fragment) or None


def _validate_index(connection: sqlite3.Connection, document_count: int) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        raise BrainIndexError("SQLite integrity validation failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise BrainIndexError("SQLite foreign-key validation failed")
    persisted_documents = connection.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0]
    chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts_count = connection.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    if persisted_documents != document_count or chunk_count != fts_count:
        raise BrainIndexError("Repository Brain index inventory is incomplete")
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    dimension = metadata.get("embedding_dimension")
    if dimension is not None:
        invalid = connection.execute(
            """
            SELECT COUNT(*)
            FROM chunks
            WHERE embedding IS NULL OR length(embedding) != ?
            """,
            (int(dimension) * np.dtype(np.float32).itemsize,),
        ).fetchone()[0]
        if invalid:
            raise BrainIndexError("persisted embedding dimension is invalid")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "BRAIN_CHUNK_OVERLAP_TOKENS",
    "BRAIN_CHUNK_TARGET_TOKENS",
    "BRAIN_INDEX_SCHEMA_VERSION",
    "BrainIndexError",
    "build_brain_index",
    "ensure_brain_index",
]
