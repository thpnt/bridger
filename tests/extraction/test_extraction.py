"""Focused invariants for deterministic Layer 2 extraction."""

import json
import subprocess
from pathlib import Path

import pytest

from bridger.contracts.files import (
    FileDisposition,
    FileIndex,
    FileRecord,
    summarize_files,
)
from bridger.contracts.repository import RepositoryContext
from bridger.extraction.graphify import adapt_file_index_to_graphify
from bridger.extraction.service import extract_repository_facts
from bridger.repository.service import prepare_repository


def test_adapter_selects_only_extractable_fully_readable_files(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    records = [
        _file_record("a.py", processing_mode="extract", read_mode="full"),
        _file_record("b.py", processing_mode="metadata_only", read_mode="full"),
        _file_record("c.py", processing_mode="skip", read_mode="full"),
        _file_record("d.py", processing_mode="extract", read_mode="bounded"),
        _file_record("e.py", processing_mode="extract", read_mode="denied"),
        _file_record("f.py", processing_mode="extract", read_mode="full"),
    ]
    for record in records:
        (repository / record.path).write_text("value = 1\n", encoding="utf-8")
    context = _context(repository)
    file_index = _file_index(context, records)

    selected = adapt_file_index_to_graphify(context, file_index)

    assert selected == [
        (repository / "a.py").resolve(),
        (repository / "f.py").resolve(),
    ]


def test_python_symbols_are_source_backed_ordered_and_parented(
    tmp_path: Path,
) -> None:
    repository = _initialize_repository(tmp_path)
    source = repository / "service.py"
    source.write_text(
        "class Service:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n"
        "\n"
        "    def run(self, count: int) -> str:\n"
        "        return self.name * count\n"
        "\n"
        "def helper(value: int) -> int:\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, graphify_result = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert list(symbols) == [
        "Service",
        "Service.__init__",
        "Service.run",
        "helper",
    ]
    assert symbols["Service"].kind == "class"
    assert symbols["Service.__init__"].kind == "constructor"
    assert symbols["Service.run"].kind == "method"
    assert symbols["helper"].kind == "function"
    assert symbols["Service.run"].parent_symbol_id == symbols["Service"].symbol_id
    assert symbols["Service.run"].path == "service.py"
    assert symbols["Service.run"].start_line == 5
    assert symbols["Service.run"].end_line == 6
    assert symbols["Service.run"].signature == "def run(self, count: int) -> str:"
    assert report.attempted_files == 1
    assert report.successful_files == 1
    assert report.failed_files == []
    assert report.produced_symbols == 4
    assert len(graphify_result["nodes"]) > 0
    assert len(graphify_result["edges"]) > 0


def test_cold_and_warm_cache_produce_identical_symbol_indexes(
    tmp_path: Path,
) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "module.py").write_text(
        "class Example:\n" "    def method(self) -> None:\n" "        pass\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)
    cache_root = tmp_path / "cache"

    cold_index, cold_report, cold_graphify = extract_repository_facts(
        context,
        file_index,
        cache_root=cache_root,
        parallel=False,
    )
    warm_index, warm_report, warm_graphify = extract_repository_facts(
        context,
        file_index,
        cache_root=cache_root,
        parallel=False,
    )

    assert warm_index == cold_index
    assert warm_report == cold_report
    assert warm_graphify["symbols"] == cold_graphify["symbols"]
    assert warm_graphify["nodes"] == cold_graphify["nodes"]
    assert warm_graphify["edges"] == cold_graphify["edges"]
    assert [
        (node["label"], node.get("source_location")) for node in cold_graphify["nodes"]
    ] == [
        ("module.py", "L1"),
        ("Example", "L1"),
        (".method()", "L2"),
    ]
    assert [edge["relation"] for edge in cold_graphify["edges"]] == [
        "contains",
        "method",
    ]


def test_ast_cache_entry_without_symbols_is_regenerated(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "cached.py").write_text("def cached():\n    pass\n", encoding="utf-8")
    _commit(repository)
    context, file_index = prepare_repository(repository)
    cache_root = tmp_path / "cache"

    expected, _, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=cache_root,
        parallel=False,
    )
    cache_entries = list(cache_root.glob("graphify-out/cache/ast/v*/*.json"))
    assert len(cache_entries) == 1
    cached_payload = json.loads(cache_entries[0].read_text(encoding="utf-8"))
    cached_payload.pop("symbols")
    cache_entries[0].write_text(json.dumps(cached_payload), encoding="utf-8")

    regenerated, report, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=cache_root,
        parallel=False,
    )

    assert regenerated == expected
    assert report.successful_files == 1
    repaired_payload = json.loads(cache_entries[0].read_text(encoding="utf-8"))
    assert repaired_payload["symbols"]


def test_parallel_workers_return_private_symbols(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    for index in range(20):
        (repository / f"module_{index:02}.py").write_text(
            f"def item_{index}():\n    pass\n",
            encoding="utf-8",
        )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=True,
        max_workers=2,
    )

    assert len(symbol_index.symbols) == 20
    assert report.attempted_files == 20
    assert report.successful_files == 20
    assert report.failed_files == []


