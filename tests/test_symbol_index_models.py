from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.models.symbol_index import (
    SymbolIndexArtifact,
    SymbolKind,
    SymbolParseError,
    SymbolRecord,
)


def symbol(**updates: object) -> SymbolRecord:
    values: dict[str, object] = {
        "id": "sym:src/example.py:1:function:example",
        "path": "src/example.py",
        "name": "example",
        "kind": SymbolKind.FUNCTION,
        "line_start": 1,
        "line_end": 2,
        "declaration": "def example()",
        "extractor": "tree_sitter_python",
    }
    values.update(updates)
    return SymbolRecord.model_validate(values)


def test_symbol_index_models_accept_valid_minimal_artifact() -> None:
    artifact = SymbolIndexArtifact(
        generated_at=datetime(2026, 6, 18, tzinfo=UTC),
        symbols=[],
        parse_errors=[],
    )

    assert artifact.schema_version == 1
    assert artifact.symbols == []


@pytest.mark.parametrize("path", ["/absolute.py", "../outside.py", "src\\file.py"])
def test_symbol_index_models_reject_non_repository_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        symbol(path=path)
    with pytest.raises(ValidationError):
        SymbolParseError(path=path, extractor="test", error="parse_error")


def test_symbol_index_models_reject_invalid_line_ranges() -> None:
    with pytest.raises(ValidationError):
        symbol(line_start=4, line_end=3)


def test_symbol_output_contains_only_contract_fields() -> None:
    assert set(symbol().model_dump()) == {
        "id",
        "path",
        "name",
        "kind",
        "line_start",
        "line_end",
        "declaration",
        "parent",
        "decorators",
        "modifiers",
        "is_exported",
        "extractor",
    }
