from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @classmethod
    def from_cwd(cls) -> "ProjectPaths":
        return cls(root=Path.cwd())

    @property
    def bridger_dir(self) -> Path:
        return self.root / ".bridger"

    @property
    def config_file(self) -> Path:
        return self.bridger_dir / "config.json"

    @property
    def file_index_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "file-index.json"

    @property
    def repo_context_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "repo-context.json"

    @property
    def symbol_index_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "symbol-index.json"

    @property
    def context_plan_bootstrap_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "context-plan-bootstrap.json"

    @property
    def context_plan_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "context-plan.json"

    @property
    def context_plan_run_artifact(self) -> Path:
        return self.bridger_dir / "artifacts" / "context-plan-run.json"

    @property
    def directories(self) -> tuple[Path, ...]:
        return tuple(
            self.bridger_dir / name
            for name in ("memory", "artifacts", "skills", "exports")
        )
