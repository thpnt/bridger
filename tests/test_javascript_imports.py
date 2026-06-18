from datetime import UTC, datetime

import pytest

from bridger.deterministic.repo_graph.imports import (
    IgnoredImportReason,
    ImportExtractionResult,
    ImportKind,
    ImportLanguage,
    ImportResolutionResult,
    JavaScriptImportResolver,
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


def extract_and_resolve(
    source_path: str, content: str, *target_paths: str
) -> tuple[ImportExtractionResult, ImportResolutionResult]:
    resolver = JavaScriptImportResolver()
    extraction = resolver.extract_imports(source_path, content)
    safe_files = make_safe_files(source_path, *target_paths)
    return extraction, resolver.resolve_imports(
        source_path, extraction.imports, safe_files
    )


def test_static_import_resolves() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.ts", 'import { router } from "./router";', "src/app/router.ts"
    )

    assert extraction.imports[0].kind is ImportKind.IMPORT
    assert resolution.resolved[0].target_path == "src/app/router.ts"


def test_side_effect_import_resolves() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.ts", 'import "./setup";', "src/app/setup.ts"
    )

    assert extraction.imports[0].specifier == "./setup"
    assert resolution.resolved[0].target_path == "src/app/setup.ts"


def test_export_from_resolves() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.ts", 'export { value } from "./value";', "src/app/value.ts"
    )

    assert extraction.imports[0].kind is ImportKind.EXPORT_FROM
    assert resolution.resolved[0].target_path == "src/app/value.ts"


def test_require_resolves() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.cjs", 'const value = require("./value");', "src/app/value.cjs"
    )

    assert extraction.imports[0].kind is ImportKind.REQUIRE
    assert resolution.resolved[0].target_path == "src/app/value.cjs"


def test_dynamic_import_resolves() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.js", 'const value = import("./value");', "src/app/value.js"
    )

    assert extraction.imports[0].kind is ImportKind.DYNAMIC_IMPORT
    assert resolution.resolved[0].target_path == "src/app/value.js"


def test_extensionless_import_uses_configured_extension_order() -> None:
    _, resolution = extract_and_resolve(
        "src/app/main.ts",
        'import value from "./value";',
        "src/app/value.js",
        "src/app/value.ts",
    )

    assert resolution.resolved[0].target_path == "src/app/value.ts"


@pytest.mark.parametrize("extension", [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"])
def test_exact_extension_import_resolves(extension: str) -> None:
    target_path = f"src/app/value{extension}"
    _, resolution = extract_and_resolve(
        "src/app/main.ts", f'import value from "./value{extension}";', target_path
    )

    assert resolution.resolved[0].target_path == target_path


def test_directory_index_import_resolves() -> None:
    _, resolution = extract_and_resolve(
        "src/app/main.ts",
        'import components from "./components";',
        "src/app/components/index.tsx",
    )

    assert resolution.resolved[0].target_path == "src/app/components/index.tsx"


@pytest.mark.parametrize(
    ("source_path", "content", "target_path", "language"),
    [
        (
            "src/app/main.tsx",
            'import Button from "./Button";',
            "src/app/Button.tsx",
            ImportLanguage.TSX,
        ),
        (
            "src/app/main.jsx",
            'import Button from "./Button";',
            "src/app/Button.jsx",
            ImportLanguage.JSX,
        ),
    ],
)
def test_jsx_family_import_resolves(
    source_path: str,
    content: str,
    target_path: str,
    language: ImportLanguage,
) -> None:
    extraction, resolution = extract_and_resolve(source_path, content, target_path)

    assert extraction.imports[0].language is language
    assert resolution.resolved[0].target_path == target_path


@pytest.mark.parametrize("specifier", ["react", "@/components/Button"])
def test_external_and_alias_imports_are_ignored(specifier: str) -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.ts", f'import value from "{specifier}";'
    )

    assert not resolution.unresolved
    assert resolution.ignored[0].reason is IgnoredImportReason.EXTERNAL_PACKAGE


def test_missing_relative_import_is_unresolved() -> None:
    _, resolution = extract_and_resolve(
        "src/app/main.ts", 'import value from "../missing";'
    )

    assert not resolution.resolved
    assert resolution.unresolved[0].reason is UnresolvedImportReason.NO_MATCHING_FILE


def test_skipped_file_cannot_be_a_resolution_target() -> None:
    resolver = JavaScriptImportResolver()
    extraction = resolver.extract_imports(
        "src/app/main.ts", 'import secret from "./secret";'
    )
    safe_files = make_safe_files(
        "src/app/main.ts", skipped_paths=("src/app/secret.ts",)
    )

    resolution = resolver.resolve_imports(
        "src/app/main.ts", extraction.imports, safe_files
    )

    assert not resolution.resolved
    assert resolution.unresolved


def test_malformed_source_returns_parse_error_without_crashing() -> None:
    resolver = JavaScriptImportResolver()

    result = resolver.extract_imports(
        "src/app/main.ts", 'import { value from "./value";'
    )

    assert result.errors[0].error == "parse_error"


def test_unsupported_source_returns_error_without_crashing() -> None:
    resolver = JavaScriptImportResolver()

    result = resolver.extract_imports("src/app/main.vue", "")

    assert result.errors[0].error == "unsupported_extension"


def test_output_ordering_is_deterministic() -> None:
    extraction, resolution = extract_and_resolve(
        "src/app/main.ts",
        "\n".join(
            [
                'import z from "./z";',
                'import a from "./a";',
            ]
        ),
        "src/app/z.ts",
        "src/app/a.ts",
    )

    assert [record.specifier for record in extraction.imports] == ["./z", "./a"]
    assert [record.target_path for record in resolution.resolved] == [
        "src/app/a.ts",
        "src/app/z.ts",
    ]
