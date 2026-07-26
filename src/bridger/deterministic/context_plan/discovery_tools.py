"""Typed context-plan discovery tools over deterministic repository artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from bridger.llm.models import LLMMessage, LLMToolCall, LLMToolDefinition
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanSearchRecord,
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
from bridger.tools.models import FileFilters, GrepFilters


class DiscoveryToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoveryToolOutput(BaseModel):
    """Common output boundary while keeping artifact payloads forward compatible."""

    model_config = ConfigDict(extra="allow")


class EmptyInput(DiscoveryToolInput):
    pass


class ListFilesInput(DiscoveryToolInput):
    filters: FileFilters = Field(default_factory=FileFilters)


class SearchPathsInput(DiscoveryToolInput):
    query: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1)


class GrepContentsInput(DiscoveryToolInput):
    query: str = Field(min_length=1)
    filters: GrepFilters = Field(default_factory=GrepFilters)


class ReadFileExcerptInput(DiscoveryToolInput):
    path: RepositoryPath
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class PathInput(DiscoveryToolInput):
    path: RepositoryPath


class ListSymbolsInput(PathInput):
    limit: int | None = Field(default=None, ge=1)


class SymbolIdInput(DiscoveryToolInput):
    symbol_id: str = Field(min_length=1)


class SearchSymbolsInput(DiscoveryToolInput):
    query: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1)


class ValidatePathsInput(DiscoveryToolInput):
    paths: list[RepositoryPath] = Field(min_length=1, max_length=100)


class RequestContextPlanFinalizationInput(ContextPlanFinalizationRequest):
    pass


class RepositoryListingOutput(DiscoveryToolOutput):
    source_artifact: str
    total_matches: int = Field(ge=0)
    limit_applied: int = Field(ge=0)
    truncated: bool


class FileExcerptOutput(DiscoveryToolOutput):
    source_artifact: str
    path: RepositoryPath
    line_start: int = Field(gt=0)
    line_end: int = Field(gt=0)
    content: str
    truncated: bool


class ManifestOutput(DiscoveryToolOutput):
    source_artifact: str
    manifest: dict[str, JsonValue]


class SymbolOutput(DiscoveryToolOutput):
    source_artifact: str
    symbol: dict[str, JsonValue]


class FinalizationOutput(DiscoveryToolOutput):
    decision: dict[str, JsonValue]


class FinalizationEvaluator(Protocol):
    def evaluate(
        self,
        request: ContextPlanFinalizationRequest,
        context: FinalizationContext,
    ) -> FinalizationDecision: ...


FinalizationContextProvider = Callable[[], FinalizationContext]
ToolHandler = Callable[[BaseModel], "ToolHandlerResult"]


@dataclass(frozen=True)
class ToolHandlerResult:
    output: dict[str, JsonValue]
    actual_cost: ToolBudgetCost
    inspection_delta: ToolInspectionDelta = field(default_factory=ToolInspectionDelta)
    truncated: bool = False


@dataclass(frozen=True)
class DiscoveryToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[DiscoveryToolOutput]
    handler: ToolHandler
    estimated_cost: ToolBudgetCost
    output_limit: int | None
    kind: Literal["repository", "control"]

    @property
    def input_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self.input_model.model_json_schema())

    @property
    def output_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self.output_model.model_json_schema())

    def to_llm_definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


class DiscoveryToolRegistry:
    def __init__(self, definitions: list[DiscoveryToolDefinition]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def definitions(self) -> list[DiscoveryToolDefinition]:
        return list(self._definitions.values())

    def get(self, name: str) -> DiscoveryToolDefinition | None:
        return self._definitions.get(name)

    def llm_definitions(self) -> list[LLMToolDefinition]:
        return [definition.to_llm_definition() for definition in self.definitions]


class DiscoveryToolExecutor:
    def __init__(
        self,
        context: BridgerToolContext,
        *,
        finalization_evaluator: FinalizationEvaluator | None = None,
        finalization_context_provider: FinalizationContextProvider | None = None,
    ) -> None:
        self.context = context
        self.finalization_evaluator = finalization_evaluator
        self.finalization_context_provider = finalization_context_provider
        self.registry = DiscoveryToolRegistry(self._definitions())

    def execute(self, request: ToolCallRequest) -> ToolExecutionResult:
        definition = self.registry.get(request.name)
        if definition is None:
            return self._rejected(
                request,
                ToolBudgetCost(tool_calls=1),
                "unknown_tool",
                f"Tool is not registered: {request.name}",
                ["name"],
            )
        try:
            tool_input = definition.input_model.model_validate(request.arguments)
        except ValidationError as error:
            return self._rejected(
                request,
                definition.estimated_cost,
                "invalid_arguments",
                "Tool arguments do not match the declared schema",
                ["arguments"],
                self._validation_error_context(error),
            )
        try:
            handled = definition.handler(tool_input)
            validated_output = definition.output_model.model_validate(handled.output)
        except BridgerToolError as error:
            return self._rejected(
                request,
                definition.estimated_cost,
                error.payload.error,
                error.payload.message,
                ["arguments"],
                error.payload.details or {},
            )
        except ValidationError as error:
            return self._failed(
                request,
                definition.estimated_cost,
                "invalid_tool_output",
                "Tool returned output outside its declared schema",
                self._validation_error_context(error),
            )
        except Exception:
            return self._failed(
                request,
                definition.estimated_cost,
                "tool_execution_failed",
                "Tool execution failed unexpectedly",
            )
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.COMPLETED,
            output=cast(dict[str, JsonValue], validated_output.model_dump(mode="json")),
            estimated_cost=definition.estimated_cost,
            actual_cost=handled.actual_cost,
            inspection_delta=handled.inspection_delta,
            truncated=handled.truncated,
        )

    def _definitions(self) -> list[DiscoveryToolDefinition]:
        cost = ToolBudgetCost()
        return [
            self._repository(
                "inspect_manifest",
                "Return mechanically parsed facts for an indexed manifest.",
                PathInput,
                ManifestOutput,
                self._inspect_manifest,
                ToolBudgetCost(file_reads=1),
            ),
            self._repository(
                "list_files",
                "List safe indexed files using optional mechanical filters.",
                ListFilesInput,
                RepositoryListingOutput,
                self._list_files,
                cost,
            ),
            self._repository(
                "search_paths",
                "Search safe indexed repository paths by substring.",
                SearchPathsInput,
                RepositoryListingOutput,
                self._search_paths,
                ToolBudgetCost(searches=1),
            ),
            self._repository(
                "grep_contents",
                "Find literal text with line provenance across safe indexed files.",
                GrepContentsInput,
                RepositoryListingOutput,
                self._grep_contents,
                ToolBudgetCost(searches=1),
            ),
            self._repository(
                "read_file_excerpt",
                "Read a bounded, 1-based line excerpt from a safe indexed file.",
                ReadFileExcerptInput,
                FileExcerptOutput,
                self._read_file_excerpt,
                ToolBudgetCost(file_reads=1, excerpts=1),
            ),
            self._repository(
                "list_config_files",
                "List detected safe configuration files and their kinds.",
                EmptyInput,
                RepositoryListingOutput,
                lambda _: self._list_repo_context("config_files"),
                cost,
            ),
            self._repository(
                "list_docs_files",
                "List detected safe documentation files and their kinds.",
                EmptyInput,
                RepositoryListingOutput,
                lambda _: self._list_repo_context("docs_files"),
                cost,
            ),
            self._repository(
                "list_instruction_files",
                "List detected safe instruction files and their kinds.",
                EmptyInput,
                RepositoryListingOutput,
                lambda _: self._list_repo_context("instruction_files"),
                cost,
            ),
            self._repository(
                "search_symbols",
                "Search syntactic symbol names and declarations.",
                SearchSymbolsInput,
                RepositoryListingOutput,
                self._search_symbols,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._repository(
                "list_symbols",
                "List bounded syntactic symbols declared in one safe file.",
                ListSymbolsInput,
                RepositoryListingOutput,
                self._list_symbols,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._repository(
                "get_symbol",
                "Return one syntactic symbol record by stable ID.",
                SymbolIdInput,
                SymbolOutput,
                self._get_symbol,
                ToolBudgetCost(symbol_queries=1),
            ),
            self._repository(
                "validate_paths",
                "Report whether repository-relative paths are safe indexed files.",
                ValidatePathsInput,
                DiscoveryToolOutput,
                self._validate_paths,
                cost,
            ),
            DiscoveryToolDefinition(
                name="request_context_plan_finalization",
                description=(
                    "Submit structured evidence for finalization policy evaluation."
                ),
                input_model=RequestContextPlanFinalizationInput,
                output_model=FinalizationOutput,
                handler=self._request_finalization,
                estimated_cost=cost,
                output_limit=None,
                kind="control",
            ),
        ]

    def _repository(
        self,
        name: str,
        description: str,
        input_model: type[DiscoveryToolInput],
        output_model: type[DiscoveryToolOutput],
        handler: ToolHandler,
        estimated_cost: ToolBudgetCost,
    ) -> DiscoveryToolDefinition:
        return DiscoveryToolDefinition(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            handler=handler,
            estimated_cost=estimated_cost,
            output_limit=self._output_limit(estimated_cost),
            kind="repository",
        )

    def _output_limit(self, cost: ToolBudgetCost) -> int | None:
        budgets = self.context.budgets.values
        if cost.excerpts:
            return budgets.max_file_excerpt_lines
        if cost.searches:
            return budgets.max_grep_results
        if cost.symbol_queries:
            return budgets.max_symbol_results
        return budgets.max_files_read

    def _result(
        self,
        output: dict[str, object],
        actual_cost: ToolBudgetCost,
        inspection_delta: ToolInspectionDelta | None = None,
    ) -> ToolHandlerResult:
        json_output = cast(dict[str, JsonValue], output)
        return ToolHandlerResult(
            output=json_output,
            actual_cost=actual_cost,
            inspection_delta=inspection_delta or ToolInspectionDelta(),
            truncated=bool(output.get("truncated", False)),
        )

    def _list_files(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(ListFilesInput, tool_input)
        output = self.context.file_index.list_files(value.filters)
        return self._result(
            output,
            ToolBudgetCost(),
            ToolInspectionDelta(discovered_paths=self._paths(output.get("files"))),
        )

    def _search_paths(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(SearchPathsInput, tool_input)
        output = self.context.file_index.search_paths(value.query, value.limit)
        paths = self._paths(output.get("files"))
        return self._result(
            output,
            ToolBudgetCost(searches=1),
            ToolInspectionDelta(
                discovered_paths=paths,
                searches_performed=[
                    ContextPlanSearchRecord(
                        tool="search_paths",
                        query=value.query,
                        result_count=cast(int, output["total_matches"]),
                    )
                ],
            ),
        )

    def _grep_contents(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(GrepContentsInput, tool_input)
        output = self.context.search.grep(value.query, value.filters)
        paths = self._paths(output.get("results"))
        return self._result(
            output,
            ToolBudgetCost(searches=1),
            ToolInspectionDelta(
                discovered_paths=paths,
                searches_performed=[
                    ContextPlanSearchRecord(
                        tool="grep_contents",
                        query=value.query,
                        result_count=cast(int, output["total_matches"]),
                    )
                ],
            ),
        )

    def _read_file_excerpt(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(ReadFileExcerptInput, tool_input)
        output = self.context.file_read.read_excerpt(
            value.path, value.start_line, value.end_line
        )
        path = cast(str, output["path"])
        return self._result(
            output,
            ToolBudgetCost(file_reads=1, excerpts=1),
            ToolInspectionDelta(
                evidence_paths=[path],
                excerpts_read=[
                    ContextPlanInspectedExcerpt(
                        path=path,
                        line_start=cast(int, output["line_start"]),
                        line_end=cast(int, output["line_end"]),
                    )
                ],
            ),
        )

    def _inspect_manifest(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(PathInput, tool_input)
        output = self.context.repo_context.inspect_manifest(value.path)
        manifest = cast(dict[str, object], output["manifest"])
        path = cast(str, manifest["path"])
        return self._result(
            output,
            ToolBudgetCost(file_reads=1),
            ToolInspectionDelta(evidence_paths=[path], manifests_inspected=[path]),
        )

    def _list_repo_context(self, field: str) -> ToolHandlerResult:
        service = self.context.repo_context
        method = cast(
            Callable[[], dict[str, object]], getattr(service, f"list_{field}")
        )
        output = method()
        return self._result(
            output,
            ToolBudgetCost(),
            ToolInspectionDelta(discovered_paths=self._paths(output.get(field))),
        )

    def _search_symbols(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(SearchSymbolsInput, tool_input)
        output = self.context.symbols.search(value.query, value.limit)
        return self._result(
            output,
            ToolBudgetCost(symbol_queries=1),
            ToolInspectionDelta(
                discovered_paths=self._paths(output.get("symbols")),
                searches_performed=[
                    ContextPlanSearchRecord(
                        tool="search_symbols",
                        query=value.query,
                        result_count=cast(int, output["total_matches"]),
                    )
                ],
            ),
        )

    def _list_symbols(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(ListSymbolsInput, tool_input)
        output = self.context.symbols.list_for_path(value.path, value.limit)
        symbols = self._symbols(output.get("symbols"))
        return self._result(
            output,
            ToolBudgetCost(symbol_queries=1),
            ToolInspectionDelta(
                evidence_paths=[value.path],
                symbols_inspected=symbols,
            ),
        )

    def _get_symbol(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(SymbolIdInput, tool_input)
        output = self.context.symbols.get_result(value.symbol_id)
        symbol = cast(dict[str, object], output["symbol"])
        path = cast(str, symbol["path"])
        return self._result(
            output,
            ToolBudgetCost(symbol_queries=1),
            ToolInspectionDelta(
                evidence_paths=[path], symbols_inspected=self._symbols([symbol])
            ),
        )

    def _validate_paths(self, tool_input: BaseModel) -> ToolHandlerResult:
        value = cast(ValidatePathsInput, tool_input)
        return self._result(
            self.context.file_index.validate_paths(value.paths), ToolBudgetCost()
        )

    def _request_finalization(self, tool_input: BaseModel) -> ToolHandlerResult:
        if (
            self.finalization_evaluator is None
            or self.finalization_context_provider is None
        ):
            raise BridgerToolError(
                "finalization_unavailable",
                "Finalization evaluation is not configured for this executor",
            )
        request = cast(RequestContextPlanFinalizationInput, tool_input)
        decision = self.finalization_evaluator.evaluate(
            request, self.finalization_context_provider()
        )
        return self._result(
            {"decision": decision.model_dump(mode="json")}, ToolBudgetCost()
        )

    def _paths(self, values: object, key: str = "path") -> list[str]:
        if not isinstance(values, list):
            return []
        return [
            value[key]
            for value in values
            if isinstance(value, dict) and isinstance(value.get(key), str)
        ]

    def _symbols(self, values: object) -> list[ContextPlanInspectedSymbol]:
        if not isinstance(values, list):
            return []
        result: list[ContextPlanInspectedSymbol] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            identifier = value.get("id")
            path = value.get("path")
            if isinstance(identifier, str) and isinstance(path, str):
                result.append(
                    ContextPlanInspectedSymbol(identifier=identifier, path=path)
                )
        return result

    def _rejected(
        self,
        request: ToolCallRequest,
        estimated_cost: ToolBudgetCost,
        code: str,
        message: str,
        location: list[str | int],
        context: dict[str, JsonValue] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.REJECTED,
            issues=[self._issue(code, message, location, context)],
            estimated_cost=estimated_cost,
            actual_cost=ToolBudgetCost(tool_calls=0),
        )

    def _failed(
        self,
        request: ToolCallRequest,
        estimated_cost: ToolBudgetCost,
        code: str,
        message: str,
        context: dict[str, JsonValue] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            call_id=request.call_id,
            tool_name=request.name,
            status=ToolExecutionStatus.FAILED,
            issues=[self._issue(code, message, ["execution"], context)],
            estimated_cost=estimated_cost,
            actual_cost=ToolBudgetCost(tool_calls=1),
        )

    def _issue(
        self,
        code: str,
        message: str,
        location: list[str | int],
        context: dict[str, JsonValue] | None = None,
    ) -> ContextPlanValidationIssue:
        return ContextPlanValidationIssue(
            code=code, location=location, message=message, context=context or {}
        )

    def _validation_error_context(self, error: ValidationError) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], {"errors": json.loads(error.json())})


def tool_call_request_from_llm_call(tool_call: LLMToolCall) -> ToolCallRequest:
    return ToolCallRequest(
        call_id=tool_call.id, name=tool_call.name, arguments=tool_call.arguments
    )


def tool_result_to_llm_message(result: ToolExecutionResult) -> LLMMessage:
    payload: dict[str, JsonValue] = {
        "status": result.status.value,
        "output": result.output,
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
        "truncated": result.truncated,
    }
    return LLMMessage.tool_result_message(
        tool_call_id=result.call_id,
        tool_name=result.tool_name,
        result=payload,
        failed=result.status is not ToolExecutionStatus.COMPLETED,
    )
