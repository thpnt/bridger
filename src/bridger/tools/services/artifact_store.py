from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from bridger.models.context_plan_bootstrap import ContextPlanBootstrapArtifact
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import RepoContextArtifact
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

    def load_context_plan_bootstrap(self) -> ContextPlanBootstrapArtifact:
        return self._load("context-plan-bootstrap.json", ContextPlanBootstrapArtifact)

    def load_context_plan_working_state(self) -> ContextPlanWorkingState:
        # Inspection state is mutated after every successful tool call.
        # Do not retain a stale cached snapshot between investigation turns.
        self._cache.pop("context-plan-working-state.json", None)
        return self._load("context-plan-working-state.json", ContextPlanWorkingState)

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
