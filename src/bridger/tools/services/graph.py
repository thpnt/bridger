from bridger.models.repo_graph import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    RepoGraphArtifact,
)
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.path_safety import PathSafetyService


class GraphService:
    def __init__(
        self,
        artifact: RepoGraphArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets
        self._nodes = {item.id: item for item in artifact.nodes}

    def imports(self, path: str) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        return self._edge_paths(normalized, reverse=False)

    def reverse_imports(self, path: str) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        return self._edge_paths(normalized, reverse=True)

    def neighbors(self, path: str) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        node_id = f"file:{normalized}"
        matches: list[dict[str, object]] = []
        for edge in self.artifact.edges:
            if edge.from_id == node_id:
                matches.append(self._neighbor(edge, edge.to_id, "outgoing"))
            elif edge.to_id == node_id:
                matches.append(self._neighbor(edge, edge.from_id, "incoming"))
        matches.sort(key=lambda item: (str(item["kind"]), str(item["node_id"])))
        limit = self.budgets.graph_limit()
        return {
            "source_artifact": "repo-graph.json",
            "path": normalized,
            "neighbors": matches[:limit],
            "total_matches": len(matches),
            "limit_applied": limit,
            "truncated": len(matches) > limit,
        }

    def declared_entrypoints(self) -> dict[str, object]:
        results: list[dict[str, object]] = []
        for edge in self.artifact.edges:
            if edge.kind is not GraphEdgeKind.DECLARES_ENTRYPOINT:
                continue
            source = self._nodes[edge.from_id]
            target = self._nodes[edge.to_id]
            if target.path is None:
                continue
            self.paths.validate_file(target.path)
            results.append(
                {
                    "path": target.path,
                    "source_path": source.path,
                    "source_key": source.key,
                }
            )
        results.sort(key=lambda item: (str(item["path"]), str(item["source_key"])))
        limit = self.budgets.graph_limit()
        return {
            "source_artifact": "repo-graph.json",
            "entrypoints": results[:limit],
            "total_matches": len(results),
            "limit_applied": limit,
            "truncated": len(results) > limit,
        }

    def _edge_paths(self, path: str, *, reverse: bool) -> dict[str, object]:
        node_id = f"file:{path}"
        matches: list[dict[str, object]] = []
        for edge in self.artifact.edges:
            if edge.kind is not GraphEdgeKind.IMPORTS:
                continue
            selected = edge.from_id if reverse else edge.to_id
            if (edge.to_id if reverse else edge.from_id) != node_id:
                continue
            node = self._nodes[selected]
            if node.path is None:
                continue
            self.paths.validate_file(node.path)
            matches.append({"path": node.path, "import_text": edge.import_text})
        matches.sort(key=lambda item: str(item["path"]))
        limit = self.budgets.graph_limit()
        key = "imported_by" if reverse else "imports"
        return {
            "source_artifact": "repo-graph.json",
            "path": path,
            key: matches[:limit],
            "total_matches": len(matches),
            "limit_applied": limit,
            "truncated": len(matches) > limit,
        }

    def _neighbor(
        self, edge: GraphEdge, other_id: str, direction: str
    ) -> dict[str, object]:
        node: GraphNode = self._nodes[other_id]
        result: dict[str, object] = {
            "node_id": other_id,
            "node_kind": node.kind.value,
            "kind": edge.kind.value,
            "direction": direction,
        }
        if node.path is not None:
            result["path"] = self.paths.validate_file(node.path)
        if node.kind is GraphNodeKind.SYMBOL:
            result["symbol_id"] = node.symbol_id
        if edge.import_text is not None:
            result["import_text"] = edge.import_text
        return result
