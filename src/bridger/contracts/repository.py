"""Repository identity contracts."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryContext(BaseModel):
    """Identifies the exact Git repository state used by a Layer 1 operation."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    root_path: Path
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    branch: str | None = Field(default=None, min_length=1)
    scope_path: str = "."

    @field_validator("scope_path")
    @classmethod
    def validate_scope_path(cls, value: str) -> str:
        """Reject scope paths that are not normalized repository-relative paths."""
        if not value or value.startswith("/"):
            raise ValueError("scope_path must be a normalized repository-relative path")
        if value != "." and (
            value.startswith("./")
            or value.endswith("/")
            or "/./" in value
            or "//" in value
            or ".." in value.split("/")
        ):
            raise ValueError(
                "scope_path must be normalized and remain inside the repository"
            )
        return value
