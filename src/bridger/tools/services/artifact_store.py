from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from bridger.models.file_index import FileIndexArtifact
from bridger.models.graph_summary import GraphSummaryArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.repo_discovery import RepoDiscoveryArtifact
from bridger.models.repo_graph import RepoGraphArtifact
from bridger.models.symbol_index import SymbolIndexArtifact
from bridger.models.working_state import ContextPlanWorkingState
from bridger.tools.errors import BridgerToolError

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


class ArtifactStore:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.artifact_dir = self.repo_root / ".bridger" / "artifacts"
        self._cache: dict[str, BaseModel] = {}

    def load_file_index(self) -> FileIndexArtifact:
        return self._load("file-index.json", FileIndexArtifact)

    def load_repo_context(self) -> RepoContextArtifact:
        return self._load("repo-context.json", RepoContextArtifact)

    def load_symbol_index(self) -> SymbolIndexArtifact:
        return self._load("symbol-index.json", SymbolIndexArtifact)

    def load_repo_graph(self) -> RepoGraphArtifact:
        return self._load("repo-graph.json", RepoGraphArtifact)

    def load_graph_summary(self) -> GraphSummaryArtifact:
        return self._load("graph-summary.json", GraphSummaryArtifact)

    def load_repo_discovery(self) -> RepoDiscoveryArtifact:
        return self._load("repo-discovery.json", RepoDiscoveryArtifact)

    def load_context_plan_working_state(self) -> ContextPlanWorkingState:
        return self._load(
            "context-plan-working-state.json",
            ContextPlanWorkingState,
        )

    def _load(self, name: str, model: type[ArtifactT]) -> ArtifactT:
        cached = self._cache.get(name)
        if cached is not None:
            return model.model_validate(cached)
        path = self.artifact_dir / name
        if not path.is_file():
            raise BridgerToolError(
                "artifact_missing", f"Required artifact is missing: {name}"
            )
        try:
            artifact = model.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError) as error:
            raise BridgerToolError(
                "artifact_invalid", f"Required artifact is invalid: {name}"
            ) from error
        self._cache[name] = artifact
        return artifact
