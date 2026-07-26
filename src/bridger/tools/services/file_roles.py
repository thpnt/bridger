"""Mechanical file role classification shared by repository discovery tools."""

from __future__ import annotations

from pathlib import PurePosixPath

from bridger.deterministic.repo_context.detectors import detect_file_kind
from bridger.models.repo_context import (
    CiKind,
    ConfigKind,
    DocsKind,
    InstructionKind,
    ManifestKind,
)


def classify_file_roles(path: str) -> list[str]:
    kind = detect_file_kind(path)
    roles: set[str] = set()
    if isinstance(kind, ManifestKind):
        roles.add("manifest")
    if isinstance(kind, DocsKind):
        roles.add("documentation")
    if isinstance(kind, InstructionKind):
        roles.update({"instruction", "documentation"})
    if isinstance(kind, ConfigKind):
        roles.add("configuration")
    if isinstance(kind, CiKind):
        roles.update({"ci", "configuration"})

    name = PurePosixPath(path).name.casefold()
    parts = {part.casefold() for part in PurePosixPath(path).parts}
    suffix = PurePosixPath(path).suffix.casefold()
    if (
        "test" in parts
        or "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        roles.update({"test", "source"})
    if suffix in {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".php",
        ".rs",
        ".java",
        ".rb",
        ".cs",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".swift",
        ".kt",
    }:
        roles.add("source")
    return sorted(roles)
