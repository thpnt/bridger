import re

from tree_sitter import Language, Node

from bridger.deterministic.symbols.base import ExtractionResult
from bridger.deterministic.symbols.tree_sitter_adapter import (
    TreeSitterAdapter,
    named_child_text,
)
from bridger.models.symbol_index import SymbolKind, SymbolRecord

COMMON_QUERY = """
(function_declaration) @declaration
(class_declaration) @declaration
(method_definition) @method
(variable_declarator) @variable
"""

TYPESCRIPT_QUERY = (
    COMMON_QUERY
    + """
(interface_declaration) @declaration
(type_alias_declaration) @declaration
(enum_declaration) @declaration
(internal_module) @declaration
(module) @declaration
(method_signature) @method
(function_signature) @declaration
"""
)

MODIFIERS = (
    "export",
    "default",
    "async",
    "static",
    "private",
    "protected",
    "public",
    "readonly",
)


class EcmaScriptExtractor:
    def __init__(
        self,
        *,
        language: Language,
        language_name: str,
        extensions: frozenset[str],
        extractor_name: str,
        supports_types: bool,
    ) -> None:
        self.extensions = extensions
        self.language = language_name
        self.extractor_name = extractor_name
        self._adapter = TreeSitterAdapter(language, language_name, extractor_name)
        self._query = TYPESCRIPT_QUERY if supports_types else COMMON_QUERY

    def extract(self, path: str, source: bytes) -> ExtractionResult:
        tree = self._adapter.parse(source)
        symbols: list[SymbolRecord] = []
        for _, captures in self._adapter.matches(tree, self._query):
            node = next(iter(captures.values()))[0]
            symbol = self._symbol(path, source, node)
            if symbol is not None:
                symbols.append(symbol)
        return self._adapter.extraction_result(tree, symbols)

    def _symbol(self, path: str, source: bytes, node: Node) -> SymbolRecord | None:
        if node.type == "variable_declarator":
            return self._variable(path, source, node)
        name = named_child_text(source, node, "name")
        if name is None:
            return None
        kinds = {
            "function_declaration": SymbolKind.FUNCTION,
            "class_declaration": SymbolKind.CLASS,
            "method_definition": SymbolKind.METHOD,
            "method_signature": SymbolKind.METHOD,
            "function_signature": SymbolKind.FUNCTION,
            "interface_declaration": SymbolKind.INTERFACE,
            "type_alias_declaration": SymbolKind.TYPE_ALIAS,
            "enum_declaration": SymbolKind.ENUM,
            "internal_module": SymbolKind.NAMESPACE,
            "module": SymbolKind.MODULE,
        }
        scope_names = self._adapter.enclosing_scope_names(
            source,
            node,
            {
                "class_declaration",
                "function_declaration",
                "internal_module",
                "module",
            },
        )
        return self._adapter.record(
            path=path,
            source=source,
            node=node,
            name=name,
            kind=kinds[node.type],
            parent_scope_names=scope_names,
            modifiers=self._modifiers(source, node),
            exported=self._is_exported(node),
            extractor=self.extractor_name,
        )

    def _variable(self, path: str, source: bytes, node: Node) -> SymbolRecord | None:
        declaration = node.parent
        if declaration is None or declaration.type not in {
            "lexical_declaration",
            "variable_declaration",
        }:
            return None
        container = declaration.parent
        if container is not None and container.type == "export_statement":
            top_level = container.parent
        else:
            top_level = container
        if top_level is None or top_level.type != "program":
            return None
        name = named_child_text(source, node, "name")
        value = node.child_by_field_name("value")
        if name is None:
            return None
        declaration_text = self._adapter.text(source, declaration)
        is_const = bool(re.match(r"\s*const\b", declaration_text))
        is_function = value is not None and value.type in {
            "arrow_function",
            "function_expression",
        }
        return self._adapter.record(
            path=path,
            source=source,
            node=declaration,
            name=name,
            kind=(
                SymbolKind.FUNCTION
                if is_function
                else SymbolKind.CONSTANT
                if is_const
                else SymbolKind.VARIABLE
            ),
            modifiers=self._modifiers(source, declaration),
            exported=self._is_exported(declaration),
            extractor=self.extractor_name,
        )

    def _is_exported(self, node: Node) -> bool:
        return self._export_statement(node) is not None

    def _modifiers(self, source: bytes, node: Node) -> list[str]:
        export = self._export_statement(node)
        text = self._adapter.compact_declaration(source, node)
        if export is not None:
            prefix = source[export.start_byte : node.start_byte].decode(
                "utf-8", errors="replace"
            )
            text = f"{prefix} {text}"
        return [
            modifier for modifier in MODIFIERS if re.search(rf"\b{modifier}\b", text)
        ]

    @staticmethod
    def _export_statement(node: Node) -> Node | None:
        parent = node.parent
        while parent is not None:
            if parent.type in {"class_declaration", "class"}:
                return None
            if parent.type == "export_statement":
                return parent
            parent = parent.parent
        return None
