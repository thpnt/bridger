"""Git-backed Layer 1 repository source and intake interfaces."""

from repository.file_index import build_file_index
from repository.reader import read_file
from repository.revisions import compare_revisions
from repository.service import prepare_repository, resolve_repository

__all__ = [
    "build_file_index",
    "compare_revisions",
    "prepare_repository",
    "read_file",
    "resolve_repository",
]
