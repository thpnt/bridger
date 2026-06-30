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


class SymbolRecord(ArtifactModel):
    id: str
    path: RepositoryPath
    name: str
    kind: SymbolKind
    line_start: Annotated[int, Field(ge=1)]
    line_end: Annotated[int, Field(ge=1)]
    declaration: str
    parent: str | None = None
    decorators: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)
    is_exported: bool | None = None
    extractor: str

    _validate_path = field_validator("path")(validate_repository_path)

    @model_validator(mode="after")
    def validate_line_range(self) -> "SymbolRecord":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class SymbolParseError(ArtifactModel):
    path: RepositoryPath
    extractor: str
    error: str

    _validate_path = field_validator("path")(validate_repository_path)


class SymbolIndexArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    symbols: list[SymbolRecord]
    parse_errors: list[SymbolParseError]
