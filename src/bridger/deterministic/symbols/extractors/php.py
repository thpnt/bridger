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
    extractor_name = "tree_sitter_php"

    def __init__(self) -> None:
        self._adapter = TreeSitterAdapter(Language(tree_sitter_php.language_php()))

    def extract(self, path: str, source: bytes) -> ExtractionResult:
        tree = self._adapter.parse(source)
        symbols = [
            symbol
            for _, captures in self._adapter.matches(tree, QUERY)
            if (symbol := self._symbol(path, source, captures["declaration"][0]))
            is not None
        ]
        return ExtractionResult(
            symbols=symbols, has_parse_error=tree.root_node.has_error
        )

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
        parent_node = self._adapter.ancestor(node, PARENT_TYPES)
        declaration = self._adapter.text(source, node)
        return self._adapter.record(
            path=path,
            source=source,
            node=node,
            name=name,
            kind=kinds[node.type],
            parent=(
                named_child_text(source, parent_node, "name")
                if parent_node is not None
                else None
            ),
            modifiers=[
                modifier
                for modifier in MODIFIERS
                if re.search(rf"\b{modifier}\b", declaration)
            ],
            extractor=self.extractor_name,
        )
