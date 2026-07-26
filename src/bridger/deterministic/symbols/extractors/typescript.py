import tree_sitter_typescript
from tree_sitter import Language

from bridger.deterministic.symbols.extractors.ecmascript import EcmaScriptExtractor


def create_typescript_extractor() -> EcmaScriptExtractor:
    return EcmaScriptExtractor(
        language=Language(tree_sitter_typescript.language_typescript()),
        language_name="typescript",
        extensions=frozenset({".ts"}),
        extractor_name="tree_sitter_typescript",
        supports_types=True,
    )


def create_tsx_extractor() -> EcmaScriptExtractor:
    return EcmaScriptExtractor(
        language=Language(tree_sitter_typescript.language_tsx()),
        language_name="tsx",
        extensions=frozenset({".tsx"}),
        extractor_name="tree_sitter_typescript",
        supports_types=True,
    )
