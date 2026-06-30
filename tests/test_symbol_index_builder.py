from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bridger.artifacts import write_artifact
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.symbols import build_symbol_index_for_project
from bridger.models.symbol_index import SymbolKind


def write_file(root: Path, path: str, content: str) -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)


def write_file_index(root: Path) -> None:
    write_artifact(
        root / ".bridger/artifacts/file-index.json",
        build_file_index_for_project(root),
    )


def symbols_by_name(root: Path) -> dict[str, list[object]]:
    artifact = build_symbol_index_for_project(root)
    result: dict[str, list[object]] = {}
    for symbol in artifact.symbols:
        result.setdefault(symbol.name, []).append(symbol)
    return result


def test_builder_extracts_python_symbols(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.py",
        """@registered('x')
class Example:
    @marked
    async def method(self):
        return None

def run():
    return None

async def fetch():
    return None

MAX_COUNT = 3
value = 1
""",
    )
    write_file_index(tmp_path)

    symbols = symbols_by_name(tmp_path)

    assert symbols["Example"][0].kind == SymbolKind.CLASS
    assert symbols["Example"][0].decorators == ["registered"]
    assert symbols["method"][0].kind == SymbolKind.METHOD
    assert symbols["method"][0].parent == "Example"
    assert symbols["method"][0].decorators == ["marked"]
    assert symbols["run"][0].kind == SymbolKind.FUNCTION
    assert symbols["fetch"][0].declaration.startswith("async def fetch")
    assert symbols["MAX_COUNT"][0].kind == SymbolKind.CONSTANT
    assert symbols["value"][0].kind == SymbolKind.VARIABLE


def test_builder_extracts_typescript_and_tsx_symbols(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.ts",
        """export function run() {}
export default class Example { private static method() {} }
export const load = async () => 1;
const factory = function () { return 1; };
export const VALUE = 3;
interface Contract {}
type Identifier = string;
enum State { Ready }
""",
    )
    write_file(
        tmp_path,
        "src/page.tsx",
        "export const HomePage = () => <main />;\n",
    )
    write_file_index(tmp_path)

    symbols = symbols_by_name(tmp_path)

    assert symbols["run"][0].is_exported is True
    assert symbols["Example"][0].modifiers == ["export", "default"]
    assert symbols["method"][0].parent == "Example"
    assert symbols["method"][0].modifiers == ["static", "private"]
    assert symbols["load"][0].kind == SymbolKind.FUNCTION
    assert symbols["factory"][0].kind == SymbolKind.FUNCTION
    assert symbols["factory"][0].declaration == "const factory = function ()"
    assert symbols["VALUE"][0].kind == SymbolKind.CONSTANT
    assert symbols["Contract"][0].kind == SymbolKind.INTERFACE
    assert symbols["Identifier"][0].kind == SymbolKind.TYPE_ALIAS
    assert symbols["State"][0].kind == SymbolKind.ENUM
    assert symbols["HomePage"][0].kind == SymbolKind.FUNCTION
    assert "component" not in symbols["HomePage"][0].model_dump_json()


def test_builder_extracts_javascript_and_jsx_symbols(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.js",
        "export function run() {}\nclass Example { method() {} }\n",
    )
    write_file(
        tmp_path,
        "src/view.jsx",
        "export const View = function () { return <div />; };\n",
    )
    write_file_index(tmp_path)

    symbols = symbols_by_name(tmp_path)

    assert symbols["run"][0].is_exported is True
    assert symbols["Example"][0].kind == SymbolKind.CLASS
    assert symbols["method"][0].parent == "Example"
    assert symbols["View"][0].kind == SymbolKind.FUNCTION


def test_builder_extracts_go_symbols(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "main.go",
        """package main
type User struct{}
type Runner interface { Run() }
type Identifier string
func Start() { var local = 3 }
func (user *User) Save() {}
var Current = 1
const Limit = 2
""",
    )
    write_file_index(tmp_path)

    symbols = symbols_by_name(tmp_path)

    assert symbols["User"][0].kind == SymbolKind.STRUCT
    assert symbols["User"][0].declaration == "type User struct"
    assert symbols["Runner"][0].kind == SymbolKind.INTERFACE
    assert symbols["Identifier"][0].kind == SymbolKind.TYPE
    assert symbols["Start"][0].kind == SymbolKind.FUNCTION
    assert symbols["Save"][0].kind == SymbolKind.METHOD
    assert symbols["Save"][0].parent == "User"
    assert symbols["Current"][0].kind == SymbolKind.VARIABLE
    assert symbols["Limit"][0].kind == SymbolKind.CONSTANT
    assert "local" not in symbols


