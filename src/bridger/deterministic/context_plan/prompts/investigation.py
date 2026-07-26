"""Investigation continuation prompt for Context Plan discovery."""

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    InvestigationPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import (
    build_system_message,
    render_json_section,
    render_tool_catalog,
    sorted_paths,
    sorted_strings,
    sorted_tools,
)
from bridger.llm.models import LLMMessage


def build_investigation_prompt(input: InvestigationPromptInput) -> ContextPlanPrompt:
    """Build a tools-enabled continuation without evaluating finalization policy."""

    tools = sorted_tools(input.available_tools)
    latest_results = sorted(
        input.latest_tool_results,
        key=lambda result: (result.call_id, result.tool_name),
    )
    findings = _working_state_entities(input, "findings")
    relationships = _working_state_entities(input, "relationships")
    questions = _working_state_entities(input, "open_questions")
    candidates = _working_state_entities(input, "package_candidates")
    recent_evidence = _working_state_entities(input, "recent_evidence")
    sections = [
        """Continue repository investigation.

Use the supplied state to identify the highest-value unresolved semantic area. Prefer
investigations that:

* advance a principal workflow beyond its current endpoint, symbol, or first-file
  boundary;
* connect construction to runtime behaviour;
* follow calls, usages, outputs, and downstream handoffs;
* establish state ownership, persistence, integrations, failures, or tests;
* resolve contradictions affecting package accuracy;
* strengthen a central package candidate that currently relies on weak evidence.""",
        _durable_working_state_policy(),
        render_json_section("Latest structured tool results", latest_results),
        render_json_section(
            "Semantic coverage summary",
            {
                "coverage_basis": (
                    "run inspection and durable represented areas; semantic "
                    "dimensions are not separately modeled"
                ),
                "inspection": input.inspection,
                "working_state": input.working_state_summary,
            },
        ),
        render_json_section(
            "Major workflow stage coverage",
            {
                "coverage_basis": (
                    "durable findings, relationships, and package candidates; "
                    "workflow stages are not separately modeled"
                ),
                "findings": findings,
                "relationships": relationships,
                "package_candidates": candidates,
            },
        ),
        render_json_section(
            "Central files and inspection depth",
            {
                "coverage_basis": (
                    "run inspection; centrality is not separately modeled"
                ),
                "inspection": input.inspection,
            },
        ),
        render_json_section(
            "Symbol-only and partially inspected central evidence",
            {
                "coverage_basis": "recent durable evidence only",
                "evidence": _weak_evidence(recent_evidence),
            },
        ),
        render_json_section("Discovered paths", sorted_paths(input.discovered_paths)),
        render_json_section(
            "Evidence ledger summary",
            {
                "evidence_paths": sorted_paths(input.evidence_paths),
                "recent_evidence": recent_evidence,
                "working_state": input.working_state_summary,
            },
        ),
        render_json_section("Established findings", findings),
        render_json_section("Relationships", relationships),
        render_json_section("Package candidates and evidence strength", candidates),
        render_json_section(
            "Open questions and contradictions",
            {
                "durable_questions": questions,
                "runtime_questions": sorted_strings(input.open_questions),
            },
        ),
        render_json_section(
            "Justified exclusions and inaccessible areas",
            _justified_exclusions(questions),
        ),
        render_json_section("Remaining budgets", input.remaining_budgets),
        render_json_section(
            "Runtime warnings and diagnostics", sorted_strings(input.warnings)
        ),
        render_json_section(
            "Investigation notes", sorted_strings(input.investigation_notes)
        ),
        *(_finalization_rejection_sections(latest_results, input) or []),
        render_tool_catalog(list(tools)),
        _investigation_operating_loop(),
        _finalization_policy(),
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    """Continue bounded repository investigation using semantic
coverage gaps as the primary prioritization signal.

Durable working state is the authoritative record of established understanding.
Conversation history is auxiliary context and must not be the only location where
important evidence or conclusions remain.

Open questions are not merely advisory. A high-priority question blocks finalization
when it concerns a major subsystem or workflow, remains answerable with available
tools, and can reasonably be investigated within the remaining budget.

Do not relabel an answerable gap as an unknown solely to permit finalization."""
                )
            ),
            *input.interaction_history,
            LLMMessage.user("\n\n".join(sections)),
        ),
        tools=tools,
    )


