"""Git-backed Layer 1 repository source and intake interfaces."""

from bridger.repository.file_index import build_file_index
from bridger.repository.reader import read_file
from bridger.repository.revisions import compare_revisions
from bridger.repository.service import prepare_repository, resolve_repository

__all__ = [
    "build_file_index",
    "compare_revisions",
    "prepare_repository",
    "read_file",
    "resolve_repository",
]