def test_builder_extracts_php_symbols(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/example.php",
        """<?php
namespace App\\Domain;
function helper() {}
interface Contract { public function run(); }
trait Shared { protected static function reuse() {} }
enum State { case Ready; }
class Example { final public function execute() {} }
""",
    )
    write_file_index(tmp_path)

    symbols = symbols_by_name(tmp_path)

    assert symbols["App\\Domain"][0].kind == SymbolKind.NAMESPACE
    assert symbols["helper"][0].kind == SymbolKind.FUNCTION
    assert symbols["Contract"][0].kind == SymbolKind.INTERFACE
    assert symbols["Shared"][0].kind == SymbolKind.TRAIT
    assert symbols["State"][0].kind == SymbolKind.ENUM
    assert symbols["Example"][0].kind == SymbolKind.CLASS
    assert symbols["run"][0].parent == "Contract"
    assert symbols["reuse"][0].parent == "Shared"
    assert symbols["reuse"][0].modifiers == ["protected", "static"]
    assert symbols["execute"][0].parent == "Example"
    assert symbols["execute"][0].modifiers == ["public", "final"]


def test_builder_uses_only_included_file_index_paths(tmp_path: Path) -> None:
    write_file(tmp_path, "src/included.py", "def included(): pass\n")
    write_file(tmp_path, "node_modules/skipped.js", "function skipped() {}\n")
    write_file(tmp_path, "notes.txt", "unsupported")
    write_file_index(tmp_path)
    write_file(tmp_path, "src/absent.py", "def absent(): pass\n")

    artifact = build_symbol_index_for_project(tmp_path)

    assert [symbol.name for symbol in artifact.symbols] == ["included"]
    assert artifact.parse_errors == []


def test_builder_rejects_invalid_file_index_paths(tmp_path: Path) -> None:
    artifact_path = tmp_path / ".bridger/artifacts/file-index.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        '{"schema_version":1,"generated_at":"2026-06-18T00:00:00Z",'
        '"repo_root_name":"example","files":[{"path":"../outside.py",'
        '"extension":".py","size_bytes":0,"line_count":0,"sha256":"'
        + "0"
        * 64
        + '","is_binary":false,"is_symlink":false,"detected_encoding":"utf-8"}],'
        '"skipped_files":[],"stats":{"files_seen":1,"files_included":1,'
        '"files_skipped":0,"total_included_bytes":0}}'
    )

    with pytest.raises(ValidationError):
        build_symbol_index_for_project(tmp_path)


def test_malformed_file_records_error_and_keeps_partial_results(tmp_path: Path) -> None:
    write_file(tmp_path, "valid.py", "def valid(): pass\n")
    write_file(tmp_path, "broken.ts", "export function broken( {\n")
    write_file_index(tmp_path)

    artifact = build_symbol_index_for_project(tmp_path)

    assert any(symbol.name == "valid" for symbol in artifact.symbols)
    assert [(error.path, error.error) for error in artifact.parse_errors] == [
        ("broken.ts", "parse_error")
    ]


def test_symbol_order_and_ids_are_deterministic(tmp_path: Path) -> None:
    write_file(tmp_path, "z.py", "def second(): pass\ndef first(): pass\n")
    write_file(tmp_path, "a.py", "VALUE = 1\n")
    write_file_index(tmp_path)
    generated_at = datetime(2026, 6, 18, tzinfo=UTC)

    first = build_symbol_index_for_project(tmp_path, generated_at=generated_at)
    second = build_symbol_index_for_project(tmp_path, generated_at=generated_at)

    assert first == second
    assert [symbol.path for symbol in first.symbols] == ["a.py", "z.py", "z.py"]
    assert [symbol.id for symbol in first.symbols] == [
        symbol.id for symbol in second.symbols
    ]
