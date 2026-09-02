"""Shared contracts for the Bridger consumption interface."""

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    TypeAdapter,
    model_validator,
)

from bridger.contracts.enrichment import EnrichmentTargetReference
from bridger.contracts.files import FileIndexPath


class Lens(StrEnum):
    UNDERSTAND = "understand"
    GUARDRAILS = "guardrails"
    IMPACT = "impact"


class ScopeKind(StrEnum):
    REPOSITORY = "repository"
    PATH = "path"
    SYMBOL = "symbol"
    GRAPH_ENTITY = "graph_entity"
    BRAIN_REF = "brain_ref"


class BridgerRefKind(StrEnum):
    NODE = "node"
    EDGE = "edge"
    HYPEREDGE = "hyperedge"
    COMMUNITY = "community"
    GRAPH = "graph"
    FILE = "file"
    SYMBOL = "symbol"

    BRAIN_DOCUMENT = "brain_document"
    BRAIN_CONTEXT = "brain_context"
    BRAIN_CLAIM = "brain_claim"
    EVIDENCE = "evidence"


class Substrate(StrEnum):
    BRAIN = "brain"
    DETERMINISTIC_GRAPH = "deterministic_graph"
    GRAPH_ENRICHMENT = "graph_enrichment"
    SOURCE = "source"


class Authority(StrEnum):
    DETERMINISTIC = "deterministic"
    DERIVED = "derived"


class ReadExpansion(StrEnum):
    CONTEXT = "context"
    DOCUMENT = "document"
    CLAIM = "claim"
    EVIDENCE = "evidence"


class ResultOperation(StrEnum):
    QUERY = "query"
    READ = "read"


class BridgerRef(BaseModel):
    """Addressable reference to one exact Bridger intelligence object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: BridgerRefKind
    target_ref: EnrichmentTargetReference
    repository_revision: str = Field(min_length=1)


_FILE_INDEX_PATH_ADAPTER = TypeAdapter(FileIndexPath)

_GRAPH_REF_KINDS = frozenset(
    {
        BridgerRefKind.NODE,
        BridgerRefKind.EDGE,
        BridgerRefKind.HYPEREDGE,
        BridgerRefKind.COMMUNITY,
        BridgerRefKind.GRAPH,
    }
)

_BRAIN_REF_KINDS = frozenset(
    {
        BridgerRefKind.BRAIN_DOCUMENT,
        BridgerRefKind.BRAIN_CONTEXT,
        BridgerRefKind.BRAIN_CLAIM,
    }
)


class ScopeRef(BaseModel):
    """Concrete repository or Bridger object constraining retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ScopeKind
    value: BridgerRef | EnrichmentTargetReference | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "ScopeRef":
        if self.kind is ScopeKind.REPOSITORY:
            if self.value is not None:
                raise ValueError("repository scope cannot declare a value")
            return self

        if self.kind is ScopeKind.PATH:
            if not isinstance(self.value, str):
                raise ValueError("path scope requires a FileIndexPath")
            _FILE_INDEX_PATH_ADAPTER.validate_python(self.value)
            return self

        if self.kind is ScopeKind.SYMBOL:
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("symbol scope requires a canonical symbol_id")
            return self

        if self.kind is ScopeKind.GRAPH_ENTITY:
            if isinstance(self.value, BridgerRef):
                if self.value.kind not in _GRAPH_REF_KINDS:
                    raise ValueError("graph_entity scope requires a graph BridgerRef")
                return self

            if self.value is None:
                raise ValueError("graph_entity scope requires a graph target reference")
            return self

        if self.kind is ScopeKind.BRAIN_REF:
            if (
                not isinstance(self.value, BridgerRef)
                or self.value.kind not in _BRAIN_REF_KINDS
            ):
                raise ValueError("brain_ref scope requires a Brain BridgerRef")
            return self

        raise ValueError("unsupported scope kind")


class IntelligenceQueryRequest(BaseModel):
    """Request to locate relevant repository intelligence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lens: Lens
    query: str | None = Field(default=None, min_length=1)
    scope: ScopeRef | None = None
    limit: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "IntelligenceQueryRequest":
        if self.query is not None and not self.query.strip():
            raise ValueError("query must contain non-whitespace content")

        if self.lens in {Lens.UNDERSTAND, Lens.GUARDRAILS}:
            if self.query is None and self.scope is None:
                raise ValueError("UNDERSTAND and GUARDRAILS require query or scope")

        if self.lens is Lens.IMPACT:
            if self.scope is None:
                raise ValueError("IMPACT requires concrete scope")

            if self.scope.kind not in {
                ScopeKind.PATH,
                ScopeKind.SYMBOL,
                ScopeKind.GRAPH_ENTITY,
            }:
                raise ValueError("IMPACT scope must be path, symbol, or graph_entity")

        return self


class IntelligenceReadRequest(BaseModel):
    """Request to inspect or expand an existing Bridger reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: BridgerRef
    expand: ReadExpansion | None = None


class Provenance(BaseModel):
    """Origin and authority metadata for returned intelligence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository_revision: str = Field(min_length=1)
    substrate: Substrate
    authority: Authority
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: str | None = Field(default=None, min_length=1)


class Completeness(BaseModel):
    """Completeness metadata for one bounded intelligence result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    returned_count: int = Field(ge=0)
    truncated: bool = False
    more_available: bool = False


class IntelligenceItem(BaseModel):
    """One addressable repository-intelligence result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: BridgerRef
    kind: BridgerRefKind

    title: str = Field(min_length=1)
    content: str | None = None

    document_ref: BridgerRef | None = None
    context_ref: BridgerRef | None = None

    matched_claim_refs: list[BridgerRef] = Field(default_factory=list)
    evidence_refs: list[BridgerRef] = Field(default_factory=list)
    related_refs: list[BridgerRef] = Field(default_factory=list)

    semantic_owner: str | None = Field(default=None, min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_item(self) -> "IntelligenceItem":
        if self.kind is not self.ref.kind:
            raise ValueError("item kind must match ref kind")
        return self


class IntelligenceResult(BaseModel):
    """Canonical result envelope for Bridger consumption operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: ResultOperation
    repository_revision: str = Field(min_length=1)

    lens: Lens | None = None
    query: str | None = None
    scope: ScopeRef | None = None

    items: list[IntelligenceItem] = Field(default_factory=list)
    completeness: Completeness

    @model_validator(mode="after")
    def validate_result(self) -> "IntelligenceResult":
        if self.operation is ResultOperation.QUERY and self.lens is None:
            raise ValueError("QUERY result requires lens")

        if self.completeness.returned_count != len(self.items):
            raise ValueError("completeness.returned_count must match items")

        for item in self.items:
            if item.ref.repository_revision != self.repository_revision:
                raise ValueError("item ref revision must match result revision")

            if item.provenance.repository_revision != self.repository_revision:
                raise ValueError("item provenance revision must match result revision")

        return self


__all__ = [
    "Authority",
    "BridgerRef",
    "BridgerRefKind",
    "Completeness",
    "IntelligenceItem",
    "IntelligenceQueryRequest",
    "IntelligenceReadRequest",
    "IntelligenceResult",
    "Lens",
    "Provenance",
    "ReadExpansion",
    "ResultOperation",
    "ScopeKind",
    "ScopeRef",
    "Substrate",
]
