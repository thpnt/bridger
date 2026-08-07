from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field

from paths import ProjectPaths

ProjectMode = Literal["existing", "fresh", "unknown"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectLLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_profile: str = "balanced"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1"
    project_name: str
    project_mode: ProjectMode
    created_at: datetime
    updated_at: datetime
    llm: ProjectLLMConfig = Field(default_factory=ProjectLLMConfig)


def create_project_config(root: Path, mode: ProjectMode) -> ProjectConfig:
    timestamp = utc_now()
    return ProjectConfig(
        project_name=root.name,
        project_mode=mode,
        created_at=timestamp,
        updated_at=timestamp,
    )


def read_project_config(config_file: Path) -> ProjectConfig | None:
    try:
        return ProjectConfig.model_validate_json(config_file.read_bytes())
    except (OSError, ValueError):
        return None


def write_project_config(config_file: Path, config: ProjectConfig) -> None:
    data = config.model_dump(mode="json")
    config_file.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2) + b"\n")


def initialize_project(
    paths: ProjectPaths, fresh: bool
) -> tuple[bool, ProjectConfig | None]:
    already_exists = paths.bridger_dir.exists()
    paths.bridger_dir.mkdir(exist_ok=True)
    for directory in paths.directories:
        directory.mkdir(exist_ok=True)

    existing_config = read_project_config(paths.config_file)
    config: ProjectConfig | None
    if not paths.config_file.exists():
        mode: ProjectMode = "fresh" if fresh else "existing"
        config = create_project_config(paths.root, mode)
        write_project_config(paths.config_file, config)
    elif existing_config is not None and fresh:
        config = existing_config.model_copy(
            update={"project_mode": "fresh", "updated_at": utc_now()}
        )
        write_project_config(paths.config_file, config)
    else:
        config = existing_config

    return already_exists, config
