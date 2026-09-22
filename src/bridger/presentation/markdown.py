"""Deterministic Markdown presentation for Bridger intelligence results."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, TypeGuard

from bridger.contracts._legacy_consumption import (
    BridgerRef,
    BridgerRefKind,
    IntelligenceItem,
    IntelligenceResult,
    ScopeRef,
)

_GRAPH_KINDS = frozenset(
    {
        BridgerRefKind.NODE,
        BridgerRefKind.EDGE,
        BridgerRefKind.HYPEREDGE,
        BridgerRefKind.COMMUNITY,
        BridgerRefKind.GRAPH,
    }
)

_FIELD_LABELS = {
    "deterministic_label": "Label",
    "in_degree": "In degree",
    "out_degree": "Out degree",
    "source_node_id": "Source node",
    "target_node_id": "Target node",
    "source_path": "File",
    "symbol_ids": "Symbols",
    "graph_node_ids": "Graph nodes",
    "members_truncated": "Members truncated",
    "symbols_truncated": "Symbols truncated",
    "graph_nodes_truncated": "Graph nodes truncated",
}


def render_intelligence_markdown(result: IntelligenceResult) -> str:
    """Render an already-complete result without retrieval or interpretation."""
    lines = [
        _result_heading(result),
        "",
        f"Repository revision: {result.repository_revision}",
    ]

    for item in result.items:
        lines.extend(["", *_render_item(item)])

    lines.extend(["", "## Completeness", "", *_render_completeness(result)])
    return "\n".join(lines) + "\n"


def _result_heading(result: IntelligenceResult) -> str:
    if result.operation.value == "read":
        read_descriptor = f" — {result.items[0].title}" if result.items else ""
        return f"# READ{read_descriptor}"

    lens = result.lens.value.upper() if result.lens is not None else "RESULT"
    descriptor: str | None = result.query or _scope_descriptor(result.scope)
    return f"# {lens}{f' — {descriptor}' if descriptor else ''}"


def _scope_descriptor(scope: ScopeRef | None) -> str | None:
    if scope is None:
        return None
    if scope.value is None:
        return scope.kind.value
    if isinstance(scope.value, str):
        return f"{scope.kind.value}: {scope.value}"
    return f"{scope.kind.value}: {_compact_json(scope.value)}"


def _render_item(item: IntelligenceItem) -> list[str]:
    lines = [f"## {item.title}", "", f"**Kind:** {_kind_label(item.kind)}"]
    lines.extend(_optional_metadata(item))

    if item.kind in _GRAPH_KINDS and _is_mapping(item.data):
        lines.extend(_render_graph_data(item.data))
    elif item.kind is BridgerRefKind.FILE and _is_mapping(item.data):
        lines.extend(_render_file_data(item.data))
    else:
        if item.content is not None:
            lines.extend(["", item.content])
        if item.data is not None:
            lines.extend(["", "### Data", "", *_render_value(item.data)])
    return lines


def _optional_metadata(item: IntelligenceItem) -> list[str]:
    lines: list[str] = []
    if item.semantic_owner is not None:
        lines.append(f"**Semantic owner:** {item.semantic_owner}")
    lines.append(f"**Ref:** `{_format_ref(item.ref)}`")

    provenance = item.provenance
    source = f"{_humanize(provenance.substrate.value)} · {provenance.authority.value}"
    lines.append(f"**Source:** {source}")
    if provenance.confidence is not None:
        lines.append(f"**Confidence:** {provenance.confidence}")
    if provenance.uncertainty is not None:
        lines.append(f"**Uncertainty:** {provenance.uncertainty}")

    refs = (
        ("Document", item.document_ref),
        ("Context", item.context_ref),
    )
    for label, ref in refs:
        if ref is not None:
            lines.append(f"**{label}:** `{_format_ref(ref)}`")
    for label, values in (
        ("Matched claims", item.matched_claim_refs),
        ("Evidence", item.evidence_refs),
        ("Related", item.related_refs),
    ):
        if values:
            lines.append(
                f"**{label}:** " + ", ".join(f"`{_format_ref(ref)}`" for ref in values)
            )
    return ["", *lines]


def _render_graph_data(data: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    identity = {key: data[key] for key in ("target_type", "target_ref") if key in data}
    if identity:
        lines.extend(["", "### Graph identity", "", *_render_mapping(identity)])

    deterministic = data.get("deterministic")
    if deterministic is not None:
        lines.extend(["", "### Deterministic graph", "", *_render_value(deterministic)])

    enrichment = data.get("enrichment")
    if enrichment:
        lines.extend(
            ["", "### Enrichment (AI-derived)", "", *_render_value(enrichment)]
        )

    remaining = {
        key: value
        for key, value in data.items()
        if key not in {"target_type", "target_ref", "deterministic", "enrichment"}
        and value is not None
    }
    if remaining:
        lines.extend(["", "### Data", "", *_render_mapping(remaining)])
    return lines


def _render_file_data(data: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    file_metadata = data.get("file")
    if file_metadata is not None:
        lines.extend(["", "### File metadata", "", *_render_value(file_metadata)])

    for key, heading in (
        ("symbol_ids", "Symbols"),
        ("graph_node_ids", "Graph nodes"),
    ):
        value = data.get(key)
        if value:
            lines.extend(["", f"### {heading}", "", *_render_value(value)])

    remaining = {
        key: value
        for key, value in data.items()
        if key not in {"file", "symbol_ids", "graph_node_ids"} and value is not None
    }
    if remaining:
        lines.extend(["", "### Data", "", *_render_mapping(remaining)])
    return lines


def _render_completeness(result: IntelligenceResult) -> list[str]:
    completeness = result.completeness
    lines = [f"{completeness.returned_count} results returned."]
    lines.append(f"Truncated: {_boolean(completeness.truncated)}.")
    lines.append(f"More available: {_boolean(completeness.more_available)}.")
    if completeness.more_available:
        lines.append("Additional relevant information is available.")
    elif not completeness.truncated:
        lines.append("Result is complete within the requested operation.")
    return lines


def _render_value(value: Any, indent: int = 0) -> list[str]:
    if isinstance(value, Mapping):
        return _render_mapping(value, indent)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _render_list(value, indent)
    return [f"{'  ' * indent}- {_scalar_text(value)}"]


def _render_mapping(value: Mapping[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * indent
    for key, nested in value.items():
        if nested is None or nested == [] or nested == {}:
            continue
        label = _field_label(str(key))
        if _is_scalar(nested):
            lines.append(f"{prefix}- {label}: {_scalar_text(nested)}")
            continue
        lines.append(f"{prefix}- {label}:")
        lines.extend(_render_value(nested, indent + 1))
    return lines


def _render_list(value: Sequence[Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * indent
    for entry in value:
        if entry is None:
            continue
        if _is_scalar(entry):
            lines.append(f"{prefix}- {_scalar_text(entry)}")
        else:
            lines.append(f"{prefix}-")
            lines.extend(_render_value(entry, indent + 1))
    return lines


def _format_ref(ref: BridgerRef) -> str:
    target = _compact_json(ref.target_ref)
    return f"{ref.kind.value}:{target}@{ref.repository_revision}"


def _compact_json(value: Any) -> str:
    if isinstance(value, BridgerRef):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _kind_label(kind: BridgerRefKind) -> str:
    return _humanize(kind.value).capitalize()


def _field_label(key: str) -> str:
    return _FIELD_LABELS.get(key, _humanize(key).capitalize())


def _humanize(value: str) -> str:
    return value.replace("_", " ")


def _scalar_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _compact_json(value)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _is_mapping(value: Any) -> TypeGuard[Mapping[str, Any]]:
    return isinstance(value, Mapping)


def _boolean(value: bool) -> str:
    return "yes" if value else "no"


__all__ = ["render_intelligence_markdown"]
