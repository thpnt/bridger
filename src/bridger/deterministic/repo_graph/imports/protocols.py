from collections.abc import Sequence
from typing import Protocol

from bridger.deterministic.repo_graph.imports.models import (
    ImportExtractionResult,
    ImportLanguage,
    ImportRecord,
    ImportResolutionResult,
)
from bridger.deterministic.repo_graph.imports.safe_files import SafeFileIndex


class ImportResolver(Protocol):
    """Language resolver contract over files accepted by file-index.json.

    Implementations extract syntax and resolve local candidates only. External
    imports are ignored, local-looking misses are unresolved, and artifact
    writing or repository scanning is outside this interface.
    """

    supported_extensions: frozenset[str]
    language: ImportLanguage

    def extract_imports(
        self, source_path: str, content: str
    ) -> ImportExtractionResult: ...

    def resolve_imports(
        self,
        source_path: str,
        imports: Sequence[ImportRecord],
        safe_files: SafeFileIndex,
    ) -> ImportResolutionResult: ...
