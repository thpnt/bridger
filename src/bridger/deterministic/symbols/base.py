from dataclasses import dataclass
from typing import Protocol

from bridger.models.symbol_index import (
    FileExtractionStatus,
    SymbolExtractionError,
    SymbolRecord,
)


@dataclass(frozen=True)
class ExtractionResult:
    symbols: list[SymbolRecord]
    status: FileExtractionStatus = FileExtractionStatus.SUCCESS
    errors: list[SymbolExtractionError] | None = None


class SymbolExtractor(Protocol):
    extensions: frozenset[str]
    language: str
    extractor_name: str

    def extract(self, path: str, source: bytes) -> ExtractionResult: ...
