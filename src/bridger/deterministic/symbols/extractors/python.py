import tree_sitter_python
from tree_sitter import Language, Node

from bridger.deterministic.symbols.base import ExtractionResult
from bridger.deterministic.symbols.tree_sitter_adapter import (
    TreeSitterAdapter,
    named_child_text,
)
from bridger.models.symbol_index import SymbolKind, SymbolRecord

QUERY = """
(function_definition) @declaration
(class_definition) @declaration
(assignment) @assignment
"""


class PythonExtractor:
    extensions = frozenset({".py"})
    language = "python"
    extractor_name = "tree_sitter_python"

    def __init__(self) -> None:
        self._adapter = TreeSitterAdapter(
            Language(tree_sitter_python.language()),
            self.language,
            self.extractor_name,
        )

    def extract(self, path: str, source: bytes) -> ExtractionResult:
        tree = self._adapter.parse(source)
        symbols: list[SymbolRecord] = []
        for _, captures in self._adapter.matches(tree, QUERY):
            declaration = captures.get("declaration", [None])[0]
            assignment = captures.get("assignment", [None])[0]
            if declaration is not None:
                symbol = self._declaration(path, source, declaration)
            elif assignment is not None:
                symbol = self._assignment(path, source, assignment)
            else:
                symbol = None
            if symbol is not None:
                symbols.append(symbol)
        return self._adapter.extraction_result(tree, symbols)

    def _declaration(self, path: str, source: bytes, node: Node) -> SymbolRecord | None:
        name = named_child_text(source, node, "name")
        if name is None:
            return None
        scope_names = self._adapter.enclosing_scope_names(
            source, node, {"class_definition", "function_definition"}
        )
        parent_class = self._adapter.ancestor(node, {"class_definition"})
        kind = (
            SymbolKind.CLASS
            if node.type == "class_definition"
            else SymbolKind.METHOD
            if parent_class is not None
            else SymbolKind.FUNCTION
        )
        return self._adapter.record(
            path=path,
            source=source,
            node=node,
            name=name,
            kind=kind,
            parent_scope_names=scope_names,
            decorators=self._decorators(source, node),
            extractor=self.extractor_name,
        )

    def _decorators(self, source: bytes, node: Node) -> list[str]:
        wrapper = node.parent
        if wrapper is None or wrapper.type != "decorated_definition":
            return []
        decorators: list[str] = []
        for index in range(wrapper.named_child_count):
            child = wrapper.named_child(index)
            if child is None or child.type != "decorator":
                continue
            text = self._adapter.text(source, child).lstrip("@").strip()
            decorators.append(text.split("(", 1)[0])
        return decorators

    def _assignment(self, path: str, source: bytes, node: Node) -> SymbolRecord | None:
        if self._adapter.ancestor(node, {"function_definition", "class_definition"}):
            return None
        name_node = node.child_by_field_name("left")
        if name_node is None or name_node.type != "identifier":
            return None
        name = self._adapter.text(source, name_node)
        kind = SymbolKind.CONSTANT if name.isupper() else SymbolKind.VARIABLE
        return self._adapter.record(
            path=path,
            source=source,
            node=node,
            name=name,
            kind=kind,
            extractor=self.extractor_name,
        )
