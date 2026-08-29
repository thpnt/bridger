"""File inventory and controlled-source-read contracts."""

from collections import Counter
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

BOUNDED_READ_MAX_BYTES = 64 * 1024

ReadMode = Literal["full", "bounded", "denied"]
ProcessingMode = Literal["extract", "metadata_only", "skip"]
ContentType = Literal["source", "documentation", "configuration", "binary", "unknown"]


def _validate_file_index_path(value: str) -> str:
    if (
        value.startswith("/")
        or value in {"", "."}
        or value.startswith("./")
        or value.endswith("/")
        or "/./" in value
        or "//" in value
        or ".." in value.split("/")
    ):
        raise ValueError("path must be a normalized repository-relative path")
    return value


FileIndexPath = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_validate_file_index_path),
]


class FileDisposition(BaseModel):
    """Defines permitted reads and downstream processing for one tracked file."""

    model_config = ConfigDict(extra="forbid")

    read_mode: ReadMode
    processing_mode: ProcessingMode
    reason: str | None = Field(default=None, min_length=1)


class FileRecord(BaseModel):
    """Metadata and policy for one Git-tracked file in a FileIndex."""

    model_config = ConfigDict(extra="forbid")

    path: FileIndexPath
    git_object_id: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    size_bytes: int = Field(ge=0)
    content_type: ContentType
    language: str | None = Field(default=None, min_length=1)
    disposition: FileDisposition


class FileIndexSummary(BaseModel):
    """Derived counts for one canonical FileIndex."""

    model_config = ConfigDict(extra="forbid")

    total_tracked: int = Field(ge=0)
    extractable: int = Field(ge=0)
    metadata_only: int = Field(ge=0)
    skipped: int = Field(ge=0)
    fully_readable: int = Field(ge=0)
    bounded_readable: int = Field(ge=0)
    read_denied: int = Field(ge=0)


class FileIndex(BaseModel):
    """Canonical, complete Git-tracked inventory for one repository revision."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    scope_path: str = "."
    files: list[FileRecord] = Field(default_factory=list)
    summary: FileIndexSummary

    @field_validator("scope_path")
    @classmethod
    def validate_scope_path(cls, value: str) -> str:
        """Require a normalized repository-relative analysis root."""
        if (
            not value
            or value.startswith("/")
            or (
                value != "."
                and (
                    value.startswith("./")
                    or value.endswith("/")
                    or "/./" in value
                    or "//" in value
                    or ".." in value.split("/")
                )
            )
        ):
            raise ValueError("scope_path must be a normalized repository-relative path")
        return value

    @model_validator(mode="after")
    def validate_consistency(self) -> "FileIndex":
        """Keep canonical records ordered, unique, and consistent with their summary."""
        paths = [file.path for file in self.files]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("FileIndex files must have unique, sorted paths")
        if self.summary != summarize_files(self.files):
            raise ValueError("FileIndex summary does not match its files")
        return self


class IntakeConfiguration(BaseModel):
    """Small, deterministic policy configuration for Layer 1 file intake."""

    model_config = ConfigDict(extra="forbid")

    max_full_read_bytes: int = Field(default=1024 * 1024, ge=1)
    sensitive_path_patterns: tuple[str, ...] = (
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "*/id_rsa",
        "*credentials*",
    )
    generated_path_patterns: tuple[str, ...] = ()
    excluded_path_patterns: tuple[str, ...] = ()


class SourceReadRequest(BaseModel):
    """Requests a policy-compliant read of one indexed source file."""

    model_config = ConfigDict(extra="forbid")

    path: FileIndexPath
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    max_bytes: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "SourceReadRequest":
        """Reject an inverted explicitly requested line range."""
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must not be before start_line")
        return self


class SourceReadResult(BaseModel):
    """Revision-bound content returned by the Layer 1 source-read interface."""

    model_config = ConfigDict(extra="forbid")

    path: FileIndexPath
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    content: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    encoding: str = Field(min_length=1)
    truncated: bool


class FileChangeSet(BaseModel):
    """Ordered file-level changes between two exact Git revisions."""

    model_config = ConfigDict(extra="forbid")

    base_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    target_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    added_paths: list[str] = Field(default_factory=list)
    modified_paths: list[str] = Field(default_factory=list)
    deleted_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_paths(self) -> "FileChangeSet":
        """Require deterministic, mutually exclusive path classifications."""
        groups = [self.added_paths, self.modified_paths, self.deleted_paths]
        all_paths = [path for group in groups for path in group]
        if any(group != sorted(group) for group in groups):
            raise ValueError("FileChangeSet paths must be sorted")
        if len(all_paths) != len(set(all_paths)):
            raise ValueError("FileChangeSet path classifications must be exclusive")
        return self


def summarize_files(files: list[FileRecord]) -> FileIndexSummary:
    """Compute the required FileIndex summary directly from canonical records."""
    processing_modes = Counter(file.disposition.processing_mode for file in files)
    read_modes = Counter(file.disposition.read_mode for file in files)
    return FileIndexSummary(
        total_tracked=len(files),
        extractable=processing_modes["extract"],
        metadata_only=processing_modes["metadata_only"],
        skipped=processing_modes["skip"],
        fully_readable=read_modes["full"],
        bounded_readable=read_modes["bounded"],
        read_denied=read_modes["denied"],
    )
