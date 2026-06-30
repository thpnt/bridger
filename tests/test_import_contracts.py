from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.deterministic.repo_graph.imports import (
    IgnoredImport,
    IgnoredImportReason,
    ImportExtractionResult,
    ImportKind,
    ImportLanguage,
    ImportRecord,
    ImportResolutionResult,
    ImportResolver,
    ResolvedImport,
    SafeFileIndex,
    UnresolvedImport,
    UnresolvedImportReason,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)


def make_import_record(**overrides: object) -> ImportRecord:
    values: dict[str, object] = {
        "source_path": "src/example.py",
        "import_text": "from . import helper",
        "specifier": ".",
        "language": ImportLanguage.PYTHON,
        "kind": ImportKind.FROM_IMPORT,
        "line_start": 2,
        "line_end": 2,
        "is_relative": True,
    }
    values.update(overrides)
    return ImportRecord.model_validate(values)


def make_file_index() -> FileIndexArtifact:
    indexed_file = IndexedFile(
        path="src/example.py",
        extension=".py",
        size_bytes=1,
        line_count=1,
        sha256="0" * 64,
        is_binary=False,
        is_symlink=False,
        detected_encoding="utf-8",
    )
    return FileIndexArtifact(
        generated_at=datetime(2026, 6, 19, tzinfo=UTC),
        repo_root_name="example",
        files=[indexed_file],
        skipped_files=[
            SkippedFile(path="src/skipped.py", skip_reason=SkipReason.READ_ERROR)
        ],
        stats=FileIndexStats(
            files_seen=2,
            files_included=1,
            files_skipped=1,
            total_included_bytes=1,
        ),
    )


def test_import_record_accepts_valid_input() -> None:
    record = make_import_record()

    assert record.source_path == "src/example.py"
    assert record.is_relative is True


def test_resolved_import_accepts_valid_input() -> None:
    resolved = ResolvedImport(
        source_path="src/example.py",
        target_path="src/helper.py",
        import_text="from . import helper",
        specifier=".",
        language=ImportLanguage.PYTHON,
        resolver="python",
    )

    assert resolved.target_path == "src/helper.py"


def test_unresolved_import_accepts_valid_input() -> None:
    unresolved = UnresolvedImport(
        source_path="src/example.py",
        import_text="from .missing import value",
        specifier=".missing",
        language=ImportLanguage.PYTHON,
        reason=UnresolvedImportReason.NO_MATCHING_FILE,
        resolver="python",
    )

    assert unresolved.reason is UnresolvedImportReason.NO_MATCHING_FILE


def test_ignored_import_accepts_valid_input() -> None:
    ignored = IgnoredImport(
        source_path="src/example.py",
        import_text="import pydantic",
        specifier="pydantic",
        language=ImportLanguage.PYTHON,
        reason=IgnoredImportReason.EXTERNAL_PACKAGE,
        resolver="python",
    )

    assert ignored.reason is IgnoredImportReason.EXTERNAL_PACKAGE


@pytest.mark.parametrize("path", ["/absolute.py", "../outside.py", "src\\file.py"])
@pytest.mark.parametrize("field", ["source_path", "target_path"])
def test_resolved_import_rejects_unsafe_paths(field: str, path: str) -> None:
    values = {
        "source_path": "src/example.py",
        "target_path": "src/helper.py",
        "import_text": "from . import helper",
        "specifier": ".",
        "language": ImportLanguage.PYTHON,
        "resolver": "python",
    }
    values[field] = path

    with pytest.raises(ValidationError):
        ResolvedImport.model_validate(values)


def test_safe_file_index_contains_accepted_files_and_excludes_skipped_files() -> None:
    safe_files = SafeFileIndex(make_file_index())

    assert safe_files.safe_paths == frozenset({"src/example.py"})
    assert safe_files.contains("src/example.py")
    assert not safe_files.contains("src/skipped.py")


def test_safe_file_index_rejects_unsafe_lookup_paths() -> None:
    safe_files = SafeFileIndex(make_file_index())

    with pytest.raises(ValueError):
        safe_files.contains("../outside.py")


def test_safe_file_index_candidate_lookup_is_sorted_and_unique() -> None:
    safe_files = SafeFileIndex(make_file_index())

    assert safe_files.existing_candidates(
        ["src/missing.py", "src/example.py", "src/example.py"]
    ) == ("src/example.py",)


def test_import_resolver_protocol_can_be_implemented() -> None:
    class DummyResolver:
        supported_extensions = frozenset({".dummy"})
        language = ImportLanguage.PYTHON

        def extract_imports(
            self, source_path: str, content: str
        ) -> ImportExtractionResult:
            return ImportExtractionResult(imports=[make_import_record()])

        def resolve_imports(
            self,
            source_path: str,
            imports: Sequence[ImportRecord],
            safe_files: SafeFileIndex,
        ) -> ImportResolutionResult:
            return ImportResolutionResult()

    resolver: ImportResolver = DummyResolver()

    assert resolver.supported_extensions == frozenset({".dummy"})
    assert resolver.extract_imports("src/example.py", "").imports


def test_result_records_are_sorted_deterministically() -> None:
    result = ImportExtractionResult(
        imports=[
            make_import_record(line_start=3, line_end=3, specifier="z"),
            make_import_record(line_start=1, line_end=1, specifier="a"),
        ]
    )

    assert [record.line_start for record in result.imports] == [1, 3]
