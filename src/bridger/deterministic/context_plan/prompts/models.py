"""Typed, provider-independent inputs and outputs for Context Plan prompts."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from bridger.deterministic.context_plan.discovery_tools import FileExcerptOutput
from bridger.deterministic.context_plan.run_state import DiscoveryBudgetLimits
from bridger.llm.models import LLMMessage, LLMToolDefinition
from bridger.models.context_plan import (
    ContextPlan,
    ContextPlanExclusion,
    ContextPlanInspectedSymbol,
    ContextPlanRunInspection,
    ContextPlanValidationIssue,
    ToolExecutionResult,
)
from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    GraphSummaryArtifact,
)
from bridger.models.repo_context import ManifestFile, RepoContextArtifact
from bridger.models.repo_discovery import RepoDiscoveryArtifact
from bridger.models.repository_path import RepositoryPath
from bridger.models.synthesis_manifest import SynthesisInputManifest
from bridger.models.working_state import (
    ContextPlanWorkingStateSummary,
    EstablishedFinding,
    EvidenceRecord,
    OpenQuestion,
    PackageCandidate,
    RelationshipRecord,
)


class ContextPlanPromptInput(BaseModel):
    """Shared input boundary for prompt builders, not runtime state."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ContextPlanPrompt:
    """A provider-neutral prompt payload for one Context Plan model turn."""

    messages: tuple[LLMMessage, ...]
    tools: tuple[LLMToolDefinition, ...] = ()
    output_type: type[ContextPlan] | None = None


class OrientationPromptInput(ContextPlanPromptInput):
    repository_bootstrap: RepoDiscoveryArtifact
    repository_context: RepoContextArtifact | None = None
    graph_summary: GraphSummaryArtifact | None = None
    available_tools: list[LLMToolDefinition] = Field(default_factory=list)
    run_budget_limits: DiscoveryBudgetLimits | None = None
    initial_warnings: list[str] = Field(default_factory=list)


class InvestigationPromptInput(ContextPlanPromptInput):
    interaction_history: list[LLMMessage] = Field(default_factory=list)
    latest_tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    inspection: ContextPlanRunInspection
    discovered_paths: list[RepositoryPath] = Field(default_factory=list)
    evidence_paths: list[RepositoryPath] = Field(default_factory=list)
    remaining_budgets: dict[str, int | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    investigation_notes: list[str] = Field(default_factory=list)
    working_state_summary: ContextPlanWorkingStateSummary | None = None
    working_state_entities: dict[str, JsonValue] = Field(default_factory=dict)
    available_tools: list[LLMToolDefinition] = Field(default_factory=list)


class FinalSynthesisPromptInput(ContextPlanPromptInput):
    """Already validated evidence selected by the future orchestration layer."""

    repository_bootstrap: RepoDiscoveryArtifact
    validated_evidence_paths: list[RepositoryPath] = Field(default_factory=list)
    inspected_excerpts: list[FileExcerptOutput] = Field(default_factory=list)
    inspected_symbols: list[ContextPlanInspectedSymbol] = Field(default_factory=list)
    manifest_evidence: list[ManifestFile] = Field(default_factory=list)
    graph_evidence: GraphSummaryArtifact | None = None
    collected_findings: list[str] = Field(default_factory=list)
    confirmed_entrypoints: list[DeclaredEntrypointSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    intentionally_excluded: list[ContextPlanExclusion] = Field(default_factory=list)
    synthesis_manifest: SynthesisInputManifest | None = None
    selected_candidates: list[PackageCandidate] = Field(default_factory=list)
    selected_findings: list[EstablishedFinding] = Field(default_factory=list)
    selected_relationships: list[RelationshipRecord] = Field(default_factory=list)
    selected_questions: list[OpenQuestion] = Field(default_factory=list)
    selected_evidence: list[EvidenceRecord] = Field(default_factory=list)


class ContextPlanRepairPromptInput(ContextPlanPromptInput):
    """One invalid candidate and the unchanged synthesis evidence boundary."""

    invalid_output: JsonValue
    validation_issues: list[ContextPlanValidationIssue] = Field(min_length=1)
    synthesis_evidence: FinalSynthesisPromptInput
