from pathlib import PurePosixPath

from bridger.deterministic.symbols.base import SymbolExtractor
from bridger.deterministic.symbols.extractors import (
    GoExtractor,
    PhpExtractor,
    PythonExtractor,
    create_javascript_extractor,
    create_tsx_extractor,
    create_typescript_extractor,
)


def build_extractor_registry() -> dict[str, SymbolExtractor]:
    extractors: tuple[SymbolExtractor, ...] = (
        PythonExtractor(),
        create_typescript_extractor(),
        create_tsx_extractor(),
        create_javascript_extractor(),
        GoExtractor(),
        PhpExtractor(),
    )
    return {
        extension: extractor
        for extractor in extractors
        for extension in extractor.extensions
    }


def extractor_for_path(
    path: str, registry: dict[str, SymbolExtractor]
) -> SymbolExtractor | None:
    return registry.get(PurePosixPath(path).suffix.lower())
