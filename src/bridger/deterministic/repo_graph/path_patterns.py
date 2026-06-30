from pathlib import PurePosixPath

from bridger.models.repo_graph import GraphEdge, GraphEdgeKind, GraphNode, GraphNodeKind

PATTERN_NODE_IDS = {
    "next_app_route": "framework_pattern:next_app_route",
    "next_app_page": "framework_pattern:next_app_page",
    "next_pages_api_route": "framework_pattern:next_pages_api_route",
    "frontend_main_file": "framework_pattern:frontend_main_file",
    "python_main_file": "framework_pattern:python_main_file",
    "python_app_file": "framework_pattern:python_app_file",
}


def build_path_pattern_graph(
    safe_paths: frozenset[str],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    matched_patterns: set[str] = set()
    edges: list[GraphEdge] = []
    for path in sorted(safe_paths):
        for pattern in _patterns_for_path(path):
            matched_patterns.add(pattern)
            edges.append(
                GraphEdge(
                    from_id=f"file:{path}",
                    to_id=PATTERN_NODE_IDS[pattern],
                    kind=GraphEdgeKind.MATCHES_PATH_PATTERN,
                )
            )
    nodes = [
        GraphNode(id=PATTERN_NODE_IDS[pattern], kind=GraphNodeKind.FRAMEWORK_PATTERN)
        for pattern in sorted(matched_patterns)
    ]
    return nodes, edges


def _patterns_for_path(path: str) -> tuple[str, ...]:
    parts = PurePosixPath(path).parts
    matches: list[str] = []
    app_index = 1 if parts[:2] == ("src", "app") else 0
    if parts[app_index : app_index + 1] == ("app",):
        if parts[-1] in {"route.ts", "route.tsx"}:
            matches.append("next_app_route")
        if parts[-1] == "page.tsx":
            matches.append("next_app_page")
    pages_index = 1 if parts[:2] == ("src", "pages") else 0
    if parts[pages_index : pages_index + 2] == ("pages", "api") and parts[-1].endswith(
        (".ts", ".tsx")
    ):
        matches.append("next_pages_api_route")
    if path in {"src/main.tsx", "src/main.jsx"}:
        matches.append("frontend_main_file")
    if path == "main.py":
        matches.append("python_main_file")
    if path == "app.py":
        matches.append("python_app_file")
    return tuple(matches)
