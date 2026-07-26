"""Typed extraction of factual evidence from repository tool results."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import PurePosixPath
from typing import cast

from pydantic import JsonValue

from bridger.models.context_plan import ToolExecutionResult, ToolExecutionStatus
from bridger.models.working_state import (
    EvidenceKind,
    EvidenceLineRange,
    EvidenceRecord,
    InspectionLevel,
)

_SYMBOL_TOOLS = {"search_symbols", "list_symbols"}
_DISCOVERY_LIST_TOOLS = {"list_files", "validate_paths"}
_STATE_CONTROL_TOOLS = {
    "record_finding",
    "refine_finding",
    "supersede_finding",
    "record_relationship",
    "open_question",
    "resolve_question",
    "create_package_candidate",
    "update_package_candidate",
    "merge_package_candidates",
    "discard_package_candidate",
    "restore_package_candidate",
}


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_id(prefix: str, identity: object) -> str:
    digest = sha256(canonical_json(identity).encode()).hexdigest()
    return f"{prefix}.{digest}"


def area_key_for_path(path: str | None) -> str:
    """Return a stable, deliberately small repository-area classification."""

    if path is None:
        return "repository"
    normalized = path.lower()
    if "websocket" in normalized or "/ws/" in f"/{normalized}/":
        return "websocket"
    if "worker" in normalized:
        return "worker"
    if any(
        token in normalized
        for token in ("/persistence/", "/database/", "/storage/", "/repositories/")
    ):
        return "persistence"
    name = PurePosixPath(normalized).name
    if (
        name.startswith(("pyproject.", "package.", "tsconfig.", "ruff."))
        or name in {"go.mod", "cargo.toml", "composer.json", "makefile"}
        or "/config/" in f"/{normalized}/"
    ):
        return "configuration"
    parts = PurePosixPath(normalized).parts
    if parts and parts[0] in {"test", "tests", "spec", "specs"}:
        return "testing"
    if parts and parts[0] in {"src", "app", "lib", "packages", "services"}:
        return "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    return parts[0] if parts else "repository"


class EvidenceExtractor:
    """Convert one successful repository result into canonical evidence records."""

    def extract(
        self,
        result: ToolExecutionResult,
        *,
        starting_sequence: int = 0,
        source_arguments: dict[str, JsonValue] | None = None,
    ) -> list[EvidenceRecord]:
        if (
            result.status is not ToolExecutionStatus.COMPLETED
            or result.output is None
            or result.tool_name == "request_context_plan_finalization"
            or result.tool_name in _STATE_CONTROL_TOOLS
        ):
            return []

        raw = self._raw_records(result)
        records: list[EvidenceRecord] = []
        seen: set[str] = set()
        for offset, item in enumerate(raw, start=1):
            identity = {
                "kind": item["kind"],
                "source_tool": result.tool_name,
                "path": item["path"],
                "line_ranges": item["line_ranges"],
                "symbol_id": item["symbol_id"],
                "structured_payload": item["structured_payload"],
                "content": item["content"],
            }
            evidence_id = stable_id("ev", identity)
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            content = cast(str | None, item["content"])
            payload = dict(cast(dict[str, JsonValue], item["structured_payload"]))
            if source_arguments:
                payload["_request_arguments"] = source_arguments
                identity["structured_payload"] = payload
                evidence_id = stable_id("ev", identity)
            digest_source = content if content is not None else canonical_json(payload)
            content_digest = sha256(digest_source.encode()).hexdigest()
            records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    kind=cast(EvidenceKind, item["kind"]),
                    source_tool=result.tool_name,
                    source_call_id=result.call_id,
                    path=cast(str | None, item["path"]),
                    line_ranges=[
                        EvidenceLineRange.model_validate(value)
                        for value in cast(list[dict[str, int]], item["line_ranges"])
                    ],
                    symbol_id=cast(str | None, item["symbol_id"]),
                    structured_payload=payload,
                    content=content,
                    content_digest=content_digest,
                    inspection_level=cast(InspectionLevel, item["inspection_level"]),
                    truncated=result.truncated,
                    sequence_number=starting_sequence + offset,
                    area_key=area_key_for_path(cast(str | None, item["path"])),
                )
            )
        return records

    def _raw_records(self, result: ToolExecutionResult) -> list[dict[str, object]]:
        output = cast(dict[str, JsonValue], result.output)
        if result.tool_name == "read_file_excerpt":
            return [
                self._record(
                    EvidenceKind.FILE_EXCERPT,
                    path=self._string(output.get("path")),
                    line_ranges=self._line_ranges(
                        output.get("line_start"), output.get("line_end")
                    ),
                    payload=output,
                    content=self._string(output.get("content")),
                    level=InspectionLevel.EXCERPT_INSPECTED,
                )
            ]
        if result.tool_name in {"read_file_ranges", "read_around_match"}:
            path = self._string(output.get("path"))
            return [
                self._record(
                    EvidenceKind.FILE_EXCERPT,
                    path=path,
                    line_ranges=self._line_ranges_from_ranges(output.get("ranges")),
                    payload=output,
                    content="\n\n".join(
                        self._string(item.get("content")) or ""
                        for item in self._items_from_value(output.get("ranges"))
                    ),
                    level=InspectionLevel.EXCERPT_INSPECTED,
                )
            ]
        if result.tool_name == "inspect_manifest":
            manifest = self._mapping(output.get("manifest"))
            return [
                self._record(
                    EvidenceKind.MANIFEST_FACT,
                    path=self._string(manifest.get("path")),
                    payload=manifest,
                    level=InspectionLevel.IMPLEMENTATION_INSPECTED,
                )
            ]
        if result.tool_name == "get_file_overview":
            return [
                self._record(
                    EvidenceKind.FILE_METADATA,
                    path=self._string(output.get("path")),
                    payload=output,
                    level=InspectionLevel.SYMBOL_ONLY,
                )
            ]
        if result.tool_name == "read_symbol_excerpt":
            symbol = self._mapping(output.get("symbol"))
            returned = self._mapping(output.get("returned_source_range"))
            return [
                self._record(
                    EvidenceKind.FILE_EXCERPT,
                    path=self._string(symbol.get("path")),
                    line_ranges=self._line_ranges(
                        returned.get("line_start"), returned.get("line_end")
                    ),
                    symbol_id=self._string(symbol.get("symbol_id")),
                    payload=symbol,
                    content=self._string(output.get("content")),
                    level=InspectionLevel.EXCERPT_INSPECTED,
                )
            ]
        if result.tool_name == "grep_contents":
            return [
                self._record(
                    EvidenceKind.SEARCH_HIT,
                    path=self._string(item.get("path")),
                    line_ranges=self._line_ranges(
                        item.get("line_number"), item.get("line_number")
                    ),
                    payload=item,
                    content=self._string(item.get("match")),
                    level=InspectionLevel.LINE_OBSERVED,
                )
                for item in self._items(output)
            ]
        if result.tool_name == "search_with_context":
            return [
                self._record(
                    EvidenceKind.SEARCH_HIT,
                    path=self._string(item.get("path")),
                    line_ranges=self._line_ranges(
                        self._mapping(item.get("context_range")).get("line_start"),
                        self._mapping(item.get("context_range")).get("line_end"),
                    ),
                    payload=item,
                    content=self._string(item.get("content")),
                    level=InspectionLevel.LINE_OBSERVED,
                )
                for item in self._items(output)
            ]
        if result.tool_name in _SYMBOL_TOOLS:
            return [
                self._record(
                    EvidenceKind.SYMBOL_METADATA,
                    path=self._string(item.get("path")),
                    line_ranges=self._line_ranges(
                        item.get("line_start"), item.get("line_end")
                    ),
                    symbol_id=self._string(item.get("symbol_id")),
                    payload=item,
                    content=self._string(item.get("signature_preview")),
                    level=InspectionLevel.SYMBOL_ONLY,
                )
                for item in self._items(output)
            ]
        if result.tool_name == "get_symbol":
            item = self._mapping(output.get("symbol"))
            return [
                self._record(
                    EvidenceKind.SYMBOL_METADATA,
                    path=self._string(item.get("path")),
                    line_ranges=self._line_ranges(
                        item.get("line_start"), item.get("line_end")
                    ),
                    symbol_id=self._string(item.get("id")),
                    payload=item,
                    content=self._string(item.get("declaration")),
                    level=InspectionLevel.SYMBOL_ONLY,
                )
            ]
        if result.tool_name in _DISCOVERY_LIST_TOOLS:
            return [
                self._record(
                    EvidenceKind.FILE_METADATA,
                    path=self._string(item.get("path")),
                    payload=item,
                    level=InspectionLevel.DISCOVERED,
                )
                for item in self._items(output)
                if self._string(item.get("path")) is not None
            ]
        return [
            self._record(
                EvidenceKind.REPOSITORY_FACT,
                payload=output,
                level=InspectionLevel.LOCATED,
            )
        ]

    @staticmethod
    def _items_from_value(value: JsonValue | None) -> list[dict[str, JsonValue]]:
        return (
            [item for item in value if isinstance(item, dict)]
            if isinstance(value, list)
            else []
        )

    @classmethod
    def _line_ranges_from_ranges(cls, value: JsonValue | None) -> list[dict[str, int]]:
        ranges: list[dict[str, int]] = []
        for item in cls._items_from_value(value):
            ranges.extend(
                cls._line_ranges(item.get("line_start"), item.get("line_end"))
            )
        return ranges

    @staticmethod
    def _record(
        kind: EvidenceKind,
        *,
        path: str | None = None,
        line_ranges: list[dict[str, int]] | None = None,
        symbol_id: str | None = None,
        payload: dict[str, JsonValue] | None = None,
        content: str | None = None,
        level: InspectionLevel,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "path": path,
            "line_ranges": line_ranges or [],
            "symbol_id": symbol_id,
            "structured_payload": payload or {},
            "content": content,
            "inspection_level": level,
        }

    @staticmethod
    def _items(output: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
        for key in (
            "results",
            "files",
            "symbols",
            "config_files",
            "docs_files",
            "instruction_files",
        ):
            value = output.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        symbol = output.get("symbol")
        if isinstance(symbol, dict):
            return [symbol]
        return []

    @staticmethod
    def _mapping(value: JsonValue | None) -> dict[str, JsonValue]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _string(value: JsonValue | None) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _line_ranges(
        line_start: JsonValue | None, line_end: JsonValue | None
    ) -> list[dict[str, int]]:
        if (
            isinstance(line_start, int)
            and not isinstance(line_start, bool)
            and isinstance(line_end, int)
            and not isinstance(line_end, bool)
            and line_start > 0
            and line_end >= line_start
        ):
            return [{"line_start": line_start, "line_end": line_end}]
        return []
