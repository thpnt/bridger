from importlib import metadata
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


class TreeSitterCompatibilityError(RuntimeError):
    pass


def _validate_tree_sitter_version() -> None:
    installed_version = metadata.version("tree-sitter")
    if installed_version.startswith("0.25."):
        return
    raise TreeSitterCompatibilityError(
        f"Tree-sitter {installed_version} is incompatible with Bridger's "
        "language bindings."
    )


def build_extractor_registry() -> dict[str, SymbolExtractor]:
    _validate_tree_sitter_version()
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