def _working_state_entities(
    input: InvestigationPromptInput,
    name: str,
) -> list[object]:
    value = input.working_state_entities.get(name, [])
    return list(value) if isinstance(value, list) else []


def _weak_evidence(recent_evidence: list[object]) -> list[object]:
    weak_levels = {"discovered", "located", "symbol_only", "line_observed"}
    return [
        item
        for item in recent_evidence
        if isinstance(item, dict) and item.get("inspection_level") in weak_levels
    ]


def _justified_exclusions(questions: list[object]) -> list[object]:
    return [
        item
        for item in questions
        if isinstance(item, dict)
        and item.get("status") in {"unanswerable", "resolved"}
        and item.get("resolution")
    ]


def _finalization_rejection_sections(
    latest_results: list[object],
    input: InvestigationPromptInput,
) -> list[str] | None:
    issues: list[object] = []
    for result in latest_results:
        if getattr(result, "tool_name", None) != "request_context_plan_finalization":
            continue
        output = getattr(result, "output", None)
        if not isinstance(output, dict):
            continue
        decision = output.get("decision")
        if not isinstance(decision, dict) or decision.get("accepted") is not False:
            continue
        raw_issues = decision.get("issues", [])
        if isinstance(raw_issues, list):
            issues.extend(raw_issues)
    if not issues:
        return None

    weak_evidence_reasons = [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and issue.get("code")
        in {
            "uninspected_evidence_path",
            "unknown_evidence_path",
            "unsafe_evidence_path",
            "skipped_evidence_path",
        }
    ]
    feedback = {
        "rejected_coverage_areas": issues,
        "incomplete_workflow_stages": [],
        "weak_evidence_reasons": weak_evidence_reasons,
        "unsupported_package_candidates": [],
        "blocking_open_questions": sorted_strings(input.open_questions),
        "required_next_investigations": _required_investigations(issues),
    }
    return [
        """Finalization was rejected because the current evidence does not yet
satisfy semantic completion policy.

Address the listed gaps through targeted investigation. Do not repeat already
sufficient exploration and do not broaden into unrelated repository areas.

For each rejected item, determine whether to:

* inspect implementation;
* follow a caller, usage, or handoff;
* inspect persistence or external integration behaviour;
* inspect failure or retry handling;
* inspect relevant tests;
* document a justified exclusion or genuine unknown.

Update durable state before requesting finalization again.""",
        render_json_section("Structured finalization rejection feedback", feedback),
    ]


def _required_investigations(issues: list[object]) -> list[str]:
    codes = {
        str(issue.get("code"))
        for issue in issues
        if isinstance(issue, dict) and issue.get("code") is not None
    }
    investigations: list[str] = []
    if codes & {
        "uninspected_evidence_path",
        "unknown_evidence_path",
        "unsafe_evidence_path",
        "skipped_evidence_path",
    }:
        investigations.extend(
            [
                "validate candidate evidence paths",
                "inspect implementation for package-critical evidence",
            ]
        )
    if not investigations:
        investigations.append("address each reported finalization issue")
    return investigations


