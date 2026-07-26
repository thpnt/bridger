import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from bridger.deterministic.file_index.builder import build_file_index_for_project
from bridger.models.file_index import ReadPolicy, SkipReason


def skipped_paths(repo: Path) -> dict[str, SkipReason]:
    artifact = build_file_index_for_project(repo)
    return {file.path: file.skip_reason for file in artifact.skipped_files}


def indexed_files(repo: Path) -> dict[str, object]:
    artifact = build_file_index_for_project(repo)
    return {file.path: file for file in artifact.files}


def init_git(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)


def test_builder_includes_text_file_with_metadata(tmp_path: Path) -> None:
    content = b"first\nsecond\n"
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_bytes(content)

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == ["src/example.py"]
    indexed = artifact.files[0]
    assert indexed.extension == ".py"
    assert indexed.size_bytes == len(content)
    assert indexed.line_count == 2
    assert indexed.sha256 == sha256(content).hexdigest()
    assert indexed.is_binary is False
    assert indexed.is_symlink is False
    assert indexed.detected_encoding == "utf-8"
    assert artifact.stats.total_included_bytes == len(content)


@pytest.mark.parametrize("directory", [".git", "node_modules"])
def test_builder_retains_ignored_directory_files_as_metadata(
    tmp_path: Path, directory: str
) -> None:
    ignored_file = tmp_path / directory / "nested" / "example.txt"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("not read")

    indexed = indexed_files(tmp_path)[f"{directory}/nested/example.txt"]
    assert indexed.read_policy is ReadPolicy.METADATA_ONLY
    assert indexed.read_policy_reason is SkipReason.IGNORED_DIRECTORY


def test_builder_excludes_bridger_directory(tmp_path: Path) -> None:
    ignored_file = tmp_path / ".bridger" / "nested" / "example.txt"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("not read")

    assert skipped_paths(tmp_path)[".bridger/nested/example.txt"] == (
        SkipReason.BRIDGER_DIRECTORY
    )


@pytest.mark.parametrize("filename", [".env", ".env.local", "secret.pem"])
def test_builder_skips_sensitive_files(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("secret")

    indexed = indexed_files(tmp_path)[filename]
    assert indexed.read_policy is ReadPolicy.METADATA_ONLY
    assert indexed.read_policy_reason is SkipReason.SENSITIVE_FILE


def test_builder_respects_root_gitignore_file_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.generated\ncache/\n")
    (tmp_path / "keep.txt").write_text("keep")
    (tmp_path / "ignored.generated").write_text("ignore")
    (tmp_path / "cache" / "nested.txt").parent.mkdir()
    (tmp_path / "cache" / "nested.txt").write_text("ignore")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == [
        ".gitignore",
        "cache/nested.txt",
        "ignored.generated",
        "keep.txt",
    ]
    assert artifact.files[1].read_policy_reason is SkipReason.GITIGNORED
    assert artifact.files[2].read_policy_reason is SkipReason.GITIGNORED


def test_builder_respects_gitignore_negation(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("generated/\n!generated/keep.txt\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "drop.txt").write_text("drop")
    (tmp_path / "generated" / "keep.txt").write_text("keep")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == [
        ".gitignore",
        "generated/drop.txt",
        "generated/keep.txt",
    ]
    assert artifact.files[1].read_policy_reason is SkipReason.GITIGNORED


def test_builder_skips_binary_file(tmp_path: Path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"text\0binary")

    indexed = indexed_files(tmp_path)["binary.dat"]
    assert indexed.is_binary is True
    assert indexed.read_policy is ReadPolicy.METADATA_ONLY
    assert indexed.read_policy_reason is SkipReason.BINARY_FILE


def test_builder_skips_large_file(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_bytes(b"x" * 11)

    artifact = build_file_index_for_project(tmp_path, max_file_bytes=10)

    assert artifact.files[0].read_policy is ReadPolicy.METADATA_ONLY
    assert artifact.files[0].read_policy_reason is SkipReason.LARGE_FILE


def test_builder_output_is_sorted_and_stats_are_consistent(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z")
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "secret.pem").write_text("secret")
    (tmp_path / ".env").write_text("secret")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == [
        ".env",
        "a.txt",
        "secret.pem",
        "z.txt",
    ]
    assert artifact.skipped_files == []
    assert artifact.stats.files_seen == 4
    assert artifact.stats.files_included == 4
    assert artifact.stats.files_skipped == 0
    assert artifact.stats.files_metadata_only == 2


def test_builder_marks_non_utf8_text_encoding_unknown(tmp_path: Path) -> None:
    (tmp_path / "legacy.txt").write_bytes(b"legacy: \xff")

    artifact = build_file_index_for_project(tmp_path)

    assert artifact.files[0].detected_encoding == "unknown"
    assert artifact.files[0].read_policy is ReadPolicy.METADATA_ONLY


def test_builder_skips_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("target")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")

    indexed = indexed_files(tmp_path)["link.txt"]
    assert indexed.read_policy is ReadPolicy.METADATA_ONLY
    assert indexed.read_policy_reason is SkipReason.SYMLINK_UNSUPPORTED


def test_builder_uses_head_tracked_paths_and_excludes_untracked_files(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitignore").write_text("*.ignored\n")
    (tmp_path / "tracked.py").write_text("tracked = True\n")
    (tmp_path / "tracked.ignored").write_text("tracked = True\n")
    bridger_file = tmp_path / ".bridger" / "state.json"
    bridger_file.parent.mkdir()
    bridger_file.write_text("internal")
    init_git(tmp_path)
    (tmp_path / "untracked.py").write_text("untracked = True\n")
    subprocess.run(
        ["git", "add", "-f", "tracked.ignored", ".bridger"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "tracked ignored file"],
        cwd=tmp_path,
        check=True,
    )

    artifact = build_file_index_for_project(tmp_path)

    assert artifact.revision != "unknown"
    assert [file.path for file in artifact.files] == [
        ".gitignore",
        "tracked.ignored",
        "tracked.py",
    ]
    assert "untracked.py" not in {file.path for file in artifact.files}
    assert artifact.skipped_files == [
        artifact.skipped_files[0]
    ]
    assert artifact.skipped_files[0].path == ".bridger/state.json"
    assert artifact.files[1].read_policy_reason is SkipReason.GITIGNORED
    assert artifact.stats.untracked_files_excluded == 1
