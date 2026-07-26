import tree_sitter_javascript
from tree_sitter import Language

from bridger.deterministic.symbols.extractors.ecmascript import EcmaScriptExtractor


def create_javascript_extractor() -> EcmaScriptExtractor:
    return EcmaScriptExtractor(
        language=Language(tree_sitter_javascript.language()),
        language_name="javascript",
        extensions=frozenset({".js", ".jsx", ".mjs", ".cjs"}),
        extractor_name="tree_sitter_javascript",
        supports_types=False,
    )
