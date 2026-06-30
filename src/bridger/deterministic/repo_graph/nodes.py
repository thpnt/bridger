from pathlib import PurePosixPath

from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_graph import GraphEdge, GraphEdgeKind, GraphNode, GraphNodeKind
from bridger.models.symbol_index import SymbolIndexArtifact


def build_file_and_directory_graph(
    file_index: FileIndexArtifact,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    file_paths = sorted({file.path for file in file_index.files})
    directory_paths = _directory_paths(file_paths)
    nodes = [
        GraphNode(id=_directory_id(path), kind=GraphNodeKind.DIRECTORY, path=path)
        for path in sorted(directory_paths)
    ]
    nodes.extend(
        GraphNode(id=_file_id(path), kind=GraphNodeKind.FILE, path=path)
        for path in file_paths
    )

    edges: list[GraphEdge] = []
    for directory in sorted(directory_paths):
        if directory == ".":
            continue
        parent = PurePosixPath(directory).parent.as_posix()
        edges.append(
            GraphEdge(
                from_id=_directory_id(parent),
                to_id=_directory_id(directory),
                kind=GraphEdgeKind.CONTAINS,
            )
        )
    edges.extend(
        GraphEdge(
            from_id=_directory_id(PurePosixPath(path).parent.as_posix()),
            to_id=_file_id(path),
            kind=GraphEdgeKind.CONTAINS,
        )
        for path in file_paths
    )
    return nodes, edges


def build_symbol_graph(
    symbol_index: SymbolIndexArtifact, safe_paths: frozenset[str]
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for symbol in symbol_index.symbols:
        if symbol.path not in safe_paths:
            continue
        node_id = f"symbol:{symbol.id}"
        nodes.append(
            GraphNode(
                id=node_id,
                kind=GraphNodeKind.SYMBOL,
                symbol_id=symbol.id,
            )
        )
        edges.append(
            GraphEdge(
                from_id=_file_id(symbol.path),
                to_id=node_id,
                kind=GraphEdgeKind.DECLARES_SYMBOL,
            )
        )
    return nodes, edges


def _directory_paths(file_paths: list[str]) -> set[str]:
    directories = {"."}
    for path in file_paths:
        parent = PurePosixPath(path).parent
        while parent.as_posix() != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _directory_id(path: str) -> str:
    return f"dir:{path}"


def _file_id(path: str) -> str:
    return f"file:{path}"
