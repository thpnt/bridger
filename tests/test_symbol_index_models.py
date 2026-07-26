from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.models.symbol_index import (
    SourceRange,
    SymbolFileExtraction,
    SymbolIndexArtifact,
    SymbolKind,
    SymbolRecord,
)


def symbol(**updates: object) -> SymbolRecord:
    values: dict[str, object] = {
        "id": "sym:test-example",
        "path": "src/example.py",
        "language": "python",
        "name": "example",
        "qualified_name": "example",
        "kind": SymbolKind.FUNCTION,
        "declaration_range": SourceRange(
            start_line=1,
            start_column=0,
            end_line=2,
            end_column=10,
            start_byte=0,
            end_byte=20,
        ),
        "body_range": None,
        "body_available": False,
        "declaration_preview": "def example()",
        "signature": "def example()",
        "extractor": "tree_sitter_python",
    }
    values.update(updates)
    return SymbolRecord.model_validate(values)


def test_symbol_index_models_accept_valid_minimal_artifact() -> None:
    artifact = SymbolIndexArtifact(
        generated_at=datetime(2026, 6, 18, tzinfo=UTC),
        symbols=[],
        files=[],
    )

    assert artifact.schema_version == 2
    assert artifact.symbols == []


@pytest.mark.parametrize("path", ["/absolute.py", "../outside.py", "src\\file.py"])
def test_symbol_index_models_reject_non_repository_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        symbol(path=path)
    with pytest.raises(ValidationError):
        SymbolFileExtraction(
            path=path, status="unsupported", symbol_count=0, errors=[]
        )


def test_symbol_index_models_reject_invalid_line_ranges() -> None:
    with pytest.raises(ValidationError):
        symbol(
            declaration_range=SourceRange(
                start_line=4, start_column=0, end_line=3, end_column=0
            )
        )


def test_symbol_output_contains_only_contract_fields() -> None:
    assert set(symbol().model_dump()) == {
        "id",
        "path",
        "language",
        "name",
        "qualified_name",
        "kind",
        "parent_id",
        "parent_name",
        "declaration_range",
        "body_range",
        "body_available",
        "declaration_preview",
        "signature",
        "decorators",
        "modifiers",
        "exported",
        "extraction_status",
        "extractor",
    }
