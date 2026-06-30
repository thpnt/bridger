import ast
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import TypeVar

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

RESOLVER_NAME = "python_ast"
T = TypeVar("T")


class PythonImportResolver:
    """Extract and conservatively resolve Python imports."""

    supported_extensions = frozenset({".py"})
    language = ImportLanguage.PYTHON

    def extract_imports(self, source_path: str, content: str) -> ImportExtractionResult:
        if PurePosixPath(source_path).suffix.lower() not in self.supported_extensions:
            return ImportExtractionResult(
                errors=[_resolver_error(source_path, "unsupported_extension")]
            )

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return ImportExtractionResult(
                errors=[_resolver_error(source_path, "parse_error")]
            )
        except Exception:
            return ImportExtractionResult(
                errors=[_resolver_error(source_path, "extraction_error")]
            )

        records: list[ImportRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                records.extend(_records_for_import(source_path, content, node))
            elif isinstance(node, ast.ImportFrom):
                records.extend(_records_for_from_import(source_path, content, node))
        return ImportExtractionResult(imports=records)

    def resolve_imports(
        self,
        source_path: str,
        imports: Sequence[ImportRecord],
        safe_files: SafeFileIndex,
    ) -> ImportResolutionResult:
        if not safe_files.contains(source_path):
            return ImportResolutionResult(
                errors=[_resolver_error(source_path, "source_not_in_safe_file_index")]
            )

        module_index = _PythonModuleIndex(safe_files)
        resolved: list[ResolvedImport] = []
        unresolved: list[UnresolvedImport] = []
        ignored: list[IgnoredImport] = []
        errors: list[ImportResolverError] = []

        for record in imports:
            if record.source_path != source_path:
                errors.append(
                    _resolver_error(
                        source_path,
                        "import_source_mismatch",
                        import_text=record.import_text,
                        specifier=record.specifier,
                    )
                )
                continue
            if record.language is not ImportLanguage.PYTHON:
                errors.append(
                    _resolver_error(
                        source_path,
                        "unsupported_language",
                        import_text=record.import_text,
                        specifier=record.specifier,
                    )
                )
                continue

            target = module_index.resolve(source_path, record)
            if target is not None:
                resolved.append(_resolved_import(record, target))
            elif record.is_relative or module_index.has_root(record.specifier):
                unresolved.append(_unresolved_import(record))
            else:
                ignored.append(_ignored_import(record))

        return ImportResolutionResult(
            resolved=_deduplicate(resolved),
            unresolved=_deduplicate(unresolved),
            ignored=_deduplicate(ignored),
            errors=_deduplicate(errors),
        )


class _PythonModuleIndex:
    def __init__(self, safe_files: SafeFileIndex) -> None:
        paths_by_module: dict[str, set[str]] = defaultdict(set)
        for path in safe_files.safe_paths:
            module = _module_name_for_path(path)
            if module is not None:
                paths_by_module[module].add(path)
        self._paths_by_module = {
            module: tuple(sorted(paths)) for module, paths in paths_by_module.items()
        }
        self._roots = frozenset(
            module.partition(".")[0] for module in self._paths_by_module
        )

    def has_root(self, specifier: str) -> bool:
        root = specifier.lstrip(".").partition(".")[0]
        return root in self._roots

    def resolve(self, source_path: str, record: ImportRecord) -> str | None:
        module_names = _candidate_module_names(source_path, record)
        for module_name in module_names:
            candidates = self._paths_by_module.get(module_name, ())
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                return None
        return None


def _records_for_import(
    source_path: str, content: str, node: ast.Import
) -> list[ImportRecord]:
    import_text = ast.get_source_segment(content, node) or _fallback_import_text(node)
    return [
        _import_record(
            source_path=source_path,
            import_text=import_text,
            specifier=alias.name,
            kind=ImportKind.IMPORT,
            node=node,
            is_relative=False,
        )
        for alias in node.names
    ]


def _records_for_from_import(
    source_path: str, content: str, node: ast.ImportFrom
) -> list[ImportRecord]:
    import_text = ast.get_source_segment(content, node) or _fallback_import_text(node)
    prefix = "." * node.level + (node.module or "")
    return [
        _import_record(
            source_path=source_path,
            import_text=import_text,
            specifier=_from_specifier(prefix, alias.name),
            kind=ImportKind.FROM_IMPORT,
            node=node,
            is_relative=node.level > 0,
        )
        for alias in node.names
    ]


def _from_specifier(prefix: str, imported_name: str) -> str:
    if imported_name == "*":
        return prefix
    if prefix.endswith("."):
        return prefix + imported_name
    return f"{prefix}.{imported_name}"


def _import_record(
    *,
    source_path: str,
    import_text: str,
    specifier: str,
    kind: ImportKind,
    node: ast.Import | ast.ImportFrom,
    is_relative: bool,
) -> ImportRecord:
    return ImportRecord(
        source_path=source_path,
        import_text=import_text,
        specifier=specifier,
        language=ImportLanguage.PYTHON,
        kind=kind,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        is_relative=is_relative,
    )


def _candidate_module_names(source_path: str, record: ImportRecord) -> tuple[str, ...]:
    if record.is_relative:
        full_name = _absolute_relative_module(source_path, record.specifier)
    else:
        full_name = record.specifier
    if full_name is None:
        return ()
    if record.kind is ImportKind.FROM_IMPORT and "." in full_name:
        return full_name, full_name.rsplit(".", maxsplit=1)[0]
    return (full_name,)


def _absolute_relative_module(source_path: str, specifier: str) -> str | None:
    level = len(specifier) - len(specifier.lstrip("."))
    imported_module = specifier[level:]
    source_module = _module_name_for_path(source_path)
    if source_module is None:
        return None

    source_path_obj = PurePosixPath(source_path)
    package_parts = source_module.split(".")
    if source_path_obj.name != "__init__.py":
        package_parts = package_parts[:-1]
    parent_count = level - 1
    if parent_count > len(package_parts):
        return None
    if parent_count:
        package_parts = package_parts[:-parent_count]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts) or None


def _module_name_for_path(path: str) -> str | None:
    parsed = PurePosixPath(path)
    if parsed.suffix.lower() != ".py":
        return None
    parts = list(parsed.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


def _fallback_import_text(node: ast.Import | ast.ImportFrom) -> str:
    return ast.unparse(node)


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
    root = record.specifier.lstrip(".").partition(".")[0]
    reason = (
        IgnoredImportReason.STANDARD_LIBRARY
        if root in sys.stdlib_module_names
        else IgnoredImportReason.EXTERNAL_PACKAGE
    )
    return IgnoredImport(
        source_path=record.source_path,
        import_text=record.import_text,
        specifier=record.specifier,
        language=record.language,
        reason=reason,
        resolver=RESOLVER_NAME,
    )


def _resolver_error(
    source_path: str,
    error: str,
    *,
    import_text: str | None = None,
    specifier: str | None = None,
) -> ImportResolverError:
    return ImportResolverError(
        source_path=source_path,
        resolver=RESOLVER_NAME,
        error=error,
        import_text=import_text,
        specifier=specifier,
    )


def _deduplicate(items: Iterable[T]) -> list[T]:
    unique: dict[str, T] = {}
    for item in items:
        key = repr(item)
        unique.setdefault(key, item)
    return list(unique.values())