def _durable_working_state_policy() -> str:
    return """Durable working-state policy

Use the working-state tools to preserve high-signal repository understanding
independently of conversation history.

Repository read tools produce evidence. Working-state tools organize that evidence
into durable facts, relationships, questions, and package hypotheses.

Do not use working-state tools as an unstructured scratchpad. Record information
after a coherent evidence batch, not after every search or file listing.

Every durable behavioural finding must reference the stable evidence IDs that support
it. Do not reference paths alone when exact evidence records are available.

Finding lifecycle

Use record_finding when inspected evidence establishes one clear factual claim about
the repository. A finding should express one atomic, reusable fact; distinguish
confirmed behaviour from interpretation; cite all material supporting evidence IDs;
be narrow enough for later evidence to refine or contradict it; and identify its
relevant subsystem, workflow, contract, convention, or concern where supported.

Use refine_finding when new evidence clarifies, narrows, or strengthens the same
underlying fact. Use supersede_finding when a previous finding is contradicted,
obsolete, or replaced by a materially different conclusion. Do not silently preserve
both as simultaneously valid.

Do not record unsupported architectural hypotheses, raw symbol lists, file-presence
observations with no downstream value, duplicate findings, or assumptions inferred
only from naming or directory structure.

Relationship lifecycle

Use record_relationship when evidence establishes a meaningful connection between
repository entities, such as constructs or initializes; calls or dispatches to; owns
state for; reads from or persists to; configures; implements a contract; triggers or
hands off to; retries or recovers through; or is demonstrated by a test.

Relationships must cite supporting evidence IDs. Do not record a relationship merely
because two files import each other or appear in the same directory unless that
structural relationship is itself relevant.

Question lifecycle

Use open_question when evidence is contradictory; a major workflow stage remains
unresolved; an important relationship is suspected but unverified; a package claim
depends on missing evidence; or a meaningful repository fact appears inaccessible or
absent.

Questions should be precise and actionable. Identify what is unknown, why it matters,
and what investigation could resolve it. Use resolve_question when evidence answers
the question or when it is reclassified as a justified absence, exclusion, access
limitation, or budget-limited unknown. Do not resolve a question merely because
investigation is inconvenient or to enable finalization.

Package-candidate lifecycle

Use create_package_candidate when several findings and relationships begin to form
one coherent downstream concern, subsystem, workflow, contract, convention, or
operational area.

A package candidate should define one clear purpose; the findings and relationships
it intends to preserve; its supporting evidence; its current gaps or weak evidence;
and whether it is ready, partial, overlapping, or uncertain where the tool contract
supports such state.

Use update_package_candidate as evidence is added, claims are narrowed, ordering
becomes clearer, or gaps are resolved. Use merge_package_candidates when candidates
substantially overlap. Use discard_package_candidate when a candidate is unsupported,
redundant, incorrectly scoped, or no longer useful. Use restore_package_candidate only
when new evidence makes a discarded concern valid again.

Package candidates are hypotheses for synthesis, not canonical output. Their contents
must continue to evolve with the evidence."""


def _investigation_operating_loop() -> str:
    return """Follow this operating loop:

1. inspect current semantic and workflow coverage;
2. select the highest-value unresolved gap;
3. inspect relevant symbols or targeted implementation ranges;
4. follow usages, callers, integrations, persistence, and handoffs through search;
5. externalize the coherent evidence batch by recording or refining findings,
   recording material relationships, opening or resolving questions, and updating,
   merging, narrowing, or discarding package candidates;
6. ensure every durable claim references stable evidence IDs;
7. update coverage truthfully and repeat until finalization criteria are satisfied or
   remaining gaps are justified.

After each coherent evidence batch, externalize durable state. Do not defer findings
and relationships until finalization.

For central files, use file overviews and symbol lists to select relevant regions,
inspect complete symbol bodies or targeted ranges, continue important truncated
reads, and do not treat symbol-only or beginning-of-file evidence as substantive
inspection.

Package candidates should evolve incrementally. A candidate is not final merely
because it contains several paths.

Selective exploration is expected. Do not inspect every file, but do not omit an
important subsystem merely because one representative file was inspected."""


def _finalization_policy() -> str:
    return """Choose repository tool calls, state-management tool calls, or
request_context_plan_finalization.

Finalization is appropriate only after performing a pre-finalization check:

* concrete entrypoints and construction paths have been investigated;
* each principal workflow has been followed beyond ingress or a central symbol;
* major subsystems have implementation evidence;
* relevant configuration, state, persistence, integrations, outputs, and failure
  behaviour are covered or precisely justified;
* conventions and testing have been investigated;
* central package candidates do not rely primarily on symbol-only evidence;
* important truncated or partially inspected files have received targeted
  continuation where needed;
* remaining high-priority questions are unanswerable, inaccessible, intentionally
  excluded, or unreasonable within policy limits;
* proposed packages are sufficient for bounded downstream agents without broad
  repository rediscovery.

A finalization request must provide proposed package candidates, a semantic coverage
summary, stage-level coverage of principal workflows, incomplete areas, justified
exclusions, unresolved high-priority questions, and a brief evidence-based sufficiency
rationale, using the fields supported by the structured control tool.

Requesting finalization does not determine whether it will be accepted. Use the
structured control tool and never return a prose final answer."""
