import os
import tempfile
from pathlib import Path
from typing import TypeVar

import orjson
from pydantic import BaseModel

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


def write_artifact(destination: Path, artifact: ArtifactT) -> None:
    validated = type(artifact).model_validate(artifact.model_dump())
    serialized = (
        orjson.dumps(
            validated.model_dump(mode="json", by_alias=True),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
