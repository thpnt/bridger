from bridger.models.graph_summary import GraphSummaryArtifact


class GraphSummaryService:
    def __init__(self, artifact: GraphSummaryArtifact) -> None:
        self.artifact = artifact

    def inspect(self) -> dict[str, object]:
        return {
            "source_artifact": "graph-summary.json",
            "summary": self.artifact.model_dump(mode="json"),
        }
