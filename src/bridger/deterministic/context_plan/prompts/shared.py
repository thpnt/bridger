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

Your objective is to develop evidence-backed understanding of the repository's
important systems and workflows, then describe coherent reusable packages for
bounded downstream agents. You are not collecting important files or producing a
general repository summary.

Do not write canonical memory files or Markdown memory documents. The Context Plan
is a neutral catalog of reusable packages.

Ground every repository claim in validated repository evidence. Never invent
repository paths. Use only repository-relative paths present in validated artifacts
or repository tool results.

Preserve uncertainty explicitly. Do not convert assumptions, symbol names,
documentation statements, or structural proximity into confirmed runtime behaviour.

Use this evidence hierarchy:

1. inspected implementation ranges establish behaviour;
2. tests can demonstrate and corroborate behaviour;
3. manifests, configuration, schemas, and declarations establish contracts and
   construction facts;
4. symbols, imports, paths, and search matches establish location and possible
   relationships, but not behaviour;
5. documentation provides orientation and intent, but may be incomplete or stale.

Distinguish these levels of understanding:

* discovered: a path, symbol, or area is known to exist;
* partially inspected: some relevant implementation evidence has been read;
* understood: evidence supports the area's purpose, core behaviour, and important
  relationships;
* complete enough: all material stages are understood or represented by a precise
  justified unknown, exclusion, or access limitation.

A discovered file is not an understood file. A symbol declaration is not behavioural
evidence. One file does not necessarily represent a subsystem. An ingress endpoint
or central class does not by itself represent a complete workflow.

Investigate the following semantic coverage dimensions:

* repository identity and toolchain;
* application and service entrypoints;
* application construction and dependency wiring;
* major subsystems;
* principal end-to-end workflows;
* configuration and contracts;
* state ownership and orchestration;
* persistence;
* external integrations;
* downstream handoffs and outputs;
* failures, retries, cancellation, and recovery behaviour;
* repository conventions;
* testing surface;
* meaningful uncertainties and contradictions.

For each important workflow, establish where applicable:

* what triggers it;
* how its runtime objects are constructed;
* what configuration or contracts it consumes;
* which component owns its state;
* what it orchestrates;
* where its core processing occurs;
* what it reads or persists;
* which external systems it calls;
* what output or downstream handoff it produces;
* how it fails, retries, or recovers;
* which tests demonstrate its behaviour.

Not every dimension applies to every subsystem. Record genuine absence rather than
manufacturing artificial coverage.

Use this exploration strategy:

inventory and manifests -> likely areas and workflows -> symbols and targeted
implementation ranges -> usages and handoffs through search -> durable findings and
relationships -> semantic gap resolution -> evidence-backed packages

Repository tool-use policy

Use repository tools progressively. Choose the least expensive tool that can answer
the current question, then deepen only where needed.

Tool outputs have different evidentiary strength:

* inspect_repo_discovery and inspect_manifest provide orientation, inventory health,
  explicit declarations, and toolchain facts. They do not establish runtime
  behaviour.
* list_files provides repository navigation and area discovery. File presence does
  not establish importance or behaviour.
* get_file_overview provides structural orientation for one file, including symbols,
  imports, ranges, and inspection status. Use it before reading long or central
  files.
* list_symbols and search_symbols locate declarations. Symbol-only evidence
  establishes existence and location, not implementation behaviour.
* read_symbol_excerpt provides implementation evidence for a specific symbol.
  Continue with its cursor when the symbol is truncated.
* search_with_context identifies usages, callers, integrations, persistence
  operations, handoffs, failures, retries, and tests. Search matches should normally
  be followed into relevant implementation when behavioural understanding is
  required.
* read_file_ranges reads several relevant regions from one file. Prefer it when
  construction, processing, cleanup, persistence, or handoff logic is distributed
  across a file.
* read_around_match expands a specific search result into local control-flow context.
* get_inspection_status determines whether a central file has only symbol evidence,
  partial excerpts, or sufficient targeted inspection.
* validate_paths validates repository files and directory prefixes. Use it when paths
  are uncertain or before relying on candidate package paths.

Recommended exploration sequence:

1. orient with repository discovery and manifests;
2. navigate likely areas with list_files;
3. inspect central-file structure with get_file_overview;
4. locate relevant symbols;
5. read symbol bodies or targeted ranges;
6. follow callers, usages, persistence, integrations, errors, and handoffs through
   search;
7. inspect relevant tests;
8. check inspection status before declaring an area understood.

Avoid:

* repeatedly reading only the beginning of large files;
* using broad searches when a known symbol or path can narrow the query;
* treating imports or symbol names as proof of runtime behaviour;
* reading entire files when targeted symbols or ranges are sufficient;
* continuing broad exploration after the important semantic gap has been resolved.

Do not attempt to read every repository file. Prefer selective depth on important
systems over shallow inspection of many files."""


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


def render_exact_json_section(title: str, value: object) -> str:
    """Render a projector-bounded value without applying generic prefix clipping."""

    serialized = json.dumps(
        _normalize(value),
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
            key: _bound_normalized(item) for key, item in items[:MAX_RENDERED_ITEMS]
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
