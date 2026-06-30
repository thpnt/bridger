from bridger.models.repo_context import RepoContextArtifact
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.path_safety import PathSafetyService


class RepoContextService:
    def __init__(
        self,
        artifact: RepoContextArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets

    def inspect_manifest(self, path: str) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        manifest = next(
            (item for item in self.artifact.manifests if item.path == normalized), None
        )
        if manifest is None:
            raise BridgerToolError(
                "manifest_not_found", f"No parsed manifest exists for: {normalized}"
            )
        return {
            "source_artifact": "repo-context.json",
            "manifest": manifest.model_dump(mode="json"),
        }

    def list_config_files(self) -> dict[str, object]:
        return self._list("config_files")

    def list_docs_files(self) -> dict[str, object]:
        return self._list("docs_files")

    def list_instruction_files(self) -> dict[str, object]:
        return self._list("instruction_files")

    def list_ci_files(self) -> dict[str, object]:
        return self._list("ci_files")

    def _list(self, field: str) -> dict[str, object]:
        items = getattr(self.artifact, field)
        valid = [
            item.model_dump(mode="json")
            for item in items
            if item.path in self.paths.safe_paths
        ]
        valid.sort(key=lambda item: str(item["path"]))
        limit = self.budgets.file_limit()
        return {
            "source_artifact": "repo-context.json",
            field: valid[:limit],
            "total_matches": len(valid),
            "limit_applied": limit,
            "truncated": len(valid) > limit,
        }
