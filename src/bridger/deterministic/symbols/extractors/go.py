import tree_sitter_go
from tree_sitter import Language, Node

from bridger.deterministic.symbols.base import ExtractionResult
from bridger.deterministic.symbols.tree_sitter_adapter import (
    TreeSitterAdapter,
    named_child_text,
)
from bridger.models.symbol_index import SymbolKind, SymbolRecord

QUERY = """
(function_declaration) @declaration
(method_declaration) @declaration
(type_spec) @declaration
(type_alias) @declaration
(var_spec) @declaration
(const_spec) @declaration
"""


class GoExtractor:
    extensions = frozenset({".go"})
    extractor_name = "tree_sitter_go"

    def __init__(self) -> None:
        self._adapter = TreeSitterAdapter(Language(tree_sitter_go.language()))

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
        if node.type in {"var_spec", "const_spec"} and self._adapter.ancestor(
            node, {"function_declaration", "method_declaration"}
        ):
            return None
        name = named_child_text(source, node, "name")
        if name is None:
            return None
        kind = self._kind(node)
        parent = (
            self._receiver_type(source, node) if kind == SymbolKind.METHOD else None
        )
        declaration_node = (
            node.parent
            if node.type in {"type_spec", "type_alias", "var_spec", "const_spec"}
            and node.parent is not None
            else node
        )
        return self._adapter.record(
            path=path,
            source=source,
            node=declaration_node,
            name=name,
            kind=kind,
            parent=parent,
            is_exported=name[:1].isupper(),
            extractor=self.extractor_name,
        )

    def _kind(self, node: Node) -> SymbolKind:
        if node.type == "function_declaration":
            return SymbolKind.FUNCTION
        if node.type == "method_declaration":
            return SymbolKind.METHOD
        if node.type == "var_spec":
            return SymbolKind.VARIABLE
        if node.type == "const_spec":
            return SymbolKind.CONSTANT
        if node.type == "type_alias":
            return SymbolKind.TYPE_ALIAS
        type_node = node.child_by_field_name("type")
        if type_node is not None and type_node.type == "struct_type":
            return SymbolKind.STRUCT
        if type_node is not None and type_node.type == "interface_type":
            return SymbolKind.INTERFACE
        return SymbolKind.TYPE

    def _receiver_type(self, source: bytes, node: Node) -> str | None:
        receiver = node.child_by_field_name("receiver")
        if receiver is None:
            return None
        for descendant in self._adapter.walk(receiver):
            if descendant.type == "type_identifier":
                return self._adapter.text(source, descendant)
        return None
