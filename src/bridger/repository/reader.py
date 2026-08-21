"""Controlled, revision-bound access to indexed repository file contents."""

import hashlib

from bridger.contracts.files import (
    BOUNDED_READ_MAX_BYTES,
    FileIndex,
    SourceReadRequest,
    SourceReadResult,
)
from bridger.contracts.repository import RepositoryContext
from bridger.repository.errors import RepositoryError, SourceReadDeniedError
from bridger.repository.git import normalize_repository_path, run_git


def read_file(
    context: RepositoryContext,
    file_index: FileIndex,
    request: SourceReadRequest,
) -> SourceReadResult:
    """Read one indexed Git blob without allowing the request to widen policy."""
    _validate_index_context(context, file_index)
    path = normalize_repository_path(request.path)
    record = next((file for file in file_index.files if file.path == path), None)
    if record is None:
        raise RepositoryError(f"path is absent from the FileIndex: {path}")
    if record.disposition.read_mode == "denied":
        raise SourceReadDeniedError(f"source reads are denied for {path}")

    revision_object_id = (
        run_git(
            context.root_path,
            "rev-parse",
            f"{context.revision}:{path}",
        )
        .decode("ascii")
        .strip()
    )
    if revision_object_id != record.git_object_id:
        raise RepositoryError(
            f"FileIndex object does not match repository revision: {path}"
        )
    content_bytes = run_git(
        context.root_path,
        "cat-file",
        "-p",
        f"{context.revision}:{path}",
    )
    content, encoding = _decode_content(content_bytes)
    selected_content, start_line, end_line = _select_lines(content, request, path)
    limit = _effective_byte_limit(record.disposition.read_mode, request.max_bytes)
    bounded_content, truncated = _truncate_content(selected_content, encoding, limit)
    return SourceReadResult(
        path=path,
        revision=context.revision,
        content=bounded_content,
        start_line=start_line,
        end_line=end_line,
        content_digest=hashlib.sha256(content_bytes).hexdigest(),
        encoding=encoding,
        truncated=truncated,
    )


def _validate_index_context(context: RepositoryContext, file_index: FileIndex) -> None:
    if (
        file_index.repository_id != context.repository_id
        or file_index.revision != context.revision
        or file_index.scope_path != context.scope_path
    ):
        raise RepositoryError(
            "FileIndex does not belong to the supplied RepositoryContext"
        )


def _decode_content(content_bytes: bytes) -> tuple[str, str]:
    try:
        return content_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return content_bytes.decode("latin-1"), "latin-1"


def _select_lines(
    content: str,
    request: SourceReadRequest,
    path: str,
) -> tuple[str, int, int]:
    if content == "":
        if request.start_line not in {None, 1} or request.end_line not in {None, 1}:
            raise RepositoryError(f"line range is outside empty file: {path}")
        return "", 1, 1

    lines = content.splitlines(keepends=True)
    start_line = request.start_line or 1
    end_line = request.end_line or len(lines)
    if start_line > len(lines) or end_line > len(lines):
        raise RepositoryError(f"line range is outside file: {path}")
    return "".join(lines[start_line - 1 : end_line]), start_line, end_line


def _effective_byte_limit(
    read_mode: str,
    requested_max_bytes: int | None,
) -> int | None:
    if read_mode == "bounded":
        if requested_max_bytes is None:
            return BOUNDED_READ_MAX_BYTES
        return min(requested_max_bytes, BOUNDED_READ_MAX_BYTES)
    return requested_max_bytes


def _truncate_content(
    content: str,
    encoding: str,
    limit: int | None,
) -> tuple[str, bool]:
    if limit is None:
        return content, False
    encoded = content.encode(encoding)
    if len(encoded) <= limit:
        return content, False
    truncated = encoded[:limit]
    while True:
        try:
            return truncated.decode(encoding), True
        except UnicodeDecodeError:
            truncated = truncated[:-1]
