"""Deterministic Markdown presentation for canonical consumption results."""

from __future__ import annotations

import json

from pydantic import BaseModel

from bridger.contracts.consumption import ImpactResult, UnderstandResult


def render_intelligence_markdown(
    result: UnderstandResult | ImpactResult,
) -> str:
    """Render canonical result fields without changing or interpreting them."""
    if isinstance(result, UnderstandResult):
        sections = [
            ("Brain context", result.brain_context),
            ("Graph context", result.graph_context),
        ]
        heading = f"# UNDERSTAND — {result.query}"
    else:
        sections = [
            ("Requested symbols", result.requested_symbols),
            ("Resolved roots", result.resolved_roots),
            ("Resolution issues", result.resolution_issues),
            ("Affected graph", result.affected_graph),
            ("Brain enrichment", result.brain_enrichment),
        ]
        heading = "# IMPACT"

    lines = [heading, "", "## Revision", "", _json_block(result.revision)]
    for title, value in sections:
        lines.extend(["", f"## {title}", "", _json_block(value)])

    lines.extend(
        [
            "",
            "## Completeness",
            "",
            _json_block(result.completeness),
            "",
            "## Warnings",
            "",
            _json_block(result.warnings),
        ]
    )
    return "\n".join(lines) + "\n"


def _json_block(value: object) -> str:
    return "```json\n" + json.dumps(
        _json_value(value), ensure_ascii=False, indent=2
    ) + "\n```"


def _json_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


__all__ = ["render_intelligence_markdown"]
