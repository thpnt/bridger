from datetime import UTC, datetime
from pathlib import Path

from bridger.deterministic.symbols.registry import (
    build_extractor_registry,
    extractor_for_path,
)
from bridger.models.file_index import FileIndexArtifact
from bridger.models.symbol_index import (
    SymbolIndexArtifact,
    SymbolParseError,
    SymbolRecord,
)


def _read_indexed_file(repo_root: Path, relative_path: str) -> bytes:
    current_path = repo_root
    for part in Path(relative_path).parts:
        current_path /= part
        if current_path.is_symlink():
            raise OSError("indexed path is no longer a safe repository file")
    resolved_path = current_path.resolve(strict=True)
    if not resolved_path.is_relative_to(repo_root):
        raise OSError("indexed path is no longer a safe repository file")
    return resolved_path.read_bytes()


def _deduplicate_symbols(symbols: list[SymbolRecord]) -> list[SymbolRecord]:
    unique: dict[tuple[object, ...], SymbolRecord] = {}
    for symbol in symbols:
        key = (
            symbol.path,
            symbol.line_start,
            symbol.line_end,
            symbol.kind,
            symbol.name,
            symbol.parent,
            symbol.declaration,
        )
        unique.setdefault(key, symbol)
    return list(unique.values())


def build_symbol_index_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> SymbolIndexArtifact:
    root = repo_root.resolve()
    file_index_path = root / ".bridger" / "artifacts" / "file-index.json"
    file_index = FileIndexArtifact.model_validate_json(file_index_path.read_bytes())
    registry = build_extractor_registry()
    symbols: list[SymbolRecord] = []
    parse_errors: list[SymbolParseError] = []
    processed_paths: set[str] = set()

    for indexed_file in file_index.files:
        if indexed_file.path in processed_paths:
            continue
        processed_paths.add(indexed_file.path)
        extractor = extractor_for_path(indexed_file.path, registry)
        if extractor is None:
            continue
        try:
            source = _read_indexed_file(root, indexed_file.path)
            result = extractor.extract(indexed_file.path, source)
            symbols.extend(result.symbols)
            if result.has_parse_error:
                parse_errors.append(
                    SymbolParseError(
                        path=indexed_file.path,
                        extractor=extractor.extractor_name,
                        error="parse_error",
                    )
                )
        except OSError:
            parse_errors.append(
                SymbolParseError(
                    path=indexed_file.path,
                    extractor=extractor.extractor_name,
                    error="read_error",
                )
            )
        except Exception:
            parse_errors.append(
                SymbolParseError(
                    path=indexed_file.path,
                    extractor=extractor.extractor_name,
                    error="extractor_error",
                )
            )

    sorted_symbols = sorted(
        _deduplicate_symbols(symbols),
        key=lambda symbol: (
            symbol.path,
            symbol.line_start,
            symbol.line_end,
            symbol.kind,
            symbol.name,
            symbol.id,
        ),
    )
    return SymbolIndexArtifact(
        generated_at=generated_at or datetime.now(UTC),
        symbols=sorted_symbols,
        parse_errors=sorted(
            parse_errors,
            key=lambda error: (error.path, error.extractor, error.error),
        ),
    )
