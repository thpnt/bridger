"""Focused validation tests for shared consumption contracts."""

import pytest
from pydantic import ValidationError

from bridger.contracts import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceQueryRequest,
    IntelligenceReadRequest,
    IntelligenceResult,
    Lens,
    Provenance,
    ReadExpansion,
    ResultOperation,
    ScopeKind,
    ScopeRef,
    Substrate,
)

REVISION = "a" * 40


def _ref(kind: BridgerRefKind = BridgerRefKind.NODE) -> BridgerRef:
    return BridgerRef(
        kind=kind,
        target_ref="target-1",
        repository_revision=REVISION,
    )


def _item() -> IntelligenceItem:
    return IntelligenceItem(
        ref=_ref(),
        kind=BridgerRefKind.NODE,
        title="A node",
        provenance=Provenance(
            repository_revision=REVISION,
            substrate=Substrate.DETERMINISTIC_GRAPH,
            authority=Authority.DETERMINISTIC,
        ),
    )


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (Lens, ["understand", "guardrails", "impact"]),
        (ScopeKind, ["repository", "path", "symbol", "graph_entity", "brain_ref"]),
        (
            BridgerRefKind,
            [
                "node",
                "edge",
                "hyperedge",
                "community",
                "graph",
                "file",
                "symbol",
                "brain_document",
                "brain_context",
                "brain_claim",
                "evidence",
            ],
        ),
        (
            Substrate,
            ["brain", "deterministic_graph", "graph_enrichment", "source"],
        ),
        (Authority, ["deterministic", "derived"]),
        (ReadExpansion, ["context", "document", "claim", "evidence"]),
        (ResultOperation, ["query", "read"]),
    ],
)
def test_enum_values_are_stable(enum_type: type, expected: list[str]) -> None:
    assert [member.value for member in enum_type] == expected


def test_scope_accepts_all_supported_values() -> None:
    graph_ref = _ref(BridgerRefKind.COMMUNITY)
    brain_ref = _ref(BridgerRefKind.BRAIN_DOCUMENT)

    assert ScopeRef(kind=ScopeKind.REPOSITORY).value is None
    assert ScopeRef(kind=ScopeKind.PATH, value="src/webhooks/retry.py").value == (
        "src/webhooks/retry.py"
    )
    assert ScopeRef(kind=ScopeKind.SYMBOL, value="canonical-symbol-id")
    assert ScopeRef(
        kind=ScopeKind.GRAPH_ENTITY,
        value={"community_id": 1, "member_signature": "abc"},
    )
    assert ScopeRef(kind=ScopeKind.GRAPH_ENTITY, value=graph_ref)
    assert ScopeRef(kind=ScopeKind.BRAIN_REF, value=brain_ref)


@pytest.mark.parametrize(
    "scope",
    [
        {"kind": ScopeKind.REPOSITORY, "value": "repository"},
        {"kind": ScopeKind.PATH, "value": "./src/retry.py"},
        {"kind": ScopeKind.PATH, "value": "src//retry.py"},
        {"kind": ScopeKind.SYMBOL, "value": "   "},
        {"kind": ScopeKind.GRAPH_ENTITY},
        {"kind": ScopeKind.GRAPH_ENTITY, "value": _ref(BridgerRefKind.BRAIN_CLAIM)},
        {"kind": ScopeKind.BRAIN_REF, "value": _ref(BridgerRefKind.NODE)},
    ],
)
def test_scope_rejects_invalid_values(scope: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScopeRef.model_validate(scope)


def test_query_requests_enforce_lens_rules() -> None:
    path_scope = ScopeRef(kind=ScopeKind.PATH, value="src/retry.py")
    symbol_scope = ScopeRef(kind=ScopeKind.SYMBOL, value="symbol-id")
    graph_scope = ScopeRef(
        kind=ScopeKind.GRAPH_ENTITY,
        value={"node_id": "node-1"},
    )

    assert IntelligenceQueryRequest(lens=Lens.UNDERSTAND, query="retry behavior")
    assert IntelligenceQueryRequest(lens=Lens.UNDERSTAND, scope=path_scope)
    assert IntelligenceQueryRequest(lens=Lens.GUARDRAILS, query="security")
    assert IntelligenceQueryRequest(lens=Lens.GUARDRAILS, scope=path_scope)
    assert IntelligenceQueryRequest(lens=Lens.IMPACT, scope=path_scope)
    assert IntelligenceQueryRequest(lens=Lens.IMPACT, scope=symbol_scope)
    assert IntelligenceQueryRequest(
        lens=Lens.IMPACT,
        query="what depends on this?",
        scope=graph_scope,
    )

    invalid_requests = [
        {"lens": Lens.UNDERSTAND},
        {"lens": Lens.GUARDRAILS},
        {"lens": Lens.IMPACT},
        {
            "lens": Lens.IMPACT,
            "scope": ScopeRef(kind=ScopeKind.REPOSITORY),
        },
        {
            "lens": Lens.IMPACT,
            "scope": ScopeRef(
                kind=ScopeKind.BRAIN_REF,
                value=_ref(BridgerRefKind.BRAIN_CONTEXT),
            ),
        },
        {"lens": Lens.UNDERSTAND, "query": "   "},
    ]
    for request in invalid_requests:
        with pytest.raises(ValidationError):
            IntelligenceQueryRequest.model_validate(request)


def test_read_request_is_revision_bound_and_supports_one_expansion() -> None:
    request = IntelligenceReadRequest(ref=_ref(), expand=ReadExpansion.EVIDENCE)

    assert request.expand is ReadExpansion.EVIDENCE
    with pytest.raises(ValidationError):
        IntelligenceReadRequest(ref=_ref(), unexpected=True)


def test_references_are_frozen_and_require_revision() -> None:
    reference = _ref()

    with pytest.raises(ValidationError):
        reference.repository_revision = "b" * 40
    with pytest.raises(ValidationError):
        BridgerRef(kind=BridgerRefKind.NODE, target_ref="target-1")


def test_result_validates_items_completeness_and_revisions() -> None:
    item = _item()
    invalid_item = item.model_dump()
    invalid_item["kind"] = BridgerRefKind.EDGE
    result = IntelligenceResult(
        operation=ResultOperation.QUERY,
        repository_revision=REVISION,
        lens=Lens.UNDERSTAND,
        items=[item],
        completeness=Completeness(returned_count=1),
    )
    assert result.items == [item]

    invalid_results = [
        {
            "operation": ResultOperation.QUERY,
            "repository_revision": REVISION,
            "items": [item],
            "completeness": {"returned_count": 1},
        },
        {
            "operation": ResultOperation.READ,
            "repository_revision": REVISION,
            "lens": Lens.UNDERSTAND,
            "items": [item],
            "completeness": {"returned_count": 0},
        },
        {
            "operation": ResultOperation.READ,
            "repository_revision": "b" * 40,
            "items": [item],
            "completeness": {"returned_count": 1},
        },
        {
            "operation": ResultOperation.READ,
            "repository_revision": REVISION,
            "items": [invalid_item],
            "completeness": {"returned_count": 1},
        },
    ]
    for result_data in invalid_results:
        with pytest.raises(ValidationError):
            IntelligenceResult.model_validate(result_data)

    mismatched_provenance = item.model_copy(
        update={
            "provenance": item.provenance.model_copy(
                update={"repository_revision": "b" * 40}
            )
        }
    )
    with pytest.raises(ValidationError):
        IntelligenceResult(
            operation=ResultOperation.READ,
            repository_revision=REVISION,
            items=[mismatched_provenance],
            completeness=Completeness(returned_count=1),
        )
