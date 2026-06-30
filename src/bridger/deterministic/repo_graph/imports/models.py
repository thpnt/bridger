from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ImportLanguage(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    TSX = "tsx"
    JSX = "jsx"


class ImportKind(StrEnum):
    IMPORT = "import"
    FROM_IMPORT = "from_import"
    EXPORT_FROM = "export_from"
    REQUIRE = "require"
    DYNAMIC_IMPORT = "dynamic_import"


class UnresolvedImportReason(StrEnum):
    NO_MATCHING_FILE = "no_matching_file"
    INVALID_LOCAL_SPECIFIER = "invalid_local_specifier"
    OUTSIDE_SAFE_FILE_INDEX = "outside_safe_file_index"


class IgnoredImportReason(StrEnum):
    EXTERNAL_PACKAGE = "external_package"
    STANDARD_LIBRARY = "standard_library"


class ImportRecord(ArtifactModel):
    """One syntactic import extracted from an accepted source file."""

    source_path: RepositoryPath
    import_text: NonEmptyString
    specifier: NonEmptyString
    language: ImportLanguage
    kind: ImportKind
    line_start: Annotated[int, Field(ge=1)]
    line_end: Annotated[int, Field(ge=1)]
    is_relative: bool | None = None

    _validate_source_path = field_validator("source_path")(validate_repository_path)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ImportRecord":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ResolvedImport(ArtifactModel):
    source_path: RepositoryPath
    target_path: RepositoryPath
    import_text: NonEmptyString
    specifier: NonEmptyString
    language: ImportLanguage
    resolver: NonEmptyString

    _validate_paths = field_validator("source_path", "target_path")(
        validate_repository_path
    )


class UnresolvedImport(ArtifactModel):
    """A local-looking import without a target in the safe file index."""

    source_path: RepositoryPath
    import_text: NonEmptyString
    specifier: NonEmptyString
    language: ImportLanguage
    reason: UnresolvedImportReason
    resolver: NonEmptyString

    _validate_source_path = field_validator("source_path")(validate_repository_path)


class IgnoredImport(ArtifactModel):
    """An import intentionally excluded from local resolution."""

    source_path: RepositoryPath
    import_text: NonEmptyString
    specifier: NonEmptyString
    language: ImportLanguage
    reason: IgnoredImportReason
    resolver: NonEmptyString

    _validate_source_path = field_validator("source_path")(validate_repository_path)


class ImportResolverError(ArtifactModel):
    """A per-import or per-file error that does not abort resolver processing."""

    source_path: RepositoryPath
    resolver: NonEmptyString
    error: NonEmptyString
    import_text: str | None = None
    specifier: str | None = None

    _validate_source_path = field_validator("source_path")(validate_repository_path)


class ImportExtractionResult(ArtifactModel):
    imports: list[ImportRecord] = Field(default_factory=list)
    errors: list[ImportResolverError] = Field(default_factory=list)

    @model_validator(mode="after")
    def sort_output(self) -> "ImportExtractionResult":
        self.imports.sort(
            key=lambda record: (
                record.source_path,
                record.line_start,
                record.line_end,
                record.kind.value,
                record.specifier,
                record.import_text,
            )
        )
        self.errors.sort(key=_error_sort_key)
        return self


class ImportResolutionResult(ArtifactModel):
    resolved: list[ResolvedImport] = Field(default_factory=list)
    unresolved: list[UnresolvedImport] = Field(default_factory=list)
    ignored: list[IgnoredImport] = Field(default_factory=list)
    errors: list[ImportResolverError] = Field(default_factory=list)

    @model_validator(mode="after")
    def sort_output(self) -> "ImportResolutionResult":
        self.resolved.sort(
            key=lambda item: (
                item.source_path,
                item.target_path,
                item.specifier,
                item.import_text,
                item.resolver,
            )
        )
        self.unresolved.sort(
            key=lambda item: (
                item.source_path,
                item.specifier,
                item.reason.value,
                item.import_text,
                item.resolver,
            )
        )
        self.ignored.sort(
            key=lambda item: (
                item.source_path,
                item.specifier,
                item.reason.value,
                item.import_text,
                item.resolver,
            )
        )
        self.errors.sort(key=_error_sort_key)
        return self


def _error_sort_key(error: ImportResolverError) -> tuple[str, ...]:
    return (
        error.source_path,
        error.resolver,
        error.specifier or "",
        error.import_text or "",
        error.error,
    )
