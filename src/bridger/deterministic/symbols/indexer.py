import hashlib
from datetime import UTC, datetime
from pathlib import Path

from bridger.deterministic.symbols.registry import (
    build_extractor_registry,
    extractor_for_path,
)
from bridger.models.file_index import FileIndexArtifact, ReadPolicy
from bridger.models.symbol_index import (
    FileExtractionStatus,
    SymbolExtractionError,
    SymbolFileExtraction,
    SymbolIndexArtifact,
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


def _source_order_key(symbol: SymbolRecord) -> tuple[object, ...]:
    source_range = symbol.declaration_range
    if source_range.start_byte is not None:
        position: tuple[object, ...] = (0, source_range.start_byte)
    else:
        position = (1, source_range.start_line, source_range.start_column)
    return (
        symbol.path,
        *position,
        symbol.kind.value,
        symbol.qualified_name,
        symbol.id,
    )


def _identity_key(symbol: SymbolRecord) -> tuple[str, ...]:
    return (
        symbol.language,
        symbol.path,
        symbol.qualified_name,
        symbol.kind.value,
        symbol.signature,
    )


def _symbol_id(symbol: SymbolRecord, discriminator: int) -> str:
    canonical = "\x1f".join(
        (
            "bridger-symbol-index/v2",
            symbol.language,
            symbol.path,
            symbol.qualified_name,
            symbol.kind.value,
            symbol.signature,
            str(discriminator),
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"sym2:{digest}"


def _finalize_symbols(symbols: list[SymbolRecord]) -> list[SymbolRecord]:
    ordered = sorted(symbols, key=_source_order_key)
    occurrence_by_key: dict[tuple[str, ...], int] = {}
    finalized: list[SymbolRecord] = []
    for symbol in ordered:
        identity_key = _identity_key(symbol)
        discriminator = occurrence_by_key.get(identity_key, 0)
        occurrence_by_key[identity_key] = discriminator + 1
        finalized.append(
            symbol.model_copy(
                update={"id": _symbol_id(symbol, discriminator), "parent_id": None}
            )
        )

    by_parent_name: dict[tuple[str, str], list[SymbolRecord]] = {}
    for symbol in finalized:
        by_parent_name.setdefault((symbol.path, symbol.qualified_name), []).append(
            symbol
        )

    resolved: list[SymbolRecord] = []
    for symbol in finalized:
        parent_id: str | None = None
        if symbol.parent_name is not None and "." in symbol.qualified_name:
            parent_qualified_name = symbol.qualified_name.rsplit(".", 1)[0]
            candidates = by_parent_name.get((symbol.path, parent_qualified_name), [])
            if candidates:
                parent_id = candidates[0].id
        resolved.append(symbol.model_copy(update={"parent_id": parent_id}))
    return resolved


def _diagnostic(
    code: str, message: str, extractor: str | None
) -> SymbolExtractionError:
    return SymbolExtractionError(code=code, message=message, extractor=extractor)


def build_symbol_index_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> SymbolIndexArtifact:
    root = repo_root.resolve()
    file_index_path = root / ".bridger" / "artifacts" / "file-index.json"
    file_index = FileIndexArtifact.model_validate_json(file_index_path.read_bytes())
    registry = build_extractor_registry()
    raw_symbols: list[SymbolRecord] = []
    file_results: list[SymbolFileExtraction] = []
    processed_paths: set[str] = set()

    for indexed_file in file_index.files:
        if indexed_file.path in processed_paths:
            continue
        processed_paths.add(indexed_file.path)
        extractor = extractor_for_path(indexed_file.path, registry)
        if indexed_file.read_policy is not ReadPolicy.READABLE:
            file_results.append(
                SymbolFileExtraction(
                    path=indexed_file.path,
                    language=getattr(extractor, "language", None),
                    status=FileExtractionStatus.SKIPPED,
                    symbol_count=0,
                )
            )
            continue
        if extractor is None:
            file_results.append(
                SymbolFileExtraction(
                    path=indexed_file.path,
                    status=FileExtractionStatus.UNSUPPORTED,
                    symbol_count=0,
                )
            )
            continue
        try:
            source = _read_indexed_file(root, indexed_file.path)
            result = extractor.extract(indexed_file.path, source)
            raw_symbols.extend(result.symbols)
            file_results.append(
                SymbolFileExtraction(
                    path=indexed_file.path,
                    language=extractor.language,
                    status=result.status,
                    symbol_count=len(result.symbols),
                    errors=result.errors or [],
                )
            )
        except OSError as error:
            file_results.append(
                SymbolFileExtraction(
                    path=indexed_file.path,
                    language=extractor.language,
                    status=FileExtractionStatus.READ_ERROR,
                    symbol_count=0,
                    errors=[
                        _diagnostic("read_error", str(error), extractor.extractor_name)
                    ],
                )
            )
        except Exception as error:
            file_results.append(
                SymbolFileExtraction(
                    path=indexed_file.path,
                    language=extractor.language,
                    status=FileExtractionStatus.EXTRACTOR_ERROR,
                    symbol_count=0,
                    errors=[
                        _diagnostic(
                            "extractor_error", str(error), extractor.extractor_name
                        )
                    ],
                )
            )

    for skipped_file in file_index.skipped_files:
        if skipped_file.path in processed_paths:
            continue
        processed_paths.add(skipped_file.path)
        file_results.append(
            SymbolFileExtraction(
                path=skipped_file.path,
                status=FileExtractionStatus.SKIPPED,
                symbol_count=0,
            )
        )

    finalized_symbols = _finalize_symbols(raw_symbols)
    return SymbolIndexArtifact(
        generated_at=generated_at or datetime.now(UTC),
        symbols=finalized_symbols,
        files=sorted(file_results, key=lambda result: result.path),
    )
