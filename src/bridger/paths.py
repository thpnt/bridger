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
    def directories(self) -> tuple[Path, ...]:
        return tuple(
            self.bridger_dir / name
            for name in ("memory", "artifacts", "skills", "exports")
        )
