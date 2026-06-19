from pydantic import BaseModel, Field


class FileFilters(BaseModel):
    path_prefix: str | None = None
    extension: str | None = None
    limit: int | None = Field(default=None, ge=1)


class GrepFilters(BaseModel):
    path_prefix: str | None = None
    extension: str | None = None
    limit: int | None = Field(default=None, ge=1)
