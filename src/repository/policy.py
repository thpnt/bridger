"""Deterministic Layer 1 content classification and disposition policy."""

from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from models.files import ContentType, FileDisposition, IntakeConfiguration, ReadMode

LANGUAGES_BY_EXTENSION = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
}
DOCUMENTATION_EXTENSIONS = {".adoc", ".md", ".rst", ".txt"}
CONFIGURATION_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
BINARY_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".bin",
    ".class",
    ".dll",
    ".doc",
    ".docx",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".ttf",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".xz",
    ".zip",
}
CONFIGURATION_FILENAMES = {
    ".gitignore",
    "dockerfile",
    "makefile",
    "package-lock.json",
    "pyproject.toml",
}


def classify_file(
    path: str,
    *,
    is_regular_file: bool,
) -> tuple[ContentType, str | None]:
    """Return a coarse operational content type and optional language."""
    if not is_regular_file:
        return "unknown", None

    file_path = PurePosixPath(path)
    suffix = file_path.suffix.lower()
    filename = file_path.name.lower()
    language = LANGUAGES_BY_EXTENSION.get(suffix)
    if language is not None and suffix != ".toml":
        return "source", language
    if suffix in DOCUMENTATION_EXTENSIONS:
        return "documentation", None
    if suffix in CONFIGURATION_EXTENSIONS or filename in CONFIGURATION_FILENAMES:
        return "configuration", language
    if suffix in BINARY_EXTENSIONS:
        return "binary", None
    return "unknown", None


def determine_disposition(
    *,
    path: str,
    size_bytes: int,
    content_type: str,
    is_regular_file: bool,
    configuration: IntakeConfiguration,
) -> FileDisposition:
    """Assign exactly one centralized access and processing disposition."""
    normal_read_mode: ReadMode = (
        "bounded" if size_bytes > configuration.max_full_read_bytes else "full"
    )
    is_binary_or_non_regular = content_type == "binary" or not is_regular_file

    if path == ".bridger" or path.startswith(".bridger/"):
        return FileDisposition(
            read_mode="denied" if is_binary_or_non_regular else normal_read_mode,
            processing_mode="skip",
            reason="bridger_internal",
        )
    if _matches(path, configuration.sensitive_path_patterns):
        return FileDisposition(
            read_mode="denied",
            processing_mode="skip",
            reason="sensitive_file",
        )
    if _matches(path, configuration.excluded_path_patterns):
        return FileDisposition(
            read_mode="denied",
            processing_mode="skip",
            reason="excluded_by_policy",
        )
    if _matches(path, configuration.generated_path_patterns):
        return FileDisposition(
            read_mode="denied" if is_binary_or_non_regular else normal_read_mode,
            processing_mode="skip",
            reason="generated_file",
        )
    if is_binary_or_non_regular:
        return FileDisposition(
            read_mode="denied",
            processing_mode="skip",
            reason="unsupported_type",
        )
    if size_bytes > configuration.max_full_read_bytes:
        return FileDisposition(
            read_mode="bounded",
            processing_mode="metadata_only",
            reason="file_too_large",
        )
    if content_type == "source":
        return FileDisposition(read_mode="full", processing_mode="extract")
    return FileDisposition(
        read_mode="full",
        processing_mode="metadata_only",
        reason="unsupported_type",
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)
