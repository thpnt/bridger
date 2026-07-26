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
        entries = self._declarations(normalized, manifest.parsed)
        return {
            "source_artifact": "repo-context.json",
            "manifest": manifest.model_dump(mode="json"),
            "declarations": entries,
        }

    def _declarations(
        self, path: str, parsed: dict[str, object]
    ) -> list[dict[str, object]]:
        """Attach only literal manifest declarations, never inferred entrypoints."""
        try:
            lines = self.paths.resolve_for_read(path).read_text().splitlines()
        except (BridgerToolError, OSError, UnicodeError):
            return []
        entries: list[dict[str, object]] = []
        for key, value in sorted(parsed.items()):
            line_number = next(
                (
                    index
                    for index, line in enumerate(lines, start=1)
                    if key.replace("_", "-") in line or f'"{key}"' in line
                ),
                None,
            )
            if line_number is None:
                continue
            raw_value = lines[line_number - 1].strip()
            entry: dict[str, object] = {
                "name": key,
                "source_path": path,
                "source_range": {
                    "start_line": line_number,
                    "end_line": line_number,
                },
                "raw_value": raw_value,
                "value": value,
            }
            if key in {"bin", "main", "module", "scripts", "entry_points"}:
                entry["declaration_type"] = "explicit"
            entries.append(entry)
        return entries

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
