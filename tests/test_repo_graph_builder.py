from datetime import UTC, datetime
from pathlib import Path

from bridger.artifacts import write_artifact
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.repo_context import build_repo_context_for_project
from bridger.deterministic.repo_graph import build_repo_graph_for_project
from bridger.deterministic.symbols import build_symbol_index_for_project
from bridger.models.repo_graph import GraphEdgeKind, GraphNodeKind


def write_file(root: Path, path: str, content: str = "") -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)


def write_prerequisite_artifacts(root: Path) -> None:
    artifacts = root / ".bridger" / "artifacts"
    file_index = build_file_index_for_project(root)
    write_artifact(artifacts / "file-index.json", file_index)
    repo_context = build_repo_context_for_project(root)
    write_artifact(artifacts / "repo-context.json", repo_context)
    symbol_index = build_symbol_index_for_project(root)
    write_artifact(artifacts / "symbol-index.json", symbol_index)


def build_fixture_graph(root: Path):
    files = {
        "pyproject.toml": (
            "[project]\nname = 'example'\n[project.scripts]\nexample = 'app.cli:main'\n"
        ),
        "package.json": (
            '{"bin":{"web":"./web.js"},"main":"./web.js","module":"./missing.js"}'
        ),
        "src/app/__init__.py": "",
        "src/app/cli.py": (
            "from . import service\nfrom . import service\n"
            "from .missing import value\nimport pydantic\ndef main(): pass\n"
        ),
        "src/app/service.py": "def serve(): pass\n",
        "web.js": (
            'import "./util";\nimport "./missing";\nimport React from "react";\n'
        ),
        "util.js": "export const value = 1;\n",
        "app/api/users/route.ts": "export function GET() {}\n",
        "main.py": "print('main')\n",
        "node_modules/skipped.js": "export const skipped = true;\n",
    }
    for path, content in files.items():
        write_file(root, path, content)
    write_prerequisite_artifacts(root)
    return build_repo_graph_for_project(
        root, generated_at=datetime(2026, 6, 19, tzinfo=UTC)
    )


def test_builder_creates_structural_nodes_and_edges(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)
    nodes = {node.id: node for node in graph.nodes}
    edge_keys = {(edge.from_id, edge.to_id, edge.kind) for edge in graph.edges}

    assert nodes["dir:src/app"].kind is GraphNodeKind.DIRECTORY
    assert nodes["file:src/app/cli.py"].kind is GraphNodeKind.FILE
    assert ("dir:src/app", "file:src/app/cli.py", GraphEdgeKind.CONTAINS) in edge_keys
    symbol_nodes = [node for node in graph.nodes if node.kind is GraphNodeKind.SYMBOL]
    assert any(
        node.symbol_id and node.symbol_id.endswith(":main") for node in symbol_nodes
    )
    assert any(edge.kind is GraphEdgeKind.DECLARES_SYMBOL for edge in graph.edges)


def test_builder_creates_python_and_javascript_import_edges(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)
    imports = {
        (edge.from_id, edge.to_id)
        for edge in graph.edges
        if edge.kind is GraphEdgeKind.IMPORTS
    }

    assert ("file:src/app/cli.py", "file:src/app/service.py") in imports
    assert ("file:web.js", "file:util.js") in imports


def test_builder_records_only_local_unresolved_imports(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)

    assert {item.from_path for item in graph.unresolved_imports} == {
        "src/app/cli.py",
        "web.js",
    }
    assert all("pydantic" not in item.import_text for item in graph.unresolved_imports)
    assert all("react" not in item.import_text for item in graph.unresolved_imports)


def test_builder_excludes_skipped_and_absent_paths(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)

    persisted_paths = {node.path for node in graph.nodes if node.path is not None}
    assert "node_modules/skipped.js" not in persisted_paths
    assert "missing.js" not in persisted_paths


def test_builder_deduplicates_edges_and_is_deterministic(tmp_path: Path) -> None:
    first = build_fixture_graph(tmp_path)
    second = build_repo_graph_for_project(
        tmp_path, generated_at=datetime(2026, 6, 19, tzinfo=UTC)
    )
    python_edges = [
        edge
        for edge in first.edges
        if edge.kind is GraphEdgeKind.IMPORTS
        and edge.from_id == "file:src/app/cli.py"
        and edge.to_id == "file:src/app/service.py"
    ]

    assert len(python_edges) == 1
    assert first == second


def test_manifest_entrypoints_resolve_without_guessing(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)
    entrypoint_edges = [
        edge for edge in graph.edges if edge.kind is GraphEdgeKind.DECLARES_ENTRYPOINT
    ]
    entrypoint_targets = {edge.to_id for edge in entrypoint_edges}
    manifest_nodes = {
        node.key: node
        for node in graph.nodes
        if node.kind is GraphNodeKind.MANIFEST_ENTRY
    }

    assert "file:src/app/cli.py" in entrypoint_targets
    assert "file:web.js" in entrypoint_targets
    assert "module" in manifest_nodes
    assert all(edge.from_id != manifest_nodes["module"].id for edge in entrypoint_edges)


def test_path_patterns_match_only_safe_files(tmp_path: Path) -> None:
    graph = build_fixture_graph(tmp_path)
    matches = [
        edge for edge in graph.edges if edge.kind is GraphEdgeKind.MATCHES_PATH_PATTERN
    ]

    assert any(
        edge.from_id == "file:app/api/users/route.ts"
        and edge.to_id == "framework_pattern:next_app_route"
        for edge in matches
    )
    assert any(
        edge.from_id == "file:main.py"
        and edge.to_id == "framework_pattern:python_main_file"
        for edge in matches
    )
    assert all("skipped" not in edge.from_id for edge in matches)
    assert all(
        edge.kind
        in {
            GraphEdgeKind.CONTAINS,
            GraphEdgeKind.DECLARES_SYMBOL,
            GraphEdgeKind.IMPORTS,
            GraphEdgeKind.DECLARES_ENTRYPOINT,
            GraphEdgeKind.MATCHES_PATH_PATTERN,
        }
        for edge in graph.edges
    )
