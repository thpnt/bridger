from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

RepositoryPath = Annotated[str, StringConstraints(min_length=1)]


def validate_repository_path(path: str) -> str:
    parsed_path = PurePosixPath(path)
    if parsed_path.is_absolute() or ".." in parsed_path.parts:
        raise ValueError("path must stay within the repository")
    if "\\" in path or path != parsed_path.as_posix():
        raise ValueError("path must be a repository-relative POSIX path")
    return path


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkipReason(StrEnum):
    IGNORED_DIRECTORY = "ignored_directory"
    IGNORED_FILE = "ignored_file"
    SENSITIVE_FILE = "sensitive_file"
    BINARY_FILE = "binary_file"
    LARGE_FILE = "large_file"
    OUTSIDE_REPO = "outside_repo"
    SYMLINK_UNSUPPORTED = "symlink_unsupported"
    READ_ERROR = "read_error"


class IndexedFile(ArtifactModel):
    path: RepositoryPath
    extension: str
    size_bytes: Annotated[int, Field(ge=0)]
    line_count: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    is_binary: bool
    is_symlink: bool
    detected_encoding: str

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


class FileIndexArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    repo_root_name: str
    files: list[IndexedFile]
    skipped_files: list[SkippedFile]
    stats: FileIndexStats
