import posixpath
from collections.abc import Sequence
from pathlib import PurePosixPath

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node

from bridger.deterministic.repo_graph.imports.models import (
    IgnoredImport,
    IgnoredImportReason,
    ImportExtractionResult,
    ImportKind,
    ImportLanguage,
    ImportRecord,
    ImportResolutionResult,
    ImportResolverError,
    ResolvedImport,
    UnresolvedImport,
    UnresolvedImportReason,
)
from bridger.deterministic.repo_graph.imports.safe_files import SafeFileIndex
from bridger.deterministic.symbols.tree_sitter_adapter import TreeSitterAdapter

SUPPORTED_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
RESOLVER_NAME = "tree_sitter_typescript_javascript"


class JavaScriptImportResolver:
    """Extract and conservatively resolve TypeScript/JavaScript imports."""

    supported_extensions = frozenset(SUPPORTED_EXTENSIONS)
    language = ImportLanguage.JAVASCRIPT

    def __init__(self) -> None:
        self._javascript = TreeSitterAdapter(
            Language(tree_sitter_javascript.language())
        )
        self._typescript = TreeSitterAdapter(
            Language(tree_sitter_typescript.language_typescript())
        )
        self._tsx = TreeSitterAdapter(Language(tree_sitter_typescript.language_tsx()))

    def extract_imports(self, source_path: str, content: str) -> ImportExtractionResult:
        extension = PurePosixPath(source_path).suffix.lower()
        adapter = self._adapter_for_extension(extension)
        if adapter is None:
            return ImportExtractionResult(
                errors=[
                    ImportResolverError(
                        source_path=source_path,
                        resolver=RESOLVER_NAME,
                        error="unsupported_extension",
                    )
                ]
            )

        source = content.encode("utf-8")
        try:
            tree = adapter.parse(source)
            records = self._extract_records(
                adapter=adapter,
                source_path=source_path,
                source=source,
                language=_language_for_extension(extension),
                root=tree.root_node,
            )
        except Exception:
            return ImportExtractionResult(
                errors=[
                    ImportResolverError(
                        source_path=source_path,
                        resolver=RESOLVER_NAME,
                        error="extraction_error",
                    )
                ]
            )

        errors: list[ImportResolverError] = []
        if tree.root_node.has_error:
            errors.append(
                ImportResolverError(
                    source_path=source_path,
                    resolver=RESOLVER_NAME,
                    error="parse_error",
                )
            )
        return ImportExtractionResult(imports=records, errors=errors)

    def resolve_imports(
        self,
        source_path: str,
        imports: Sequence[ImportRecord],
        safe_files: SafeFileIndex,
    ) -> ImportResolutionResult:
        if not safe_files.contains(source_path):
            return ImportResolutionResult(
                errors=[
                    ImportResolverError(
                        source_path=source_path,
                        resolver=RESOLVER_NAME,
                        error="source_not_in_safe_file_index",
                    )
                ]
            )

        resolved: list[ResolvedImport] = []
        unresolved: list[UnresolvedImport] = []
        ignored: list[IgnoredImport] = []
        errors: list[ImportResolverError] = []

        for record in imports:
            if record.source_path != source_path:
                errors.append(
                    ImportResolverError(
                        source_path=source_path,
                        resolver=RESOLVER_NAME,
                        error="import_source_mismatch",
                        import_text=record.import_text,
                        specifier=record.specifier,
                    )
                )
                continue
            try:
                if not _is_relative_specifier(record.specifier):
                    ignored.append(_ignored_import(record))
                    continue
                target = _resolve_relative_import(
                    source_path, record.specifier, safe_files
                )
                if target is not None:
                    resolved.append(_resolved_import(record, target))
                    continue
                unresolved.append(_unresolved_import(record))
            except Exception:
                errors.append(
                    ImportResolverError(
                        source_path=record.source_path,
                        resolver=RESOLVER_NAME,
                        error="resolution_error",
                        import_text=record.import_text,
                        specifier=record.specifier,
                    )
                )

        return ImportResolutionResult(
            resolved=resolved,
            unresolved=unresolved,
            ignored=ignored,
            errors=errors,
        )

    def _adapter_for_extension(self, extension: str) -> TreeSitterAdapter | None:
        if extension == ".ts":
            return self._typescript
        if extension == ".tsx":
            return self._tsx
        if extension in {".js", ".jsx", ".mjs", ".cjs"}:
            return self._javascript
        return None

    @staticmethod
    def _extract_records(
        *,
        adapter: TreeSitterAdapter,
        source_path: str,
        source: bytes,
        language: ImportLanguage,
        root: Node,
    ) -> list[ImportRecord]:
        records: list[ImportRecord] = []
        for node in adapter.walk(root):
            record = _record_for_node(
                adapter=adapter,
                source_path=source_path,
                source=source,
                language=language,
                node=node,
            )
            if record is not None:
                records.append(record)
        return records


