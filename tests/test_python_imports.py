from datetime import UTC, datetime

import pytest

from bridger.deterministic.repo_graph.imports import (
    IgnoredImportReason,
    ImportKind,
    PythonImportResolver,
    SafeFileIndex,
    UnresolvedImportReason,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)


def make_indexed_file(path: str) -> IndexedFile:
    return IndexedFile(
        path=path,
        extension="." + path.rsplit(".", maxsplit=1)[-1],
        size_bytes=1,
        line_count=1,
        sha256="0" * 64,
        is_binary=False,
        is_symlink=False,
        detected_encoding="utf-8",
    )


def make_safe_files(
    *accepted_paths: str, skipped_paths: tuple[str, ...] = ()
) -> SafeFileIndex:
    files = [make_indexed_file(path) for path in accepted_paths]
    skipped = [
        SkippedFile(path=path, skip_reason=SkipReason.IGNORED_FILE)
        for path in skipped_paths
    ]
    return SafeFileIndex(
        FileIndexArtifact(
            generated_at=datetime(2026, 6, 19, tzinfo=UTC),
            repo_root_name="example",
            files=files,
            skipped_files=skipped,
            stats=FileIndexStats(
                files_seen=len(files) + len(skipped),
                files_included=len(files),
                files_skipped=len(skipped),
                total_included_bytes=len(files),
            ),
        )
    )


def extract_and_resolve(source_path: str, content: str, *target_paths: str):
    resolver = PythonImportResolver()
    extraction = resolver.extract_imports(source_path, content)
    resolution = resolver.resolve_imports(
        source_path,
        extraction.imports,
        make_safe_files(source_path, *target_paths),
    )
    return extraction, resolution


@pytest.mark.parametrize(
    ("content", "target_path"),
    [
        ("import app.service", "app/service.py"),
        ("import app.domain.users", "app/domain/users.py"),
        ("from app import service", "app/service.py"),
        ("from app.service import handler", "app/service.py"),
    ],
)
def test_root_layout_imports_resolve(content: str, target_path: str) -> None:
    extraction, resolution = extract_and_resolve(
        "app/main.py", content, "app/__init__.py", target_path
    )

    assert extraction.imports
    assert resolution.resolved[0].target_path == target_path


def test_src_layout_import_resolves() -> None:
    _, resolution = extract_and_resolve(
        "src/bridger/main.py",
        "import bridger.cli",
        "src/bridger/__init__.py",
        "src/bridger/cli.py",
    )

    assert resolution.resolved[0].target_path == "src/bridger/cli.py"


def test_package_init_resolution_works() -> None:
    _, resolution = extract_and_resolve(
        "app/main.py", "import app.services", "app/services/__init__.py"
    )

    assert resolution.resolved[0].target_path == "app/services/__init__.py"


@pytest.mark.parametrize(
    ("source_path", "content", "target_path"),
    [
        ("src/app/main.py", "from . import service", "src/app/service.py"),
        (
            "src/app/routes/user.py",
            "from ..domain import users",
            "src/app/domain/users.py",
        ),
    ],
)
def test_relative_imports_resolve(
    source_path: str, content: str, target_path: str
) -> None:
    _, resolution = extract_and_resolve(source_path, content, target_path)

    assert resolution.resolved[0].target_path == target_path


def test_aliases_and_line_numbers_are_extracted() -> None:
    resolver = PythonImportResolver()

    extraction = resolver.extract_imports(
        "app/main.py",
        "import app.service as service\nfrom app import routes as routes\n",
    )

    assert [record.kind for record in extraction.imports] == [
        ImportKind.IMPORT,
        ImportKind.FROM_IMPORT,
    ]
    assert [record.specifier for record in extraction.imports] == [
        "app.service",
        "app.routes",
    ]
    assert [record.line_start for record in extraction.imports] == [1, 2]


@pytest.mark.parametrize("content", ["import pydantic", "from typer import Typer"])
def test_external_imports_are_ignored(content: str) -> None:
    _, resolution = extract_and_resolve("app/main.py", content)

    assert not resolution.unresolved
    assert resolution.ignored[0].reason is IgnoredImportReason.EXTERNAL_PACKAGE


def test_standard_library_import_is_ignored() -> None:
    _, resolution = extract_and_resolve("app/main.py", "import pathlib")

    assert resolution.ignored[0].reason is IgnoredImportReason.STANDARD_LIBRARY


def test_missing_relative_import_is_unresolved() -> None:
    _, resolution = extract_and_resolve("src/app/main.py", "from . import missing")

    assert resolution.unresolved[0].reason is UnresolvedImportReason.NO_MATCHING_FILE


def test_missing_local_submodule_is_unresolved() -> None:
    _, resolution = extract_and_resolve(
        "src/app/main.py", "import app.missing", "src/app/__init__.py"
    )

    assert not resolution.ignored
    assert resolution.unresolved[0].specifier == "app.missing"


def test_invalid_python_returns_parse_error() -> None:
    result = PythonImportResolver().extract_imports("app/main.py", "from app import")

    assert not result.imports
    assert result.errors[0].error == "parse_error"


def test_unsupported_file_returns_error() -> None:
    result = PythonImportResolver().extract_imports("app/main.txt", "")

    assert result.errors[0].error == "unsupported_extension"


def test_skipped_file_cannot_be_returned() -> None:
    resolver = PythonImportResolver()
    extraction = resolver.extract_imports("app/main.py", "from . import secret")
    safe_files = make_safe_files("app/main.py", skipped_paths=("app/secret.py",))

    resolution = resolver.resolve_imports("app/main.py", extraction.imports, safe_files)

    assert not resolution.resolved
    assert resolution.unresolved


def test_ambiguous_src_and_root_modules_are_unresolved() -> None:
    _, resolution = extract_and_resolve(
        "main.py", "import app.service", "app/service.py", "src/app/service.py"
    )

    assert not resolution.resolved
    assert resolution.unresolved


def test_duplicate_imports_are_deduplicated_after_resolution() -> None:
    _, resolution = extract_and_resolve(
        "app/main.py", "import app.service\nimport app.service\n", "app/service.py"
    )

    assert len(resolution.resolved) == 1
