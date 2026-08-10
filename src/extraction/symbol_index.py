"""Conversion of private Graphify declarations into Bridger's SymbolIndex."""

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from models.files import FileIndex
from models.repository import RepositoryContext
from models.symbols import SymbolIndex, SymbolRecord, summarize_symbols

SYMBOL_INDEX_SCHEMA_VERSION = "1"


def build_symbol_index(
    context: RepositoryContext,
    file_index: FileIndex,
    graphify_symbols: list[dict[str, Any]],
) -> SymbolIndex:
    """Build a stable, validated declaration index from Graphify emissions."""
    if context.repository_id != file_index.repository_id:
        raise ValueError("RepositoryContext and FileIndex repository_id differ")
    if context.revision != file_index.revision:
        raise ValueError("RepositoryContext and FileIndex revision differ")
    if context.scope_path != file_index.scope_path:
        raise ValueError("RepositoryContext and FileIndex scope_path differ")

    eligible_files = {
        record.path: record
        for record in file_index.files
        if record.disposition.processing_mode == "extract"
        and record.disposition.read_mode == "full"
    }
    line_counts: dict[str, int] = {}
    prepared: list[dict[str, Any]] = []
    for private_symbol in graphify_symbols:
        relative_path = _repository_relative_path(
            private_symbol.get("source_file"), context.root_path
        )
        if relative_path not in eligible_files:
            raise ValueError(
                "Graphify emitted a symbol outside the eligible FileIndex: "
                f"{relative_path}"
            )
        start_line = _positive_line(private_symbol.get("start_line"), "start_line")
        end_line = _positive_line(private_symbol.get("end_line"), "end_line")
        if end_line < start_line:
            raise ValueError(f"invalid declaration range for {relative_path}")
        line_count = line_counts.get(relative_path)
        if line_count is None:
            line_count = _line_count(context.root_path / relative_path)
            line_counts[relative_path] = line_count
        if end_line > line_count:
            raise ValueError(
                f"declaration range exceeds {relative_path}: {end_line} > {line_count}"
            )
        name = _required_text(private_symbol.get("name"), "name")
        qualified_name = _optional_text(private_symbol.get("qualified_name"))
        prepared.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "kind": _required_text(private_symbol.get("kind"), "kind"),
                "path": relative_path,
                "start_line": start_line,
                "end_line": end_line,
                "parent_qualified_name": _optional_text(
                    private_symbol.get("parent_qualified_name")
                ),
                "signature": _optional_text(private_symbol.get("signature")),
                "language": _optional_text(private_symbol.get("language")),
            }
        )

    identity_counts = Counter(_identity_base(symbol) for symbol in prepared)
    symbol_ids = [
        _symbol_id(
            symbol,
            include_position=identity_counts[_identity_base(symbol)] > 1,
        )
        for symbol in prepared
    ]
    local_parent_candidates: dict[tuple[str, str], list[str]] = defaultdict(list)
    global_parent_candidates: dict[str, list[str]] = defaultdict(list)
    for symbol, symbol_id in zip(prepared, symbol_ids, strict=True):
        qualified_name = symbol["qualified_name"]
        if qualified_name:
            local_parent_candidates[(symbol["path"], qualified_name)].append(symbol_id)
            global_parent_candidates[qualified_name].append(symbol_id)

    records: list[SymbolRecord] = []
    for symbol, symbol_id in zip(prepared, symbol_ids, strict=True):
        parent_symbol_id = None
        parent_name = symbol.pop("parent_qualified_name")
        if parent_name:
            matches = local_parent_candidates.get((symbol["path"], parent_name), [])
            if not matches:
                matches = global_parent_candidates.get(parent_name, [])
            if len(matches) == 1 and matches[0] != symbol_id:
                parent_symbol_id = matches[0]
        records.append(
            SymbolRecord(
                symbol_id=symbol_id,
                parent_symbol_id=parent_symbol_id,
                **symbol,
            )
        )
    records.sort(key=_record_sort_key)
    return SymbolIndex(
        schema_version=SYMBOL_INDEX_SCHEMA_VERSION,
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        symbols=records,
        summary=summarize_symbols(records),
    )


def _repository_relative_path(value: object, root_path: Path) -> str:
    source = _required_text(value, "source_file")
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved_root = root_path.resolve()
    resolved_path = candidate.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ValueError(
            f"symbol source path escapes the repository: {source}"
        ) from error


def _line_count(path: Path) -> int:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot validate symbol ranges for {path}") from error
    return max(1, len(content.splitlines()))


def _positive_line(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Graphify symbol {field_name} must be a positive integer")
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Graphify symbol {field_name} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional Graphify symbol fields must be text")
    normalized = value.strip()
    return normalized or None


def _identity_base(symbol: dict[str, Any]) -> tuple[str, ...]:
    discriminator = symbol["signature"] or (
        f"{symbol['start_line']}:{symbol['end_line']}"
    )
    return (
        symbol["path"],
        symbol["kind"],
        symbol["qualified_name"] or symbol["name"],
        discriminator,
    )


def _symbol_id(symbol: dict[str, Any], *, include_position: bool) -> str:
    parts = list(_identity_base(symbol))
    if include_position:
        parts.append(f"{symbol['start_line']}:{symbol['end_line']}")
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"symbol_{digest[:24]}"


def _record_sort_key(symbol: SymbolRecord) -> tuple[object, ...]:
    return (
        symbol.path,
        symbol.start_line,
        symbol.end_line,
        symbol.kind,
        symbol.qualified_name or "",
        symbol.name,
        symbol.symbol_id,
    )
