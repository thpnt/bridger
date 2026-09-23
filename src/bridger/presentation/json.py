"""JSON presentation for canonical Bridger consumption results."""

from typing import cast

from pydantic import JsonValue

from bridger.contracts.consumption import ImpactResult, UnderstandResult


def render_intelligence_json(
    result: UnderstandResult | ImpactResult,
) -> dict[str, JsonValue]:
    """Return the canonical result in Pydantic's JSON-compatible representation."""
    return cast(dict[str, JsonValue], result.model_dump(mode="json"))


__all__ = ["render_intelligence_json"]
