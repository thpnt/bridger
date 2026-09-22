"""JSON presentation for canonical Bridger intelligence results."""

from typing import cast

from pydantic import JsonValue

from bridger.contracts._legacy_consumption import IntelligenceResult


def render_intelligence_json(result: IntelligenceResult) -> dict[str, JsonValue]:
    """Return the canonical result in Pydantic's JSON-compatible representation."""
    return cast(dict[str, JsonValue], result.model_dump(mode="json"))


__all__ = ["render_intelligence_json"]
