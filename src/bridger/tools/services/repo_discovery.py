from bridger.models.repo_discovery import RepoDiscoveryArtifact


class RepoDiscoveryService:
    def __init__(self, artifact: RepoDiscoveryArtifact) -> None:
        self.artifact = artifact

    def inspect(self) -> dict[str, object]:
        return {
            "source_artifact": "repo-discovery.json",
            "repo_discovery": self.artifact.model_dump(mode="json"),
        }
