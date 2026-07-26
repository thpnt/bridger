from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)


class SymbolKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE = "type"
    TYPE_ALIAS = "type_alias"
    STRUCT = "struct"
    ENUM = "enum"
    TRAIT = "trait"
    NAMESPACE = "namespace"
    MODULE = "module"


class SymbolExtractionStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class FileExtractionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    PARSE_ERROR = "parse_error"
    READ_ERROR = "read_error"
    EXTRACTOR_ERROR = "extractor_error"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"


class SourceRange(ArtifactModel):
    """A source range with 1-based lines and 0-based, end-exclusive columns."""

    start_line: Annotated[int, Field(ge=1)]
    start_column: Annotated[int, Field(ge=0)]
    end_line: Annotated[int, Field(ge=1)]
    end_column: Annotated[int, Field(ge=0)]
    start_byte: Annotated[int | None, Field(ge=0)] = None
    end_byte: Annotated[int | None, Field(ge=0)] = None

    @model_validator(mode="after")
    def validate_order(self) -> "SourceRange":
        if (self.end_line, self.end_column) <= (self.start_line, self.start_column):
            raise ValueError("source range end must be after its start")
        if self.start_byte is not None and self.end_byte is not None:
            if self.end_byte <= self.start_byte:
                raise ValueError("source range end_byte must be after start_byte")
        return self


class SymbolExtractionError(ArtifactModel):
    code: str
    message: str
    line: Annotated[int | None, Field(ge=1)] = None
    column: Annotated[int | None, Field(ge=0)] = None
    extractor: str | None = None


class SymbolFileExtraction(ArtifactModel):
    path: RepositoryPath
    language: str | None = None
    status: FileExtractionStatus
    symbol_count: Annotated[int, Field(ge=0)]
    errors: list[SymbolExtractionError] = Field(default_factory=list)

    _validate_path = field_validator("path")(validate_repository_path)


class SymbolRecord(ArtifactModel):
    id: str
    path: RepositoryPath
    language: str

    name: str
    qualified_name: str
    kind: SymbolKind

    parent_id: str | None = None
    parent_name: str | None = None

    declaration_range: SourceRange
    body_range: SourceRange | None = None
    body_available: bool

    declaration_preview: str
    signature: str

    decorators: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)
    exported: bool | None = None

    extraction_status: SymbolExtractionStatus = SymbolExtractionStatus.COMPLETE
    extractor: str

    _validate_path = field_validator("path")(validate_repository_path)

    @model_validator(mode="after")
    def validate_body(self) -> "SymbolRecord":
        if self.body_available != (self.body_range is not None):
            raise ValueError("body_available must agree with body_range")
        if self.body_range is not None:
            declaration_start = (
                self.declaration_range.start_line,
                self.declaration_range.start_column,
            )
            declaration_end = (
                self.declaration_range.end_line,
                self.declaration_range.end_column,
            )
            body_start = (self.body_range.start_line, self.body_range.start_column)
            body_end = (self.body_range.end_line, self.body_range.end_column)
            if not (declaration_start <= body_start and body_end <= declaration_end):
                raise ValueError("body_range must be contained in declaration_range")
            if (
                self.declaration_range.start_byte is not None
                and self.declaration_range.end_byte is not None
                and self.body_range.start_byte is not None
                and self.body_range.end_byte is not None
                and not (
                    self.declaration_range.start_byte
                    <= self.body_range.start_byte
                    <= self.body_range.end_byte
                    <= self.declaration_range.end_byte
                )
            ):
                raise ValueError(
                    "body byte range must be contained in declaration range"
                )
        return self

    @property
    def line_start(self) -> int:
        return self.declaration_range.start_line

    @property
    def line_end(self) -> int:
        return self.declaration_range.end_line

    @property
    def declaration(self) -> str:
        return self.declaration_preview

    @property
    def parent(self) -> str | None:
        return self.parent_name

    @property
    def is_exported(self) -> bool | None:
        return self.exported


class SymbolIndexArtifact(ArtifactModel):
    schema_version: Literal[2] = 2
    generated_at: datetime
    symbols: list[SymbolRecord]
    files: list[SymbolFileExtraction]

    @model_validator(mode="after")
    def validate_integrity(self) -> "SymbolIndexArtifact":
        symbols_by_id: dict[str, SymbolRecord] = {}
        for symbol in self.symbols:
            if symbol.id in symbols_by_id:
                raise ValueError(f"duplicate symbol ID: {symbol.id}")
            symbols_by_id[symbol.id] = symbol

        for symbol in self.symbols:
            if symbol.parent_id is None:
                if symbol.parent_name is not None and "." in symbol.qualified_name:
                    raise ValueError(
                        f"parent ID is required for nested symbol: {symbol.id}"
                    )
                continue
            parent = symbols_by_id.get(symbol.parent_id)
            if parent is None:
                raise ValueError(f"parent symbol ID was not found: {symbol.parent_id}")
            if parent.path != symbol.path:
                raise ValueError("parent and child symbols must be in the same file")

        symbol_counts: dict[str, int] = {}
        for symbol in self.symbols:
            symbol_counts[symbol.path] = symbol_counts.get(symbol.path, 0) + 1
        file_paths: set[str] = set()
        for file_result in self.files:
            if file_result.path in file_paths:
                raise ValueError(
                    f"duplicate file extraction result: {file_result.path}"
                )
            file_paths.add(file_result.path)
            if symbol_counts.get(file_result.path, 0) != file_result.symbol_count:
                raise ValueError(
                    "symbol_count does not match emitted symbols for "
                    f"{file_result.path}"
                )
        missing_file_results = set(symbol_counts) - file_paths
        if missing_file_results:
            raise ValueError(
                "symbols are missing file extraction results: "
                + ", ".join(sorted(missing_file_results))
            )
        return self
