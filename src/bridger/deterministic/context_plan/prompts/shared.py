"""Small deterministic rendering helpers shared by Context Plan prompts."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from bridger.llm.models import LLMToolDefinition

MAX_RENDERED_ITEMS = 40
MAX_RENDERED_STRING_CHARACTERS = 4_000
MAX_RENDERED_SECTION_CHARACTERS = 16_000

COMMON_INSTRUCTIONS = """You are building a Context Plan for Bridger, not writing code.
Do not write canonical memory files or Markdown memory documents.
Ground every repository claim in the available evidence. Never invent repository
paths: use only repository-relative paths present in validated artifacts or
repository tool results. Preserve uncertainty explicitly when evidence is absent
or incomplete. Deterministic artifacts provide factual constraints; you own the
interpretation of those facts. The eventual Context Plan is a neutral catalog of
reusable packages. Do not assign packages to downstream memory agents."""


def build_system_message(extra_instructions: str) -> str:
    return f"{COMMON_INSTRUCTIONS}\n\n{extra_instructions}"


def render_json_section(title: str, value: object) -> str:
    """Render prompt context canonically with visible, bounded truncation."""

    bounded = _bound(value)
    serialized = json.dumps(
        bounded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized) > MAX_RENDERED_SECTION_CHARACTERS:
        serialized = json.dumps(
            {
                "_bridger_truncated": (
                    "Section exceeded "
                    f"{MAX_RENDERED_SECTION_CHARACTERS} characters; the preview "
                    "does not contain all supplied evidence."
                ),
                "preview": serialized[:MAX_RENDERED_SECTION_CHARACTERS],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return f"{title}:\n```json\n{serialized}\n```"


def render_tool_catalog(tools: list[LLMToolDefinition]) -> str:
    """Describe supplied tools while their schemas remain in the prompt payload."""

    catalog = [
        {"description": tool.description, "name": tool.name}
        for tool in sorted(tools, key=lambda tool: tool.name)
    ]
    return render_json_section("Available tool catalog", catalog)


def sorted_tools(tools: list[LLMToolDefinition]) -> tuple[LLMToolDefinition, ...]:
    return tuple(sorted(tools, key=lambda tool: tool.name))


def sorted_strings(values: list[str]) -> list[str]:
    return sorted(values)


def sorted_paths(paths: list[str]) -> list[str]:
    return sorted(paths)


def _bound(value: object) -> Any:
    normalized = _normalize(value)
    return _bound_normalized(normalized)


def _normalize(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize(item) for item in value]
    return value


def _bound_normalized(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= MAX_RENDERED_STRING_CHARACTERS:
            return value
        omitted = len(value) - MAX_RENDERED_STRING_CHARACTERS
        return (
            value[:MAX_RENDERED_STRING_CHARACTERS]
            + f" [BRIDGER TRUNCATED: {omitted} characters omitted]"
        )
    if isinstance(value, dict):
        items = sorted(value.items())
        bounded = {
            key: _bound_normalized(item)
            for key, item in items[:MAX_RENDERED_ITEMS]
        }
        if len(items) > MAX_RENDERED_ITEMS:
            bounded["_bridger_truncated"] = (
                f"{len(items) - MAX_RENDERED_ITEMS} mapping entries omitted"
            )
        return bounded
    if isinstance(value, list):
        items = [_bound_normalized(item) for item in value]
        items.sort(key=_canonical_key)
        if len(items) > MAX_RENDERED_ITEMS:
            return [
                *items[:MAX_RENDERED_ITEMS],
                {
                    "_bridger_truncated": (
                        f"{len(items) - MAX_RENDERED_ITEMS} list entries omitted"
                    )
                },
            ]
        return items
    return value


def _canonical_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
