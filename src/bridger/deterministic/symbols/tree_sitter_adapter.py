import re
from collections.abc import Iterator, Sequence

from tree_sitter import Language, Node, Parser, Query, QueryCursor, Tree

from bridger.deterministic.symbols.base import ExtractionResult
from bridger.models.symbol_index import (
    FileExtractionStatus,
    SourceRange,
    SymbolExtractionError,
    SymbolExtractionStatus,
    SymbolKind,
    SymbolRecord,
)

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
    def __init__(
        self, language: Language, language_name: str, extractor_name: str
    ) -> None:
        self._language = language
        self.language_name = language_name
        self.extractor_name = extractor_name
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
    def _normalise(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _body_start(node: Node) -> int | None:
        if node.type in {"interface_declaration", "type_alias_declaration"}:
            return None
        direct_body = node.child_by_field_name("body")
        if direct_body is not None and TreeSitterAdapter._has_content(direct_body):
            return direct_body.start_byte
        for descendant in TreeSitterAdapter.walk(node):
            if (
                descendant is not node
                and descendant.type in NESTED_BODY_TYPES
                and TreeSitterAdapter._has_content(descendant)
            ):
                return descendant.start_byte
            if descendant.type in {"arrow_function", "function_expression"}:
                body = descendant.child_by_field_name("body")
                if body is not None and TreeSitterAdapter._has_content(body):
                    return body.start_byte
        return None

    @staticmethod
    def body(node: Node) -> Node | None:
        if node.type in {"interface_declaration", "type_alias_declaration"}:
            return None
        direct_body = node.child_by_field_name("body")
        if direct_body is not None and TreeSitterAdapter._has_content(direct_body):
            return direct_body
        for descendant in TreeSitterAdapter.walk(node):
            if (
                descendant is not node
                and descendant.type in NESTED_BODY_TYPES
                and TreeSitterAdapter._has_content(descendant)
            ):
                return descendant
            if descendant.type in {"arrow_function", "function_expression"}:
                body = descendant.child_by_field_name("body")
                if body is not None and TreeSitterAdapter._has_content(body):
                    return body
        return None

    @staticmethod
    def _has_content(node: Node) -> bool:
        return node.end_byte > node.start_byte and node.end_point > node.start_point

    @staticmethod
    def compact_declaration(source: bytes, node: Node) -> str:
        body_start = TreeSitterAdapter._body_start(node)
        end_byte = body_start if body_start is not None else node.end_byte
        declaration = (
            TreeSitterAdapter._normalise(
                source[node.start_byte : end_byte].decode("utf-8", errors="replace")
            )
            .rstrip("{: ")
            .strip()
        )
        if len(declaration) > MAX_DECLARATION_LENGTH:
            return declaration[: MAX_DECLARATION_LENGTH - 3].rstrip() + "..."
        return declaration

    @staticmethod
    def signature(source: bytes, node: Node) -> str:
        body_start = TreeSitterAdapter._body_start(node)
        end_byte = body_start if body_start is not None else node.end_byte
        return (
            TreeSitterAdapter._normalise(
                source[node.start_byte : end_byte].decode("utf-8", errors="replace")
            )
            .rstrip("{: ")
            .strip()
        )

    @staticmethod
    def source_range(node: Node) -> SourceRange:
        return SourceRange(
            start_line=node.start_point.row + 1,
            start_column=node.start_point.column,
            end_line=node.end_point.row + 1,
            end_column=node.end_point.column,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )

    def extraction_result(
        self, tree: Tree, symbols: list[SymbolRecord]
    ) -> ExtractionResult:
        error_nodes = [
            node
            for node in self.walk(tree.root_node)
            if node.type == "ERROR" or node.is_missing
        ]
        errors = [self._diagnostic(node) for node in error_nodes]
        if tree.root_node.has_error and not errors:
            errors.append(
                SymbolExtractionError(
                    code="parse_error",
                    message="Tree-sitter reported a syntax error during recovery",
                    line=tree.root_node.start_point.row + 1,
                    column=tree.root_node.start_point.column,
                    extractor=self.extractor_name,
                )
            )
        if not errors:
            return ExtractionResult(symbols=symbols)
        for index, symbol in enumerate(symbols):
            if not error_nodes or any(
                self._overlaps(symbol.declaration_range, node) for node in error_nodes
            ):
                symbols[index] = symbol.model_copy(
                    update={"extraction_status": SymbolExtractionStatus.PARTIAL}
                )
        return ExtractionResult(
            symbols=symbols,
            status=(
                FileExtractionStatus.PARTIAL
                if symbols
                else FileExtractionStatus.PARSE_ERROR
            ),
            errors=errors,
        )

    def _diagnostic(self, node: Node) -> SymbolExtractionError:
        return SymbolExtractionError(
            code="missing_node" if node.is_missing else "parse_error",
            message=(
                "Tree-sitter reported a missing syntax node"
                if node.is_missing
                else "Tree-sitter reported a recoverable syntax error"
            ),
            line=node.start_point.row + 1,
            column=node.start_point.column,
            extractor=self.extractor_name,
        )

    @staticmethod
    def _overlaps(source_range: SourceRange, node: Node) -> bool:
        start = (source_range.start_line, source_range.start_column)
        end = (source_range.end_line, source_range.end_column)
        node_start = (node.start_point.row + 1, node.start_point.column)
        node_end = (node.end_point.row + 1, node.end_point.column)
        return start < node_end and node_start < end

    @staticmethod
    def ancestor(node: Node, kinds: set[str]) -> Node | None:
        parent = node.parent
        while parent is not None:
            if parent.type in kinds:
                return parent
            parent = parent.parent
        return None

    @staticmethod
    def enclosing_scope_names(
        source: bytes, node: Node, kinds: set[str]
    ) -> tuple[str, ...]:
        scopes: list[str] = []
        parent = node.parent
        while parent is not None:
            if parent.type in kinds:
                name = named_child_text(source, parent, "name")
                if name:
                    scopes.append(name)
            parent = parent.parent
        scopes.reverse()
        return tuple(scopes)

    def record(
        self,
        *,
        path: str,
        source: bytes,
        node: Node,
        name: str,
        kind: SymbolKind,
        extractor: str,
        parent_scope_names: Sequence[str] = (),
        decorators: list[str] | None = None,
        modifiers: list[str] | None = None,
        exported: bool | None = None,
        include_body: bool = True,
    ) -> SymbolRecord:
        body = TreeSitterAdapter.body(node) if include_body else None
        scopes = [scope for scope in parent_scope_names if scope]
        qualified_name = ".".join([*scopes, name])
        return SymbolRecord(
            id=f"pending:{path}:{node.start_byte}:{kind.value}:{name}",
            path=path,
            language=self.language_name,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            parent_name=scopes[-1] if scopes else None,
            declaration_range=TreeSitterAdapter.source_range(node),
            body_range=TreeSitterAdapter.source_range(body) if body else None,
            body_available=body is not None,
            declaration_preview=TreeSitterAdapter.compact_declaration(source, node),
            signature=TreeSitterAdapter.signature(source, node),
            decorators=decorators or [],
            modifiers=modifiers or [],
            exported=exported,
            extractor=extractor,
        )


def named_child_text(source: bytes, node: Node, field: str) -> str | None:
    child = node.child_by_field_name(field)
    if child is None:
        return None
    return TreeSitterAdapter.text(source, child)
