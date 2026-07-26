from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from bridger.models.repository_path import RepositoryPath, validate_repository_path


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkipReason(StrEnum):
    BRIDGER_DIRECTORY = "bridger_directory"
    IGNORED_DIRECTORY = "ignored_directory"
    IGNORED_FILE = "ignored_file"
    GITIGNORED = "gitignored"
    SENSITIVE_FILE = "sensitive_file"
    BINARY_FILE = "binary_file"
    LARGE_FILE = "large_file"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    OUTSIDE_REPO = "outside_repo"
    SYMLINK_UNSUPPORTED = "symlink_unsupported"
    READ_ERROR = "read_error"


class ContentType(StrEnum):
    TEXT = "text"
    BINARY = "binary"
    SYMLINK = "symlink"
    UNKNOWN = "unknown"


class ReadPolicy(StrEnum):
    READABLE = "readable"
    METADATA_ONLY = "metadata_only"


class IndexedFile(ArtifactModel):
    path: RepositoryPath
    extension: str
    size_bytes: Annotated[int, Field(ge=0)]
    line_count: Annotated[int, Field(ge=0)]
    sha256: Annotated[str | None, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = None
    is_binary: bool
    is_symlink: bool
    detected_encoding: str
    content_type: ContentType = ContentType.TEXT
    read_policy: ReadPolicy = ReadPolicy.READABLE
    read_policy_reason: SkipReason | None = None

    _validate_path = field_validator("path")(validate_repository_path)


class SkippedFile(ArtifactModel):
    path: RepositoryPath
    skip_reason: SkipReason

    _validate_path = field_validator("path")(validate_repository_path)


class FileIndexStats(ArtifactModel):
    files_seen: Annotated[int, Field(ge=0)]
    files_included: Annotated[int, Field(ge=0)]
    files_skipped: Annotated[int, Field(ge=0)]
    total_included_bytes: Annotated[int, Field(ge=0)]
    files_tracked: Annotated[int, Field(ge=0)] = 0
    files_readable: Annotated[int, Field(ge=0)] = 0
    files_metadata_only: Annotated[int, Field(ge=0)] = 0
    files_excluded: Annotated[int, Field(ge=0)] = 0
    untracked_files_excluded: Annotated[int, Field(ge=0)] = 0


class FileIndexDiagnostic(ArtifactModel):
    code: str
    message: str
    path: RepositoryPath | None = None

    @field_validator("path")
    @classmethod
    def validate_optional_path(cls, path: str | None) -> str | None:
        return validate_repository_path(path) if path is not None else None


class FileIndexArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    repo_root_name: str
    revision: str = "unknown"
    files: list[IndexedFile]
    skipped_files: list[SkippedFile]
    stats: FileIndexStats
    diagnostics: list[FileIndexDiagnostic] = Field(default_factory=list)
