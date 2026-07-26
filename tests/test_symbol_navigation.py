from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bridger.artifacts import write_artifact
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.symbols import build_symbol_index_for_project
from bridger.models.context_plan_bootstrap import ContextPlanBootstrapBudgets
from bridger.models.symbol_index import (
    FileExtractionStatus,
    SymbolIndexArtifact,
)
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.path_safety import PathSafetyService
from bridger.tools.services.symbols import SymbolService

GENERATED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def write_file(root: Path, path: str, content: str) -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)


def write_file_index(root: Path) -> None:
    write_artifact(
        root / ".bridger/artifacts/file-index.json",
        build_file_index_for_project(root),
    )


def build_symbols(root: Path):
    write_file_index(root)
    return build_symbol_index_for_project(root, generated_at=GENERATED_AT)


def test_same_line_duplicates_and_overloads_have_unique_ids(tmp_path: Path) -> None:
    write_file(tmp_path, "src/example.js", "class Box { run() {} run() {} }\n")
    write_file(
        tmp_path,
        "src/overloads.ts",
        "function load(value: string): void;\nfunction load(value: number): void;\n",
    )

    artifact = build_symbols(tmp_path)
    methods = [symbol for symbol in artifact.symbols if symbol.name == "run"]
    overloads = [symbol for symbol in artifact.symbols if symbol.name == "load"]

    assert len(methods) == 2
    assert len({symbol.id for symbol in methods}) == 2
    assert len(overloads) == 2
    assert len({symbol.id for symbol in overloads}) == 2


def test_unrelated_line_insertion_does_not_change_id(tmp_path: Path) -> None:
    write_file(tmp_path, "src/example.py", "def stable(value):\n    return value\n")
    first = build_symbols(tmp_path)
    first_id = next(symbol.id for symbol in first.symbols if symbol.name == "stable")

    write_file(
        tmp_path,
        "src/example.py",
        "# unrelated line\n\ndef stable(value):\n    return value\n",
    )
    second = build_symbol_index_for_project(tmp_path, generated_at=GENERATED_AT)
    second_id = next(symbol.id for symbol in second.symbols if symbol.name == "stable")

    assert first_id == second_id


def test_qualified_names_and_parent_ids_are_resolved(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.py",
        "class Outer:\n"
        "    class Inner:\n"
        "        def execute(self):\n"
        "            pass\n",
    )

    artifact = build_symbols(tmp_path)
    symbols = {symbol.qualified_name: symbol for symbol in artifact.symbols}

    assert symbols["Outer.Inner.execute"].parent_id == symbols["Outer.Inner"].id
    assert symbols["Outer.Inner"].parent_id == symbols["Outer"].id


def test_ranges_and_body_availability_are_exact(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.ts",
        "interface Contract { run(): void }\n"
        "function execute(\n"
        "  value: string,\n"
        ") {\n"
        "  return value\n"
        "}\n",
    )

    artifact = build_symbols(tmp_path)
    contract = next(symbol for symbol in artifact.symbols if symbol.name == "Contract")
    run = next(symbol for symbol in artifact.symbols if symbol.name == "run")
    execute = next(symbol for symbol in artifact.symbols if symbol.name == "execute")

    assert contract.body_range is None
    assert contract.body_available is False
    assert run.body_range is None
    assert run.body_available is False
    assert execute.declaration_range.start_line == 2
    assert execute.declaration_range.start_column == 0
    assert execute.body_range is not None
    assert execute.body_range.start_line == 4
    assert execute.body_range.start_column == 2
    assert execute.body_range.start_byte is not None
    assert execute.body_range.end_byte is not None


def test_file_statuses_and_partial_diagnostics_are_retained(tmp_path: Path) -> None:
    write_file(tmp_path, "valid.py", "def valid(): pass\n")
    write_file(tmp_path, "broken.py", "def broken(:\n")
    write_file(tmp_path, "notes.txt", "not supported\n")
    write_file(tmp_path, ".env", "SECRET=value\n")

    artifact = build_symbols(tmp_path)
    statuses = {result.path: result for result in artifact.files}

    assert statuses["valid.py"].status is FileExtractionStatus.SUCCESS
    assert statuses["notes.txt"].status is FileExtractionStatus.UNSUPPORTED
    assert statuses[".env"].status is FileExtractionStatus.SKIPPED
    assert statuses["broken.py"].status is FileExtractionStatus.PARTIAL
    assert statuses["broken.py"].errors[0].line == 1
    assert any(symbol.name == "broken" for symbol in artifact.symbols)
    assert (
        next(
            symbol for symbol in artifact.symbols if symbol.name == "broken"
        ).extraction_status.value
        == "partial"
    )


def test_duplicate_ids_fail_artifact_validation(tmp_path: Path) -> None:
    write_file(tmp_path, "example.py", "def first(): pass\ndef second(): pass\n")
    artifact = build_symbols(tmp_path)
    duplicate = artifact.symbols[1].model_copy(update={"id": artifact.symbols[0].id})

    with pytest.raises(ValidationError, match="duplicate symbol ID"):
        SymbolIndexArtifact(
            generated_at=GENERATED_AT,
            symbols=[artifact.symbols[0], duplicate],
            files=[artifact.files[0].model_copy(update={"symbol_count": 2})],
        )


def test_symbol_service_filters_searches_and_paginates(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.py",
        "def alpha(): pass\ndef beta(): pass\ndef gamma(): pass\n",
    )
    write_file_index(tmp_path)
    file_index = build_file_index_for_project(tmp_path)
    artifact = build_symbol_index_for_project(tmp_path, generated_at=GENERATED_AT)
    service = SymbolService(
        artifact,
        PathSafetyService(file_index, tmp_path),
        BudgetService(ContextPlanBootstrapBudgets(max_symbol_results=1)),
    )

    first = service.list_for_path("src/example.py")
    second = service.list_for_path("src/example.py", cursor=first["next_cursor"])
    third = service.list_for_path("src/example.py", cursor=second["next_cursor"])
    ids = [item["id"] for page in (first, second, third) for item in page["symbols"]]

    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert first["has_more"] is True
    assert third["has_more"] is False
    assert (
        service.list_for_path(
            path_prefix="src", language="python", kind="function", body_available=True
        )["total_matches"]
        == 3
    )
    assert service.search("alpha", match_mode="exact")["total_matches"] == 1

    with pytest.raises(BridgerToolError) as error:
        service.list_for_path("src/example.py", cursor="not-a-cursor")
    assert error.value.payload.error == "invalid_cursor"
