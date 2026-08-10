"""Layer 2 deterministic extraction contracts."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractionFailure(BaseModel):
    """One file that Graphify could not extract successfully."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    error: str = Field(min_length=1)


class ExtractionReport(BaseModel):
    """Completeness report for one revision-bound extraction run."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    attempted_files: int = Field(ge=0)
    successful_files: int = Field(ge=0)
    failed_files: list[ExtractionFailure] = Field(default_factory=list)
    produced_symbols: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "ExtractionReport":
        """Require every attempted file to be classified once."""
        if self.successful_files + len(self.failed_files) != self.attempted_files:
            raise ValueError("attempted files must equal successful plus failed files")
        paths = [failure.path for failure in self.failed_files]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("failed files must have unique, sorted paths")
        return self
