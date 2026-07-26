from hashlib import sha256
from pathlib import Path, PurePosixPath

from bridger.models.file_index import ContentType, IndexedFile

BINARY_CHECK_BYTES = 8192


def has_binary_marker(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" in file.read(BINARY_CHECK_BYTES)


def collect_file_metadata(path: Path, relative_path: PurePosixPath) -> IndexedFile:
    content = path.read_bytes()
    is_binary = b"\0" in content[:BINARY_CHECK_BYTES]
    try:
        content.decode("utf-8")
        detected_encoding = "utf-8"
    except UnicodeDecodeError:
        detected_encoding = "unknown"

    content_type = (
        ContentType.BINARY
        if is_binary
        else ContentType.TEXT
        if detected_encoding == "utf-8"
        else ContentType.UNKNOWN
    )

    return IndexedFile(
        path=relative_path.as_posix(),
        extension=path.suffix,
        size_bytes=len(content),
        line_count=len(content.splitlines()),
        sha256=sha256(content).hexdigest(),
        is_binary=is_binary,
        is_symlink=False,
        detected_encoding=detected_encoding,
        content_type=content_type,
    )
