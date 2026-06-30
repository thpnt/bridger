from dataclasses import dataclass
from typing import Protocol

from bridger.models.symbol_index import SymbolRecord


@dataclass(frozen=True)
class ExtractionResult:
    symbols: list[SymbolRecord]
    has_parse_error: bool = False


class SymbolExtractor(Protocol):
    extensions: frozenset[str]
    extractor_name: str

    def extract(self, path: str, source: bytes) -> ExtractionResult: ...