def _record_for_node(
    *,
    adapter: TreeSitterAdapter,
    source_path: str,
    source: bytes,
    language: ImportLanguage,
    node: Node,
) -> ImportRecord | None:
    if node.type in {"import_statement", "export_statement"}:
        specifier_node = node.child_by_field_name("source")
        kind = (
            ImportKind.IMPORT
            if node.type == "import_statement"
            else ImportKind.EXPORT_FROM
        )
    elif node.type == "call_expression":
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return None
        function_text = adapter.text(source, function)
        if function_text == "require":
            kind = ImportKind.REQUIRE
        elif function.type == "import":
            kind = ImportKind.DYNAMIC_IMPORT
        else:
            return None
        specifier_node = _first_string_argument(arguments)
    else:
        return None

    specifier = _string_value(adapter, source, specifier_node)
    if specifier is None:
        return None
    line_start = node.start_point.row + 1
    return ImportRecord(
        source_path=source_path,
        import_text=adapter.text(source, node),
        specifier=specifier,
        language=language,
        kind=kind,
        line_start=line_start,
        line_end=max(line_start, node.end_point.row + 1),
        is_relative=_is_relative_specifier(specifier),
    )


def _first_string_argument(arguments: Node) -> Node | None:
    if not arguments.named_children:
        return None
    first_argument = arguments.named_children[0]
    if first_argument.type != "string":
        return None
    return first_argument


def _string_value(
    adapter: TreeSitterAdapter, source: bytes, string_node: Node | None
) -> str | None:
    if string_node is None or string_node.type != "string":
        return None
    fragments = [
        child for child in string_node.named_children if child.type == "string_fragment"
    ]
    if len(fragments) != 1:
        return None
    return adapter.text(source, fragments[0])


def _language_for_extension(extension: str) -> ImportLanguage:
    if extension == ".ts":
        return ImportLanguage.TYPESCRIPT
    if extension == ".tsx":
        return ImportLanguage.TSX
    if extension == ".jsx":
        return ImportLanguage.JSX
    return ImportLanguage.JAVASCRIPT


def _is_relative_specifier(specifier: str) -> bool:
    return specifier.startswith("./") or specifier.startswith("../")


def _resolve_relative_import(
    source_path: str, specifier: str, safe_files: SafeFileIndex
) -> str | None:
    source_directory = PurePosixPath(source_path).parent.as_posix()
    normalized = posixpath.normpath(posixpath.join(source_directory, specifier))
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        return None

    for candidate in _candidate_paths(normalized):
        if safe_files.contains(candidate):
            return candidate
    return None


def _candidate_paths(normalized_path: str) -> tuple[str, ...]:
    extension = PurePosixPath(normalized_path).suffix.lower()
    if extension:
        return (normalized_path,) if extension in SUPPORTED_EXTENSIONS else ()

    direct = tuple(
        f"{normalized_path}{extension}" for extension in SUPPORTED_EXTENSIONS
    )
    indexes = tuple(
        f"{normalized_path}/index{extension}" for extension in SUPPORTED_EXTENSIONS
    )
    return direct + indexes


def _resolved_import(record: ImportRecord, target_path: str) -> ResolvedImport:
    return ResolvedImport(
        source_path=record.source_path,
        target_path=target_path,
        import_text=record.import_text,
        specifier=record.specifier,
        language=record.language,
        resolver=RESOLVER_NAME,
    )


def _unresolved_import(record: ImportRecord) -> UnresolvedImport:
    return UnresolvedImport(
        source_path=record.source_path,
        import_text=record.import_text,
        specifier=record.specifier,
        language=record.language,
        reason=UnresolvedImportReason.NO_MATCHING_FILE,
        resolver=RESOLVER_NAME,
    )


def _ignored_import(record: ImportRecord) -> IgnoredImport:
    return IgnoredImport(
        source_path=record.source_path,
        import_text=record.import_text,
        specifier=record.specifier,
        language=record.language,
        reason=IgnoredImportReason.EXTERNAL_PACKAGE,
        resolver=RESOLVER_NAME,
    )