def test_go_dedicated_extractor_emits_types_fields_and_methods(
    tmp_path: Path,
) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "service.go").write_text(
        "package repository\n\n"
        "type Service struct {\n"
        "    Name string\n"
        "}\n\n"
        "func (service *Service) Run() string {\n"
        "    return service.Name\n"
        "}\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert symbols["repository.Service"].kind == "struct"
    assert symbols["repository.Service.Name"].kind == "field"
    assert symbols["repository.Service.Run"].kind == "method"
    assert (
        symbols["repository.Service.Run"].parent_symbol_id
        == symbols["repository.Service"].symbol_id
    )
    assert report.failed_files == []


def test_graph_enum_members_are_present_in_symbol_index(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "Status.java").write_text(
        "public enum Status {\n    READY,\n    DONE;\n}\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, graphify_result = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert symbols["Status"].kind == "enum"
    assert symbols["Status.READY"].kind == "enum_member"
    assert symbols["Status.DONE"].kind == "enum_member"
    assert symbols["Status.READY"].parent_symbol_id == symbols["Status"].symbol_id
    assert [
        edge["relation"]
        for edge in graphify_result["edges"]
        if edge["relation"] == "case_of"
    ] == ["case_of", "case_of"]
    assert report.failed_files == []


def test_exported_graph_variables_are_present_in_symbol_index(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "settings.ts").write_text(
        "export const settings = { retries: 3 };\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert symbols["settings"].kind == "variable"
    assert report.failed_files == []


def test_ruby_factory_class_matches_graph_symbol(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "invoice.rb").write_text(
        "module Billing\n"
        "  Invoice = Struct.new(:total) do\n"
        "    def payable?\n"
        "      total > 0\n"
        "    end\n"
        "  end\n"
        "end\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, graphify_result = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert symbols["Billing.Invoice"].kind == "class"
    assert symbols["Billing.Invoice.payable?"].kind == "method"
    assert (
        symbols["Billing.Invoice.payable?"].parent_symbol_id
        == symbols["Billing.Invoice"].symbol_id
    )
    assert "Billing::Invoice" in {node["label"] for node in graphify_result["nodes"]}
    assert report.failed_files == []


def test_sql_tables_and_views_match_graph_symbols(tmp_path: Path) -> None:
    pytest.importorskip("tree_sitter_sql")
    repository = _initialize_repository(tmp_path)
    (repository / "schema.sql").write_text(
        "CREATE TABLE users (id INTEGER PRIMARY KEY);\n"
        "CREATE VIEW active_users AS SELECT id FROM users;\n"
        "CREATE PROCEDURE refresh_users() SELECT id FROM users;\n",
        encoding="utf-8",
    )
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, graphify_result = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    symbols = {symbol.qualified_name: symbol for symbol in symbol_index.symbols}
    assert symbols["users"].kind == "table"
    assert symbols["active_users"].kind == "view"
    assert symbols["refresh_users"].kind == "procedure"
    assert symbols["refresh_users"].start_line == 3
    assert symbols["refresh_users"].end_line == 3
    graph_labels = {node["label"] for node in graphify_result["nodes"]}
    assert {"users", "active_users", "refresh_users()"} <= graph_labels
    assert report.failed_files == []


def test_graphify_failure_is_reported_instead_of_omitted(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "unsupported.r").write_text("value <- 1\n", encoding="utf-8")
    context = _context(repository)
    records = [
        _file_record(
            "unsupported.r",
            processing_mode="extract",
            read_mode="full",
        )
    ]

    symbol_index, report, _ = extract_repository_facts(
        context,
        _file_index(context, records),
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    assert symbol_index.symbols == []
    assert report.attempted_files == 1
    assert report.successful_files == 0
    assert [failure.path for failure in report.failed_files] == ["unsupported.r"]
    assert "no AST extractor" in report.failed_files[0].error


def test_file_with_no_declarations_is_still_successful(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    (repository / "empty.py").write_text("# no declarations\n", encoding="utf-8")
    _commit(repository)
    context, file_index = prepare_repository(repository)

    symbol_index, report, _ = extract_repository_facts(
        context,
        file_index,
        cache_root=tmp_path / "cache",
        parallel=False,
    )

    assert symbol_index.symbols == []
    assert report.attempted_files == 1
    assert report.successful_files == 1
    assert report.failed_files == []


def test_adapter_rejects_mismatched_repository_identity(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    context = _context(repository)
    file_index = _file_index(context, [])
    mismatched = context.model_copy(update={"repository_id": "other"})

    with pytest.raises(ValueError, match="repository_id differ"):
        adapt_file_index_to_graphify(mismatched, file_index)


def _file_record(
    path: str,
    *,
    processing_mode: str,
    read_mode: str,
) -> FileRecord:
    return FileRecord(
        path=path,
        git_object_id="1" * 40,
        size_bytes=10,
        content_type="source",
        language="Python",
        disposition=FileDisposition(
            processing_mode=processing_mode,
            read_mode=read_mode,
        ),
    )


def _context(repository: Path) -> RepositoryContext:
    return RepositoryContext(
        repository_id="test-repository",
        root_path=repository,
        revision="a" * 40,
    )


def _file_index(
    context: RepositoryContext,
    records: list[FileRecord],
) -> FileIndex:
    ordered_records = sorted(records, key=lambda record: record.path)
    return FileIndex(
        schema_version="1",
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        files=ordered_records,
        summary=summarize_files(ordered_records),
    )


def _initialize_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Layer Two Test")
    return repository


def _commit(repository: Path) -> None:
    _git(repository, "add", "-A")
    _git(repository, "commit", "-m", "fixture")


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
