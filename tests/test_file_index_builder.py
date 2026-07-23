from hashlib import sha256
from pathlib import Path

import pytest

from bridger.deterministic.file_index.builder import build_file_index_for_project
from bridger.models.file_index import SkipReason


def skipped_paths(repo: Path) -> dict[str, SkipReason]:
    artifact = build_file_index_for_project(repo)
    return {file.path: file.skip_reason for file in artifact.skipped_files}


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


@pytest.mark.parametrize("directory", [".bridger", ".git", "node_modules"])
def test_builder_skips_ignored_directories(tmp_path: Path, directory: str) -> None:
    ignored_file = tmp_path / directory / "nested" / "example.txt"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("not read")

    assert (
        skipped_paths(tmp_path)[f"{directory}/nested/example.txt"]
        == SkipReason.IGNORED_DIRECTORY
    )


@pytest.mark.parametrize("filename", [".env", ".env.local", "secret.pem"])
def test_builder_skips_sensitive_files(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("secret")

    assert skipped_paths(tmp_path)[filename] == SkipReason.SENSITIVE_FILE


def test_builder_respects_root_gitignore_file_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.generated\ncache/\n")
    (tmp_path / "keep.txt").write_text("keep")
    (tmp_path / "ignored.generated").write_text("ignore")
    (tmp_path / "cache" / "nested.txt").parent.mkdir()
    (tmp_path / "cache" / "nested.txt").write_text("ignore")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == [".gitignore", "keep.txt"]
    assert {
        file.path: file.skip_reason for file in artifact.skipped_files
    } == {
        "cache/nested.txt": SkipReason.GITIGNORED,
        "ignored.generated": SkipReason.GITIGNORED,
    }


def test_builder_respects_gitignore_negation(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("generated/\n!generated/keep.txt\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "drop.txt").write_text("drop")
    (tmp_path / "generated" / "keep.txt").write_text("keep")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == [
        ".gitignore",
        "generated/keep.txt",
    ]
    assert {
        file.path: file.skip_reason for file in artifact.skipped_files
    } == {"generated/drop.txt": SkipReason.GITIGNORED}


def test_builder_skips_binary_file(tmp_path: Path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"text\0binary")

    assert skipped_paths(tmp_path)["binary.dat"] == SkipReason.BINARY_FILE


def test_builder_skips_large_file(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_bytes(b"x" * 11)

    artifact = build_file_index_for_project(tmp_path, max_file_bytes=10)

    assert artifact.skipped_files[0].skip_reason == SkipReason.LARGE_FILE


def test_builder_output_is_sorted_and_stats_are_consistent(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z")
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "secret.pem").write_text("secret")
    (tmp_path / ".env").write_text("secret")

    artifact = build_file_index_for_project(tmp_path)

    assert [file.path for file in artifact.files] == ["a.txt", "z.txt"]
    assert [file.path for file in artifact.skipped_files] == [".env", "secret.pem"]
    assert artifact.stats.files_seen == 4
    assert artifact.stats.files_included == 2
    assert artifact.stats.files_skipped == 2


def test_builder_marks_non_utf8_text_encoding_unknown(tmp_path: Path) -> None:
    (tmp_path / "legacy.txt").write_bytes(b"legacy: \xff")

    artifact = build_file_index_for_project(tmp_path)

    assert artifact.files[0].detected_encoding == "unknown"


def test_builder_skips_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("target")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")

    assert skipped_paths(tmp_path)["link.txt"] == SkipReason.SYMLINK_UNSUPPORTED
