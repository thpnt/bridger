from fnmatch import fnmatch
from pathlib import PurePosixPath

from bridger.models.file_index import SkipReason

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".bridger",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".turbo",
        ".next",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "vendor",
    }
)

SENSITIVE_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "*.sqlite",
    "*.db",
)


def directory_skip_reason(path: PurePosixPath) -> SkipReason | None:
    if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts[:-1]):
        return SkipReason.IGNORED_DIRECTORY
    return None


def file_skip_reason(path: PurePosixPath) -> SkipReason | None:
    if directory_skip_reason(path) is not None:
        return SkipReason.IGNORED_DIRECTORY
    if any(fnmatch(path.name, pattern) for pattern in SENSITIVE_FILE_PATTERNS):
        return SkipReason.SENSITIVE_FILE
    return None
