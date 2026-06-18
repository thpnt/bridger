from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.models.repo_context import (
    ConfigFile,
    ConfigKind,
    RepoContextArtifact,
)


def test_repo_context_models_accept_valid_minimal_artifact() -> None:
    artifact = RepoContextArtifact(
        generated_at=datetime(2026, 6, 18, tzinfo=UTC),
        manifests=[],
        config_files=[],
        ci_files=[],
        instruction_files=[],
        docs_files=[],
        parse_errors=[],
    )

    assert artifact.schema_version == 1


@pytest.mark.parametrize("path", ["/tsconfig.json", "../tsconfig.json"])
def test_repo_context_models_reject_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ConfigFile(path=path, kind=ConfigKind.TYPESCRIPT_CONFIG)
