from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)


def test_file_index_models_accept_valid_minimal_artifact() -> None:
    artifact = FileIndexArtifact(
        generated_at=datetime(2026, 6, 18, tzinfo=UTC),
        repo_root_name="example",
        files=[
            IndexedFile(
                path="src/example.py",
                extension=".py",
                size_bytes=1,
                line_count=1,
                sha256="0" * 64,
                is_binary=False,
                is_symlink=False,
                detected_encoding="utf-8",
            )
        ],
        skipped_files=[SkippedFile(path=".env", skip_reason=SkipReason.SENSITIVE_FILE)],
        stats=FileIndexStats(
            files_seen=2,
            files_included=1,
            files_skipped=1,
            total_included_bytes=1,
        ),
    )

    assert artifact.schema_version == 1
    assert artifact.files[0].path == "src/example.py"


@pytest.mark.parametrize("path", ["/absolute.py", "../outside.py", "src\\file.py"])
def test_file_index_models_reject_non_repository_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        SkippedFile(path=path, skip_reason=SkipReason.READ_ERROR)
