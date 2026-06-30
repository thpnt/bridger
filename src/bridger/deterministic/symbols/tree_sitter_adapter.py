import re
from collections.abc import Iterator

from tree_sitter import Language, Node, Parser, Query, QueryCursor, Tree

from bridger.models.symbol_index import SymbolKind, SymbolRecord

MAX_DECLARATION_LENGTH = 300
NESTED_BODY_TYPES = {
    "class_body",
    "compound_statement",
    "declaration_list",
    "enum_body",
    "enum_declaration_list",
    "field_declaration_list",
    "interface_body",
    "statement_block",
}


class TreeSitterAdapter:
    def __init__(self, language: Language) -> None:
        self._language = language
        self._parser = Parser(language)

    def parse(self, source: bytes) -> Tree:
        return self._parser.parse(source)

    def matches(
        self, tree: Tree, query_source: str
    ) -> list[tuple[int, dict[str, list[Node]]]]:
        query = Query(self._language, query_source)
        return QueryCursor(query).matches(tree.root_node)

    @staticmethod
    def walk(node: Node) -> Iterator[Node]:
        yield node
        for child_index in range(node.named_child_count):
            child = node.named_child(child_index)
            if child is not None:
                yield from TreeSitterAdapter.walk(child)

    @staticmethod
    def text(source: bytes, node: Node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def compact_declaration(source: bytes, node: Node) -> str:
        body_start = TreeSitterAdapter._body_start(node)
        end_byte = body_start if body_start is not None else node.end_byte
        declaration = source[node.start_byte : end_byte].decode(
            "utf-8", errors="replace"
        )
        declaration = re.sub(r"\s+", " ", declaration).strip().rstrip("{:").strip()
        if len(declaration) > MAX_DECLARATION_LENGTH:
            return declaration[: MAX_DECLARATION_LENGTH - 3].rstrip() + "..."
        return declaration

    @staticmethod
    def _body_start(node: Node) -> int | None:
        direct_body = node.child_by_field_name("body")
        if direct_body is not None:
            return direct_body.start_byte
        for descendant in TreeSitterAdapter.walk(node):
            if descendant is not node and descendant.type in NESTED_BODY_TYPES:
                return descendant.start_byte
        return None

    @staticmethod
    def ancestor(node: Node, kinds: set[str]) -> Node | None:
        parent = node.parent
        while parent is not None:
            if parent.type in kinds:
                return parent
            parent = parent.parent
        return None

    @staticmethod
    def record(
        *,
        path: str,
        source: bytes,
        node: Node,
        name: str,
        kind: SymbolKind,
        extractor: str,
        parent: str | None = None,
        decorators: list[str] | None = None,
        modifiers: list[str] | None = None,
        is_exported: bool | None = None,
    ) -> SymbolRecord:
        line_start = node.start_point.row + 1
        return SymbolRecord(
            id=f"sym:{path}:{line_start}:{kind.value}:{name}",
            path=path,
            name=name,
            kind=kind,
            line_start=line_start,
            line_end=max(line_start, node.end_point.row + 1),
            declaration=TreeSitterAdapter.compact_declaration(source, node),
            parent=parent,
            decorators=decorators or [],
            modifiers=modifiers or [],
            is_exported=is_exported,
            extractor=extractor,
        )


def named_child_text(source: bytes, node: Node, field: str) -> str | None:
    child = node.child_by_field_name(field)
    if child is None:
        return None
    return TreeSitterAdapter.text(source, child)
