"""Deterministic source-symbol contracts owned by Bridger."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SymbolKind = Literal[
    "class",
    "interface",
    "struct",
    "enum",
    "function",
    "method",
    "constructor",
    "property",
    "field",
    "type",
    "module",
    "namespace",
    "table",
    "view",
    "procedure",
    "trigger",
    "enum_member",
    "variable",
]


class SymbolRecord(BaseModel):
    """One source-backed declaration at an exact repository-relative range."""

    model_config = ConfigDict(extra="forbid")

    symbol_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    qualified_name: str | None = Field(default=None, min_length=1)
    kind: SymbolKind
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    parent_symbol_id: str | None = Field(default=None, min_length=1)
    signature: str | None = Field(default=None, min_length=1, max_length=500)
    language: str | None = Field(default=None, min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Require a normalized repository-relative source path."""
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

    @model_validator(mode="after")
    def validate_range(self) -> "SymbolRecord":
        """Reject inverted declaration ranges."""
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        if self.parent_symbol_id == self.symbol_id:
            raise ValueError("a symbol cannot be its own parent")
        return self


class SymbolIndexSummary(BaseModel):
    """Small derived summary of one SymbolIndex."""

    model_config = ConfigDict(extra="forbid")

    total_symbols: int = Field(ge=0)
    files_with_symbols: int = Field(ge=0)
    symbols_by_kind: dict[SymbolKind, int] = Field(default_factory=dict)


class SymbolIndex(BaseModel):
    """Canonical declaration index for one exact repository revision."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    scope_path: str = "."
    symbols: list[SymbolRecord] = Field(default_factory=list)
    summary: SymbolIndexSummary

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
    def validate_consistency(self) -> "SymbolIndex":
        """Keep symbols ordered, unique, and consistent with their summary."""
        sort_keys = [_symbol_sort_key(symbol) for symbol in self.symbols]
        if sort_keys != sorted(sort_keys):
            raise ValueError("SymbolIndex symbols must be deterministically ordered")
        symbol_ids = [symbol.symbol_id for symbol in self.symbols]
        if len(symbol_ids) != len(set(symbol_ids)):
            raise ValueError("SymbolIndex symbol_id values must be unique")
        known_ids = set(symbol_ids)
        if any(
            symbol.parent_symbol_id not in known_ids
            for symbol in self.symbols
            if symbol.parent_symbol_id is not None
        ):
            raise ValueError("parent_symbol_id must reference a symbol in the index")
        if self.summary != summarize_symbols(self.symbols):
            raise ValueError("SymbolIndex summary does not match its symbols")
        return self


def summarize_symbols(symbols: list[SymbolRecord]) -> SymbolIndexSummary:
    """Compute the required SymbolIndex summary from canonical records."""
    kind_counts = Counter(symbol.kind for symbol in symbols)
    return SymbolIndexSummary(
        total_symbols=len(symbols),
        files_with_symbols=len({symbol.path for symbol in symbols}),
        symbols_by_kind={kind: kind_counts[kind] for kind in sorted(kind_counts)},
    )


def _symbol_sort_key(symbol: SymbolRecord) -> tuple[object, ...]:
    return (
        symbol.path,
        symbol.start_line,
        symbol.end_line,
        symbol.kind,
        symbol.qualified_name or "",
        symbol.name,
        symbol.symbol_id,
    )
