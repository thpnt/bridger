"""The bounded, evidence-only Context Plan exploration registry."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from bridger.llm.models import LLMMessage, LLMToolCall, LLMToolDefinition
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanValidationIssue,
    FinalizationContext,
    FinalizationDecision,
    ToolBudgetCost,
    ToolCallRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInspectionDelta,
)
from bridger.models.repository_path import RepositoryPath
from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import BridgerToolError


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(extra="allow")


class FileExcerptOutput(Output):
    source_artifact: str
    path: RepositoryPath
    line_start: int = Field(gt=0)
    line_end: int = Field(gt=0)
    content: str
    truncated: bool = False


class EmptyInput(Input):
    pass


class ManifestInput(Input):
    path: RepositoryPath | None = None


class ListFilesInput(Input):
    prefix: RepositoryPath | None = None
    pattern: str | None = None
    extension: str | None = None
    role: str | None = None
    recursive: bool = False
    max_depth: int = Field(default=1, ge=0, le=8)
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = None


class OverviewInput(Input):
    path: RepositoryPath
    symbol_limit: int = Field(default=100, ge=1, le=300)
    symbol_cursor: str | None = None
    import_limit: int = Field(default=100, ge=1, le=300)
    import_cursor: str | None = None


class SymbolsInput(Input):
    path: RepositoryPath | None = None
    prefix: RepositoryPath | None = None
    kinds: list[str] | None = None
    parent_symbol_id: str | None = None
    language: str | None = None
    exported: bool | None = None
    body_available: bool | None = None
    extraction_status: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = None


class SearchSymbolsInput(SymbolsInput):
    query: str = Field(min_length=1, max_length=256)
    match_mode: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class SymbolExcerptInput(Input):
    symbol_id: str = Field(min_length=1)
    context_lines: int = Field(default=10, ge=0, le=50)
    cursor: str | None = None


class SearchContextInput(Input):
    query: str = Field(min_length=1)
    match_mode: Literal["literal", "regex"] = "literal"
    case_sensitive: bool = False
    path_prefix: RepositoryPath | None = None
    file_pattern: str | None = None
    before: int = Field(default=3, ge=0, le=20)
    after: int = Field(default=3, ge=0, le=20)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class FileRangesInput(Input):
    path: RepositoryPath
    ranges: list[dict[str, int]] = Field(min_length=1, max_length=10)


class AroundInput(Input):
    path: RepositoryPath
    line: int = Field(ge=1)
    before: int = Field(default=20, ge=0, le=100)
    after: int = Field(default=20, ge=0, le=100)


class PathsInput(Input):
    paths: list[RepositoryPath] = Field(min_length=1, max_length=500)


class FinalizationInput(ContextPlanFinalizationRequest):
    pass


@dataclass(frozen=True)
class Handled:
    output: dict[str, JsonValue]
    actual_cost: ToolBudgetCost
    delta: ToolInspectionDelta = field(default_factory=ToolInspectionDelta)


@dataclass(frozen=True)
class Definition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], Handled]
    cost: ToolBudgetCost
    kind: Literal["repository", "control"]

    @property
    def estimated_cost(self) -> ToolBudgetCost:
        return self.cost

    def to_llm_definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=cast(
                dict[str, JsonValue], self.input_model.model_json_schema()
            ),
        )


class DiscoveryToolRegistry:
    def __init__(self, definitions: list[Definition]) -> None:
        self._definitions = {item.name: item for item in definitions}

    @property
    def definitions(self) -> list[Definition]:
        return list(self._definitions.values())

    def get(self, name: str) -> Definition | None:
        return self._definitions.get(name)

    def llm_definitions(self) -> list[LLMToolDefinition]:
        return [item.to_llm_definition() for item in self.definitions]


class DiscoveryToolExecutor:
    def __init__(
        self,
        context: BridgerToolContext,
        *,
        finalization_evaluator: object | None = None,
        finalization_context_provider: Callable[[], FinalizationContext] | None = None,
    ) -> None:
        self.context = context
        self.finalization_evaluator = finalization_evaluator
        self.finalization_context_provider = finalization_context_provider
        self.registry = DiscoveryToolRegistry(self._definitions())

    def execute(self, request: ToolCallRequest) -> ToolExecutionResult:
        definition = self.registry.get(request.name)
        if definition is None:
            return self._reject(
                request, ToolBudgetCost(), "invalid_arguments", "Tool is not registered"
            )
        try:
            value = definition.input_model.model_validate(request.arguments)
            handled = definition.handler(value)
        except ValidationError as error:
            return self._reject(
                request,
                definition.cost,
                "invalid_arguments",
                "Tool arguments do not match the declared schema",
                {"errors": json.loads(error.json())},
            )
        except BridgerToolError as error:
            return self._reject(
                request,
                definition.cost,
                error.payload.error,
                error.payload.message,
                error.payload.details or {},
            )
        except Exception:
            return self._reject(
                request, definition.cost, "internal_tool_error", "Tool execution failed"
            )
        output = handled.output
        if len(json.dumps(output, ensure_ascii=False).encode("utf-8")) > 128 * 1024:
            return self._reject(
                request,
                definition.cost,
                "result_limit_exceeded",
                "Tool response exceeds the 128 KiB serialized response ceiling",
            )
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.COMPLETED,
            output=output,
            estimated_cost=definition.cost,
            actual_cost=handled.actual_cost,
            inspection_delta=handled.delta,
            truncated=bool(output.get("truncated", False)),
        )

    def _definitions(self) -> list[Definition]:
        return [
            self._definition(
                "inspect_repo_discovery",
                "Orient using deterministic repository inventory and artifact health.",
                EmptyInput,
                self._repo_discovery,
            ),
            self._definition(
                "inspect_manifest",
                "Inspect one explicit manifest declaration.",
                ManifestInput,
                self._manifest,
                ToolBudgetCost(file_reads=1),
            ),
            self._definition(
                "list_files",
                "Navigate Git-tracked inventory paths and directory prefixes.",
                ListFilesInput,
                self._list_files,
            ),
            self._definition(
                "get_file_overview",
                "Return bounded structural metadata, symbols, and local import syntax.",
                OverviewInput,
                self._overview,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._definition(
                "list_symbols",
                "List indexed symbols without reading symbol bodies.",
                SymbolsInput,
                self._list_symbols,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._definition(
                "search_symbols",
                "Search indexed symbol names using deterministic matching.",
                SearchSymbolsInput,
                self._search_symbols,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._definition(
                "read_symbol_excerpt",
                "Read a complete symbol progressively with exact source ranges.",
                SymbolExcerptInput,
                self._symbol_excerpt,
                ToolBudgetCost(file_reads=1, excerpts=1),
            ),
            self._definition(
                "search_with_context",
                "Search readable Git-tracked source with bounded line context.",
                SearchContextInput,
                self._search_context,
                ToolBudgetCost(searches=1),
            ),
            self._definition(
                "read_file_ranges",
                "Read multiple normalized inclusive file ranges.",
                FileRangesInput,
                self._ranges,
                ToolBudgetCost(file_reads=1, excerpts=1),
            ),
            self._definition(
                "read_around_match",
                "Read bounded context around one source line.",
                AroundInput,
                self._around,
                ToolBudgetCost(file_reads=1, excerpts=1),
            ),
            self._definition(
                "get_inspection_status",
                "Report factual persistent inspection state for a file.",
                OverviewInput,
                self._inspection,
            ),
            self._definition(
                "validate_paths",
                "Validate Git-inventory files and directory prefixes.",
                PathsInput,
                self._validate,
            ),
            Definition(
                "request_context_plan_finalization",
                "Submit structured evidence for finalization policy evaluation.",
                FinalizationInput,
                self._finalize,
                ToolBudgetCost(),
                "control",
            ),
        ]

    @staticmethod
    def _definition(
        name: str,
        description: str,
        model: type[BaseModel],
        handler: Callable[[BaseModel], Handled],
        cost: ToolBudgetCost | None = None,
    ) -> Definition:
        return Definition(
            name, description, model, handler, cost or ToolBudgetCost(), "repository"
        )

    def _repo_discovery(self, _: BaseModel) -> Handled:
        files = self.context.file_index.artifact.files
        roles = {
            role: []
            for role in (
                "manifest",
                "documentation",
                "instruction",
                "configuration",
                "test",
                "ci",
            )
        }
        for item in files:
            from bridger.tools.services.file_roles import classify_file_roles

            for role in classify_file_roles(item.path):
                if role in roles:
                    roles[role].append(item.path)
        index = self.context.symbols.artifact
        statuses: dict[str, int] = {}
        for file in index.files:
            statuses[file.status.value] = statuses.get(file.status.value, 0) + 1
        payload = self._common(
            {
                "repository": {
                    "revision": self.context.cursors.source_fingerprint.split(":", 1)[
                        0
                    ],
                    "inventory_schema_version": (
                        self.context.file_index.artifact.schema_version
                    ),
                },
                "inventory": {
                    "total_files": len(files),
                    "readable_text_files": sum(
                        item.read_policy.value == "readable" for item in files
                    ),
                    "metadata_only_files": sum(
                        item.read_policy.value != "readable" for item in files
                    ),
                    "binary_files": sum(item.is_binary for item in files),
                    "sensitive_files": sum(
                        reason == "sensitive_file"
                        for reason in self.context.path_safety.skipped_paths.values()
                    ),
                    "restricted_files": sum(
                        item.read_policy.value != "readable" for item in files
                    ),
                    "total_bytes": sum(item.size_bytes for item in files),
                    "total_lines_if_known": sum(item.line_count for item in files),
                },
                "top_level_structure": self._top_level(files),
                "languages": self._languages(),
                "content_kinds": self._content_kinds(files),
                "anchors": {key: sorted(value)[:50] for key, value in roles.items()},
                "symbol_index": {
                    "schema_version": index.schema_version,
                    "total_symbols": len(index.symbols),
                    "indexed_files": len(index.files),
                    "successful_files": statuses.get("success", 0),
                    "partial_files": statuses.get("partial", 0),
                    "unsupported_files": statuses.get("unsupported", 0),
                    "failed_files": sum(
                        value
                        for key, value in statuses.items()
                        if key in {"parse_error", "read_error", "extractor_error"}
                    ),
                    "errors_by_code": {},
                },
                "omitted_count": sum(
                    max(0, len(value) - 50) for value in roles.values()
                ),
                "omitted_reasons": ["anchor_limit"]
                if any(len(value) > 50 for value in roles.values())
                else [],
            }
        )
        return Handled(payload, ToolBudgetCost())

    def _manifest(self, value: BaseModel) -> Handled:
        selected = cast(ManifestInput, value).path
        manifests = self.context.repo_context.artifact.manifests
        if selected is None:
            if len(manifests) != 1:
                raise BridgerToolError(
                    "invalid_arguments",
                    "path is required when multiple manifests exist",
                )
            selected = manifests[0].path
        output = self.context.repo_context.inspect_manifest(selected)
        return Handled(
            self._common(output),
            ToolBudgetCost(file_reads=1),
            self._ranges_delta(
                selected, [(1, self.context.file_index.get_file(selected).line_count)]
            ),
        )

    def _list_files(self, value: BaseModel) -> Handled:
        data = cast(ListFilesInput, value)
        return Handled(
            cast(
                dict[str, JsonValue],
                self.context.file_index.list_files(**data.model_dump()),
            ),
            ToolBudgetCost(),
        )

    def _overview(self, value: BaseModel) -> Handled:
        data = cast(OverviewInput, value)
        item = self.context.file_index.get_file(data.path)
        symbols = self.context.symbols.list_for_path(
            data.path, data.symbol_limit, data.symbol_cursor
        )
        symbol_items = [
            self._symbol_navigation(item)
            for item in cast(list[dict[str, object]], symbols["symbols"])
        ]
        imports = self._imports(data.path, data.import_limit)
        output = self._common(
            {
                "path": data.path,
                "language": self._language(data.path),
                "content_kind": item.content_type.value,
                "read_policy": item.read_policy.value,
                "size_bytes": item.size_bytes,
                "total_lines": item.line_count,
                "symbols": {
                    "total": symbols["total_available"],
                    "returned": len(symbol_items),
                    "items": symbol_items,
                    "has_more": symbols["has_more"],
                    "next_cursor": symbols["next_cursor"],
                },
                "imports": {
                    "total": len(imports),
                    "returned": len(imports),
                    "items": imports,
                    "has_more": False,
                    "next_cursor": None,
                },
                "structural_sections": [],
                "inspected_ranges": [],
                "inspection_level": "structural_overview_only",
                "symbol_inspection_summary": {"discovered": len(symbol_items)},
            }
        )
        return Handled(
            output,
            ToolBudgetCost(symbol_queries=1),
            ToolInspectionDelta(evidence_paths=[data.path]),
        )

    def _list_symbols(self, value: BaseModel) -> Handled:
        data = cast(SymbolsInput, value)
        if data.kinds is not None and len(data.kinds) != 1:
            raise BridgerToolError("invalid_arguments", "Use one kind per symbol query")
        output = self.context.symbols.list_for_path(
            data.path,
            data.limit,
            data.cursor,
            path_prefix=data.prefix,
            language=data.language,
            kind=data.kinds[0] if data.kinds else None,
            parent_id=data.parent_symbol_id,
            exported=data.exported,
            body_available=data.body_available,
            extraction_status=data.extraction_status,
        )
        output["symbols"] = [
            self._symbol_navigation(item)
            for item in cast(list[dict[str, object]], output["symbols"])
        ]
        return Handled(self._common(output), ToolBudgetCost(symbol_queries=1))

    def _search_symbols(self, value: BaseModel) -> Handled:
        data = cast(SearchSymbolsInput, value)
        output = self.context.symbols.search(
            data.query,
            data.limit,
            data.cursor,
            match_mode=data.match_mode,
            path_prefix=data.prefix,
            language=data.language,
            kind=data.kinds[0] if data.kinds else None,
            parent_id=data.parent_symbol_id,
            exported=data.exported,
            body_available=data.body_available,
            extraction_status=data.extraction_status,
        )
        output["symbols"] = [
            self._symbol_navigation(item)
            for item in cast(list[dict[str, object]], output["symbols"])
        ]
        return Handled(self._common(output), ToolBudgetCost(symbol_queries=1))

    def _symbol_excerpt(self, value: BaseModel) -> Handled:
        data = cast(SymbolExcerptInput, value)
        symbol = self.context.symbols.get(data.symbol_id)
        body_end = symbol.declaration_range.end_line
        cursor_line = None
        filters = {"symbol_id": data.symbol_id, "context_lines": data.context_lines}
        if data.cursor:
            cursor_line = int(
                self.context.cursors.decode(
                    data.cursor, "read_symbol_excerpt", filters
                )[0]
            )
        read = self.context.file_read.read_symbol(
            symbol.path,
            symbol.declaration_range.start_line,
            body_end,
            data.context_lines,
            cursor_line,
        )
        if read["has_more"]:
            read["next_cursor"] = self.context.cursors.encode(
                "read_symbol_excerpt", filters, [read["next_line"]]
            )
        output = self._common(
            {
                "symbol": self._symbol_navigation(symbol.model_dump(mode="json")),
                "symbol_total_lines": body_end
                - symbol.declaration_range.start_line
                + 1,
                "returned_symbol_relative_range": {
                    "line_start": read["returned_source_range"]["line_start"]
                    - symbol.declaration_range.start_line
                    + 1,
                    "line_end": read["returned_source_range"]["line_end"]
                    - symbol.declaration_range.start_line
                    + 1,
                },
                **read,
            }
        )
        returned = read["returned_source_range"]
        return Handled(
            output,
            ToolBudgetCost(file_reads=1, excerpts=1),
            self._ranges_delta(
                symbol.path, [(returned["line_start"], returned["line_end"])], symbol.id
            ),
        )

    def _search_context(self, value: BaseModel) -> Handled:
        data = cast(SearchContextInput, value)
        output = self.context.search.search_with_context(**data.model_dump())
        ranges = [
            (
                str(item["path"]),
                int(cast(dict[str, int], item["context_range"])["line_start"]),
                int(cast(dict[str, int], item["context_range"])["line_end"]),
            )
            for item in cast(list[dict[str, object]], output["results"])
        ]
        delta = ToolInspectionDelta(
            evidence_paths=sorted({path for path, _, _ in ranges}),
            excerpts_read=[
                ContextPlanInspectedExcerpt(path=path, line_start=start, line_end=end)
                for path, start, end in ranges
            ],
        )
        return Handled(self._common(output), ToolBudgetCost(searches=1), delta)

    def _ranges(self, value: BaseModel) -> Handled:
        data = cast(FileRangesInput, value)
        output = self.context.file_read.read_ranges(data.path, data.ranges)
        ranges = [
            (int(item["line_start"]), int(item["line_end"]))
            for item in cast(list[dict[str, object]], output["ranges"])
        ]
        return Handled(
            self._common(output),
            ToolBudgetCost(file_reads=1, excerpts=1),
            self._ranges_delta(data.path, ranges),
        )

    def _around(self, value: BaseModel) -> Handled:
        data = cast(AroundInput, value)
        output = self.context.file_read.read_around(
            data.path, data.line, data.before, data.after
        )
        returned = cast(dict[str, int], output["returned_range"])
        return Handled(
            self._common(output),
            ToolBudgetCost(file_reads=1, excerpts=1),
            self._ranges_delta(
                data.path, [(returned["line_start"], returned["line_end"])]
            ),
        )

    def _inspection(self, value: BaseModel) -> Handled:
        data = cast(OverviewInput, value)
        item = self.context.file_index.get_file(data.path)
        try:
            state = self.context.artifact_store.load_context_plan_working_state()
        except BridgerToolError:
            state = None
        file = (
            next(
                (entry for entry in state.inspected_files if entry.path == data.path),
                None,
            )
            if state
            else None
        )
        ranges = (
            [entry.model_dump(mode="json") for entry in file.inspected_ranges]
            if file
            else []
        )
        observed = sum(entry["line_end"] - entry["line_start"] + 1 for entry in ranges)
        return Handled(
            self._common(
                {
                    "path": data.path,
                    "total_lines": item.line_count,
                    "inspected_ranges": ranges[:200],
                    "remaining_ranges": self._remaining(item.line_count, ranges),
                    "inspection_ratio": observed / item.line_count
                    if item.line_count
                    else 1.0,
                    "symbols": {
                        "total": len(
                            self.context.symbols.list_for_path(data.path, 500)[
                                "symbols"
                            ]
                        ),
                        "discovered": len(file.symbol_ids_seen) if file else 0,
                        "declaration_only": len(file.symbol_ids_seen)
                        - len(file.symbol_ids_inspected)
                        if file
                        else 0,
                        "bodies_partially_inspected": len(file.symbol_ids_inspected)
                        if file
                        else 0,
                        "bodies_fully_inspected": 0,
                    },
                    "inspection_level": self._inspection_level(file),
                }
            ),
            ToolBudgetCost(),
        )

    def _validate(self, value: BaseModel) -> Handled:
        return Handled(
            self._common(
                self.context.file_index.validate_paths(cast(PathsInput, value).paths)
            ),
            ToolBudgetCost(),
        )

    def _finalize(self, value: BaseModel) -> Handled:
        if (
            self.finalization_evaluator is None
            or self.finalization_context_provider is None
        ):
            raise BridgerToolError(
                "artifact_unavailable", "Finalization is not configured"
            )
        decision = cast(object, self.finalization_evaluator).evaluate(
            cast(ContextPlanFinalizationRequest, value),
            self.finalization_context_provider(),
        )
        return Handled(
            {"decision": cast(FinalizationDecision, decision).model_dump(mode="json")},
            ToolBudgetCost(),
        )

    @staticmethod
    def _common(payload: dict[str, object]) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "status": "completed",
                "total_available": payload.get("total_available"),
                "returned_count": payload.get("returned_count"),
                "has_more": payload.get("has_more", False),
                "next_cursor": payload.get("next_cursor"),
                "truncated": payload.get("truncated", False),
                "omitted_count": payload.get("omitted_count", 0),
                "omitted_reasons": payload.get("omitted_reasons", []),
                "warnings": payload.get("warnings", []),
                **payload,
            },
        )

    @staticmethod
    def _symbol_navigation(value: dict[str, object]) -> dict[str, object]:
        return {
            "symbol_id": value.get("id"),
            "path": value.get("path"),
            "language": value.get("language"),
            "name": value.get("name"),
            "qualified_name": value.get("qualified_name"),
            "kind": value.get("kind"),
            "parent_id": value.get("parent_id"),
            "declaration_range": value.get("declaration_range"),
            "body_range": value.get("body_range"),
            "body_available": value.get("body_available"),
            "signature_preview": value.get("signature"),
            "exported": value.get("exported"),
            "extraction_status": value.get("extraction_status"),
        }

    @staticmethod
    def _ranges_delta(
        path: str, ranges: list[tuple[int, int]], symbol_id: str | None = None
    ) -> ToolInspectionDelta:
        return ToolInspectionDelta(
            evidence_paths=[path],
            excerpts_read=[
                ContextPlanInspectedExcerpt(path=path, line_start=start, line_end=end)
                for start, end in ranges
            ],
            symbols_inspected=[
                ContextPlanInspectedSymbol(identifier=symbol_id, path=path)
            ]
            if symbol_id
            else [],
        )

    @staticmethod
    def _top_level(files: list[object]) -> dict[str, list[str]]:
        paths = sorted(cast(str, item.path) for item in files)
        return {
            "files": [path for path in paths if "/" not in path][:50],
            "directories": sorted(
                {path.split("/", 1)[0] for path in paths if "/" in path}
            )[:50],
        }

    def _languages(self) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for symbol in self.context.symbols.artifact.symbols:
            counts[symbol.language] = counts.get(symbol.language, 0) + 1
        return [
            {
                "language": name,
                "file_count": sum(
                    self._language(item.path) == name
                    for item in self.context.file_index.artifact.files
                ),
                "symbol_count": count,
            }
            for name, count in sorted(counts.items())
        ]

    @staticmethod
    def _content_kinds(files: list[object]) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for item in files:
            counts[item.content_type.value] = counts.get(item.content_type.value, 0) + 1
        return [{"kind": key, "count": value} for key, value in sorted(counts.items())]

    @staticmethod
    def _language(path: str) -> str | None:
        return {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".php": "php",
        }.get("." + path.rsplit(".", 1)[1] if "." in path else "")

    def _imports(self, path: str, limit: int) -> list[dict[str, object]]:
        """Return local import syntax without resolving it to repository paths."""
        language = self._language(path)
        if language not in {"python", "javascript", "typescript"}:
            return []
        item = self.context.file_index.get_file(path)
        if item.read_policy.value != "readable":
            return []
        try:
            lines = (
                self.context.path_safety.resolve_for_read(path)
                .read_text(encoding=item.detected_encoding)
                .splitlines()
            )
        except (BridgerToolError, OSError, UnicodeError, LookupError):
            return []
        imports: list[dict[str, object]] = []
        for line_number, raw in enumerate(lines, start=1):
            text = raw.strip()
            if language == "python" and text.startswith(("import ", "from ")):
                module = text.split()[1]
                form = "from" if text.startswith("from ") else "import"
            elif language in {"javascript", "typescript"} and text.startswith(
                "import "
            ):
                module = text.rsplit(" from ", 1)[-1].strip(";'\"")
                form = "import"
            else:
                continue
            imports.append(
                {
                    "raw_text": raw,
                    "module_or_source": module,
                    "import_form": form,
                    "source_range": {
                        "start_line": line_number,
                        "end_line": line_number,
                    },
                }
            )
            if len(imports) == limit:
                break
        return imports

    @staticmethod
    def _remaining(total: int, ranges: list[dict[str, int]]) -> list[dict[str, int]]:
        cursor, result = 1, []
        for item in ranges:
            if cursor < item["line_start"]:
                result.append(
                    {"line_start": cursor, "line_end": item["line_start"] - 1}
                )
            cursor = item["line_end"] + 1
        if cursor <= total:
            result.append({"line_start": cursor, "line_end": total})
        return result[:200]

    @staticmethod
    def _inspection_level(file: object | None) -> str:
        if file is None:
            return "not_inspected"
        status = file.inspection_status.value
        return {
            "discovered": "not_inspected",
            "symbol_only": "symbol_only",
            "partially_inspected": "partial_excerpt",
            "implementation_inspected": "substantively_inspected",
        }.get(status, "not_inspected")

    def _reject(
        self,
        request: ToolCallRequest,
        cost: ToolBudgetCost,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.REJECTED,
            issues=[
                ContextPlanValidationIssue(
                    code=code,
                    location=["arguments"],
                    message=message,
                    context=cast(dict[str, JsonValue], details or {}),
                )
            ],
            estimated_cost=cost,
            actual_cost=ToolBudgetCost(),
        )


def tool_call_request_from_llm_call(call: LLMToolCall) -> ToolCallRequest:
    return ToolCallRequest(call_id=call.id, name=call.name, arguments=call.arguments)


def tool_result_to_llm_message(result: ToolExecutionResult) -> LLMMessage:
    return LLMMessage.tool_result_message(
        tool_call_id=result.call_id,
        tool_name=result.tool_name,
        result={
            "status": result.status.value,
            "output": result.output,
            "issues": [issue.model_dump(mode="json") for issue in result.issues],
            "truncated": result.truncated,
        },
        failed=result.status is not ToolExecutionStatus.COMPLETED,
    )
