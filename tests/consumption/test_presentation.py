"""Focused tests for the stateless Bridger presentation layer."""

from bridger.contracts._legacy_consumption import (
    Authority,
    BridgerRef,
    BridgerRefKind,
    Completeness,
    IntelligenceItem,
    IntelligenceResult,
    Lens,
    Provenance,
    ResultOperation,
    ScopeKind,
    ScopeRef,
    Substrate,
)
from bridger.presentation import (
    render_intelligence_json,
    render_intelligence_markdown,
)

REVISION = "a" * 40


def _ref(kind: BridgerRefKind, target: object) -> BridgerRef:
    return BridgerRef(
        kind=kind,
        target_ref=target,  # type: ignore[arg-type]
        repository_revision=REVISION,
    )


def _item(
    kind: BridgerRefKind,
    target: object,
    *,
    title: str,
    content: str | None = None,
    data: object = None,
    **kwargs: object,
) -> IntelligenceItem:
    return IntelligenceItem(
        ref=_ref(kind, target),
        kind=kind,
        title=title,
        content=content,
        data=data,  # type: ignore[arg-type]
        provenance=Provenance(
            repository_revision=REVISION,
            substrate=kwargs.pop("substrate", Substrate.SOURCE),  # type: ignore[arg-type]
            authority=kwargs.pop("authority", Authority.DETERMINISTIC),  # type: ignore[arg-type]
            confidence=kwargs.pop("confidence", None),  # type: ignore[arg-type]
            uncertainty=kwargs.pop("uncertainty", None),  # type: ignore[arg-type]
        ),
        **kwargs,  # type: ignore[arg-type]
    )


def _result(
    items: list[IntelligenceItem],
    *,
    operation: ResultOperation = ResultOperation.QUERY,
    lens: Lens | None = Lens.UNDERSTAND,
    query: str | None = "retry lifecycle",
    completeness: Completeness | None = None,
    scope: ScopeRef | None = None,
) -> IntelligenceResult:
    return IntelligenceResult(
        operation=operation,
        repository_revision=REVISION,
        lens=lens,
        query=query,
        scope=scope,
        items=items,
        completeness=completeness or Completeness(returned_count=len(items)),
    )


def test_json_is_the_canonical_result_dump() -> None:
    document_ref = _ref(BridgerRefKind.BRAIN_DOCUMENT, {"document_id": "doc-1"})
    item = _item(
        BridgerRefKind.BRAIN_CONTEXT,
        {"document_id": "doc-1", "start_line": 2, "end_line": 4},
        title="Retry lifecycle",
        content="Brain wording stays exactly here.",
        substrate=Substrate.BRAIN,
        authority=Authority.DERIVED,
        document_ref=document_ref,
        related_refs=[_ref(BridgerRefKind.NODE, "retry-node")],
    )
    result = _result(
        [item],
        completeness=Completeness(
            returned_count=1,
            truncated=True,
            more_available=True,
        ),
    )

    rendered = render_intelligence_json(result)

    assert rendered == result.model_dump(mode="json")
    assert rendered["items"][0]["content"] == "Brain wording stays exactly here."
    assert rendered["items"][0]["data"] is None
    assert rendered["items"][0]["related_refs"][0]["target_ref"] == "retry-node"
    assert rendered["items"][0]["provenance"]["substrate"] == "brain"
    assert rendered["completeness"] == {
        "returned_count": 1,
        "truncated": True,
        "more_available": True,
    }


def test_json_keeps_repository_data_structured() -> None:
    data = {
        "target_type": "node",
        "target_ref": "retry-node",
        "deterministic": {"in_degree": 3, "attributes": {"label": "Retry"}},
        "enrichment": [{"annotation_type": "name", "value": "Scheduler"}],
    }
    result = _result(
        [
            _item(
                BridgerRefKind.NODE,
                "retry-node",
                title="Retry",
                data=data,
                substrate=Substrate.DETERMINISTIC_GRAPH,
            )
        ]
    )

    rendered = render_intelligence_json(result)

    assert rendered["items"][0]["data"] == data
    assert isinstance(rendered["items"][0]["data"], dict)


def test_markdown_renders_brain_content_metadata_and_refs_without_rewriting() -> None:
    content = "The retry worker waits before replaying a failed webhook."
    item = _item(
        BridgerRefKind.BRAIN_CONTEXT,
        {"document_id": "doc-1", "start_line": 2, "end_line": 3},
        title="Webhook retry lifecycle",
        content=content,
        substrate=Substrate.BRAIN,
        authority=Authority.DERIVED,
        semantic_owner="business-logic",
        document_ref=_ref(BridgerRefKind.BRAIN_DOCUMENT, {"document_id": "doc-1"}),
        context_ref=_ref(
            BridgerRefKind.BRAIN_CONTEXT,
            {"document_id": "doc-1", "start_line": 2, "end_line": 3},
        ),
        uncertainty="The source does not define the maximum retry count.",
    )

    rendered = render_intelligence_markdown(_result([item]))

    assert "# UNDERSTAND — retry lifecycle" in rendered
    assert content in rendered
    assert "**Semantic owner:** business-logic" in rendered
    assert "**Source:** brain · derived" in rendered
    assert (
        "**Uncertainty:** The source does not define the maximum retry count."
        in rendered
    )
    assert "doc-1" in rendered
    assert "brain_context" in rendered


