import re

import tree_sitter_php
from tree_sitter import Language, Node

from bridger.deterministic.symbols.base import ExtractionResult
from bridger.deterministic.symbols.tree_sitter_adapter import (
    TreeSitterAdapter,
    named_child_text,
)
from bridger.models.symbol_index import SymbolKind, SymbolRecord

QUERY = """
(namespace_definition) @declaration
(function_definition) @declaration
(class_declaration) @declaration
(interface_declaration) @declaration
(trait_declaration) @declaration
(enum_declaration) @declaration
(method_declaration) @declaration
"""

MODIFIERS = ("public", "protected", "private", "static", "abstract", "final")
PARENT_TYPES = {
    "class_declaration",
    "interface_declaration",
    "trait_declaration",
    "enum_declaration",
}


class PhpExtractor:
    extensions = frozenset({".php"})
    language = "php"
    extractor_name = "tree_sitter_php"

    def __init__(self) -> None:
        self._adapter = TreeSitterAdapter(
            Language(tree_sitter_php.language_php()), self.language, self.extractor_name
        )

    def extract(self, path: str, source: bytes) -> ExtractionResult:
        tree = self._adapter.parse(source)
        symbols = [
            symbol
            for _, captures in self._adapter.matches(tree, QUERY)
            if (symbol := self._symbol(path, source, captures["declaration"][0]))
            is not None
        ]
        return self._adapter.extraction_result(tree, symbols)

    def _symbol(self, path: str, source: bytes, node: Node) -> SymbolRecord | None:
        name = named_child_text(source, node, "name")
        if name is None:
            return None
        kinds = {
            "namespace_definition": SymbolKind.NAMESPACE,
            "function_definition": SymbolKind.FUNCTION,
            "class_declaration": SymbolKind.CLASS,
            "interface_declaration": SymbolKind.INTERFACE,
            "trait_declaration": SymbolKind.TRAIT,
            "enum_declaration": SymbolKind.ENUM,
            "method_declaration": SymbolKind.METHOD,
        }
        declaration = self._adapter.text(source, node)
        scope_names = self._adapter.enclosing_scope_names(
            source, node, PARENT_TYPES | {"namespace_definition"}
        )
        namespace_name = (
            self._namespace_before(source, node)
            if node.type != "namespace_definition"
            else None
        )
        if namespace_name is not None:
            scope_names = (namespace_name, *scope_names)
        return self._adapter.record(
            path=path,
            source=source,
            node=node,
            name=name,
            kind=kinds[node.type],
            parent_scope_names=scope_names,
            modifiers=[
                modifier
                for modifier in MODIFIERS
                if re.search(rf"\b{modifier}\b", declaration)
            ],
            extractor=self.extractor_name,
            include_body=node.type != "interface_declaration",
        )

    def _namespace_before(self, source: bytes, node: Node) -> str | None:
        root = node
        while root.parent is not None:
            root = root.parent
        names = [
            named_child_text(source, candidate, "name")
            for candidate in self._adapter.walk(root)
            if candidate.type == "namespace_definition"
            and candidate.start_byte <= node.start_byte
        ]
        return names[-1] if names else None
