from pathlib import PurePosixPath
from typing import Annotated

from pydantic import StringConstraints

RepositoryPath = Annotated[str, StringConstraints(min_length=1)]


def validate_repository_path(path: str) -> str:
    parsed_path = PurePosixPath(path)
    if parsed_path.is_absolute() or ".." in parsed_path.parts:
        raise ValueError("path must stay within the repository")
    if "\\" in path or path != parsed_path.as_posix():
        raise ValueError("path must be a repository-relative POSIX path")
    return path
