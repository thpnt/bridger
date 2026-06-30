import json
from datetime import UTC, datetime
from pathlib import Path

from bridger.artifacts.writer import write_artifact
from bridger.models.file_index import FileIndexArtifact, FileIndexStats


def test_artifact_writer_atomically_replaces_with_valid_json(tmp_path: Path) -> None:
    destination = tmp_path / ".bridger" / "artifacts" / "file-index.json"
    destination.parent.mkdir(parents=True)
    destination.write_text("old content")
    artifact = FileIndexArtifact(
        generated_at=datetime(2026, 6, 18, tzinfo=UTC),
        repo_root_name="example",
        files=[],
        skipped_files=[],
        stats=FileIndexStats(
            files_seen=0,
            files_included=0,
            files_skipped=0,
            total_included_bytes=0,
        ),
    )

    write_artifact(destination, artifact)

    assert json.loads(destination.read_text())["schema_version"] == 1
    assert destination.read_bytes().endswith(b"\n")
    assert not any(path.name.endswith(".tmp") for path in destination.parent.iterdir())