def test_markdown_separates_deterministic_graph_facts_from_enrichment() -> None:
    item = _item(
        BridgerRefKind.NODE,
        "retry-node",
        title="RetryScheduler",
        data={
            "target_type": "node",
            "target_ref": "retry-node",
            "deterministic": {
                "attributes": {"label": "RetryScheduler", "path": "retry.py"},
                "in_degree": 3,
                "out_degree": 5,
                "community_id": 2,
            },
            "enrichment": [
                {
                    "enrichment_id": "enrichment-1",
                    "annotation_type": "name",
                    "value": "background-processing",
                    "confidence": 0.8,
                }
            ],
        },
        substrate=Substrate.DETERMINISTIC_GRAPH,
    )

    rendered = render_intelligence_markdown(_result([item]))

    deterministic_at = rendered.index("### Deterministic graph")
    enrichment_at = rendered.index("### Enrichment (AI-derived)")
    assert deterministic_at < enrichment_at
    assert "In degree: 3" in rendered
    assert "Out degree: 5" in rendered
    assert "background-processing" in rendered
    assert "AI-derived" in rendered


def test_markdown_renders_file_and_symbol_items_in_input_order() -> None:
    file_item = _item(
        BridgerRefKind.FILE,
        "src/webhooks/retry.py",
        title="src/webhooks/retry.py",
        data={
            "file": {"path": "src/webhooks/retry.py", "size_bytes": 128},
            "symbol_ids": ["RetryScheduler.schedule"],
            "graph_node_ids": ["retry-node"],
            "symbols_truncated": True,
            "graph_nodes_truncated": False,
        },
    )
    symbol_content = "def schedule():\n    return retry()\n"
    symbol_item = _item(
        BridgerRefKind.SYMBOL,
        "RetryScheduler.schedule",
        title="RetryScheduler.schedule",
        content=symbol_content,
        data={"path": "src/webhooks/retry.py", "truncated": True},
        related_refs=[_ref(BridgerRefKind.NODE, "retry-node")],
    )

    rendered = render_intelligence_markdown(_result([file_item, symbol_item]))

    assert rendered.index("## src/webhooks/retry.py") < rendered.index(
        "## RetryScheduler.schedule"
    )
    assert "### Symbols" in rendered
    assert "RetryScheduler.schedule" in rendered
    assert "### Graph nodes" in rendered
    assert "symbols truncated: true" in rendered.lower()
    assert symbol_content in rendered
    assert "retry-node" in rendered


def test_markdown_supports_read_results_and_scope_descriptors() -> None:
    item = _item(
        BridgerRefKind.SYMBOL,
        "RetryScheduler.schedule",
        title="RetryScheduler.schedule",
        content="def schedule(): pass\n",
    )

    read = render_intelligence_markdown(
        _result(
            [item],
            operation=ResultOperation.READ,
            lens=None,
            query=None,
        )
    )
    scoped = render_intelligence_markdown(
        _result(
            [item],
            query=None,
            scope=ScopeRef(kind=ScopeKind.PATH, value="src/webhooks/retry.py"),
        )
    )

    assert "# READ — RetryScheduler.schedule" in read
    assert "# UNDERSTAND — path: src/webhooks/retry.py" in scoped
    assert "## Completeness" in read


def test_markdown_completeness_generic_fallback_and_determinism() -> None:
    item = _item(
        BridgerRefKind.BRAIN_DOCUMENT,
        {"document_id": "doc-1"},
        title="Unknown structured payload",
        data={
            "custom": {"nested": ["first", {"second": True}]},
            "zero": 0,
            "disabled": False,
            "omitted": None,
        },
        confidence=0.4,
    )
    result = _result(
        [item],
        completeness=Completeness(
            returned_count=1,
            truncated=True,
            more_available=True,
        ),
    )

    first = render_intelligence_markdown(result)
    second = render_intelligence_markdown(result)

    assert first == second
    assert "- Custom:" in first
    assert "- Nested:" in first
    assert "- Second: true" in first
    assert "- Zero: 0" in first
    assert "- Disabled: false" in first
    assert "omitted" not in first
    assert "1 results returned." in first
    assert "Truncated: yes." in first
    assert "More available: yes." in first
    assert "Additional relevant information is available." in first
