from datetime import UTC, datetime
from pathlib import Path

import pytest

from bridger.deterministic.context_plan.control_tools import (
    WorkingStateOperationExecutor,
)
from bridger.deterministic.context_plan.evidence import EvidenceExtractor
from bridger.deterministic.context_plan.working_state import (
    WorkingStateMutationService,
    WorkingStateStore,
)
from bridger.models.context_plan import (
    ToolBudgetCost,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from bridger.models.working_state import (
    ContextPlanWorkingState,
    EvidenceKind,
    FileInspectionStatus,
    FindingStatus,
    PackageCandidateStatus,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def completed_result(
    tool_name: str,
    output: dict[str, object],
    *,
    call_id: str = "call-1",
) -> ToolExecutionResult:
    return ToolExecutionResult.model_validate(
        {
            "call_id": call_id,
            "tool_name": tool_name,
            "status": ToolExecutionStatus.COMPLETED,
            "output": output,
            "estimated_cost": ToolBudgetCost(),
            "actual_cost": ToolBudgetCost(),
        }
    )


def make_service(tmp_path: Path) -> WorkingStateMutationService:
    return WorkingStateMutationService(
        ContextPlanWorkingState(run_id="run-1", updated_at=NOW),
        WorkingStateStore(tmp_path / "context-plan-working-state.json"),
        total_lines_by_path={"src/app.py": 100},
    )


@pytest.mark.parametrize(
    ("tool_name", "output", "expected_kind"),
    [
        (
            "read_file_excerpt",
            {
                "source_artifact": "file-index",
                "path": "src/app.py",
                "line_start": 3,
                "line_end": 4,
                "content": "def main():\n    pass",
                "truncated": False,
            },
            EvidenceKind.FILE_EXCERPT,
        ),
        (
            "grep_contents",
            {
                "source_artifact": "file-index",
                "results": [
                    {"path": "src/app.py", "line_number": 3, "match": "def main"}
                ],
                "total_matches": 1,
                "limit_applied": 10,
                "truncated": False,
            },
            EvidenceKind.SEARCH_HIT,
        ),
        (
            "get_symbol",
            {
                "source_artifact": "symbol-index",
                "symbol": {
                    "id": "sym:src/app.py:3:main",
                    "path": "src/app.py",
                    "line_start": 3,
                    "line_end": 4,
                    "declaration": "def main()",
                },
            },
            EvidenceKind.SYMBOL_METADATA,
        ),
        (
            "inspect_manifest",
            {
                "source_artifact": "repo-context",
                "manifest": {
                    "path": "pyproject.toml",
                    "kind": "python_pyproject",
                    "parsed": {"project_name": "fixture"},
                },
            },
            EvidenceKind.MANIFEST_FACT,
        ),
        (
            "get_graph_neighbors",
            {
                "source_artifact": "repo-graph",
                "neighbors": [
                    {
                        "path": "src/worker.py",
                        "kind": "imports",
                        "direction": "outgoing",
                    }
                ],
                "total_matches": 1,
                "limit_applied": 10,
                "truncated": False,
            },
            EvidenceKind.GRAPH_RELATIONSHIP,
        ),
        (
            "list_declared_entrypoints",
            {
                "source_artifact": "repo-graph",
                "entrypoints": [
                    {"path": "src/app.py", "source": "pyproject.toml:project.scripts"}
                ],
                "total_matches": 1,
                "limit_applied": 10,
                "truncated": False,
            },
            EvidenceKind.ENTRYPOINT_FACT,
        ),
        (
            "list_files",
            {
                "source_artifact": "file-index",
                "files": [{"path": "src/app.py", "line_count": 100}],
                "total_matches": 1,
                "limit_applied": 10,
                "truncated": False,
            },
            EvidenceKind.FILE_METADATA,
        ),
        (
            "inspect_repo_discovery",
            {"repo": {"root_name": "fixture"}, "truncated": False},
            EvidenceKind.REPOSITORY_FACT,
        ),
    ],
)
def test_evidence_extraction_preserves_tool_meaning(
    tool_name: str,
    output: dict[str, object],
    expected_kind: EvidenceKind,
) -> None:
    records = EvidenceExtractor().extract(completed_result(tool_name, output))

    assert records
    assert records[0].kind is expected_kind


def test_stable_ids_deduplicate_repeated_results(tmp_path: Path) -> None:
    extractor = EvidenceExtractor()
    first = completed_result(
        "read_file_excerpt",
        {
            "source_artifact": "file-index",
            "path": "src/app.py",
            "line_start": 1,
            "line_end": 2,
            "content": "one\ntwo",
            "truncated": False,
        },
        call_id="provider-call-a",
    )
    second = first.model_copy(update={"call_id": "provider-call-b"})
    first_records = extractor.extract(first)
    second_records = extractor.extract(second)
    service = make_service(tmp_path)

    service.apply_evidence(first_records, now=NOW)
    service.apply_evidence(second_records, now=NOW)

    assert first_records[0].evidence_id == second_records[0].evidence_id
    assert len(service.state.evidence) == 1


def test_ranges_merge_but_symbol_metadata_stays_symbol_only(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    extractor = EvidenceExtractor()
    for start, end in [(10, 20), (20, 25), (26, 30)]:
        content = "\n".join(str(line) for line in range(start, end + 1))
        service.apply_evidence(
            extractor.extract(
                completed_result(
                    "read_file_excerpt",
                    {
                        "source_artifact": "file-index",
                        "path": "src/app.py",
                        "line_start": start,
                        "line_end": end,
                        "content": content,
                        "truncated": False,
                    },
                    call_id=f"read-{start}",
                )
            ),
            now=NOW,
        )

    inspected = service.state.inspected_files[0]
    assert [
        (item.line_start, item.line_end) for item in inspected.inspected_ranges
    ] == [(10, 30)]
    assert inspected.observed_lines == 21
    assert inspected.inspection_status is FileInspectionStatus.PARTIALLY_INSPECTED

    symbol_service = WorkingStateMutationService(
        ContextPlanWorkingState(run_id="run-symbol", updated_at=NOW),
        WorkingStateStore(tmp_path / "symbol-state.json"),
    )
    symbol_service.apply_evidence(
        extractor.extract(
            completed_result(
                "list_symbols",
                {
                    "source_artifact": "symbol-index",
                    "symbols": [
                        {
                            "id": "sym:src/app.py:3:main",
                            "path": "src/app.py",
                            "line_start": 3,
                            "line_end": 4,
                            "declaration": "def main()",
                        }
                    ],
                    "total_matches": 1,
                    "limit_applied": 10,
                    "truncated": False,
                },
            )
        ),
        now=NOW,
    )

    symbol_state = symbol_service.state.inspected_files[0]
    assert symbol_state.inspection_status is FileInspectionStatus.SYMBOL_ONLY
    assert symbol_state.symbol_ids_seen == ["sym:src/app.py:3:main"]
    assert symbol_state.inspected_ranges == []


def test_findings_validate_references_and_candidate_lifecycle(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    extractor = EvidenceExtractor()
    records = extractor.extract(
        completed_result(
            "read_file_excerpt",
            {
                "source_artifact": "file-index",
                "path": "src/app.py",
                "line_start": 1,
                "line_end": 2,
                "content": "one\ntwo",
                "truncated": False,
            },
        )
    )
    service.apply_evidence(records, now=NOW)
    executor = WorkingStateOperationExecutor(service)

    rejected = executor.execute(
        "record_finding",
        {
            "statement": "The application starts here.",
            "evidence_ids": ["ev." + "0" * 64],
            "area_key": "runtime",
            "confidence": 0.9,
        },
    )
    assert rejected.status == "rejected"
    assert service.state.findings == []

    recorded = executor.execute(
        "record_finding",
        {
            "statement": "The application starts here.",
            "evidence_ids": [records[0].evidence_id],
            "area_key": "runtime",
            "confidence": 0.9,
        },
    )
    finding_id = recorded.entity_ids[0]
    refined = executor.execute(
        "refine_finding",
        {
            "finding_id": finding_id,
            "statement": "The application entrypoint starts here.",
            "evidence_ids": [records[0].evidence_id],
            "area_key": "runtime",
            "confidence": 0.95,
        },
    )
    refined_id = refined.entity_ids[0]
    assert {item.finding_id: item.status for item in service.state.findings}[
        finding_id
    ] is FindingStatus.SUPERSEDED

    created = executor.execute(
        "create_package_candidate",
        {
            "title": "Application runtime",
            "purpose": "Trace application startup.",
            "area_keys": ["runtime"],
            "finding_ids": [refined_id],
            "evidence_ids": [records[0].evidence_id],
            "question_ids": [],
            "priority": 1,
        },
    )
    candidate_id = created.entity_ids[0]
    updated = executor.execute(
        "update_package_candidate",
        {
            "candidate_id": candidate_id,
            "purpose": "Trace the confirmed application startup.",
        },
    )
    second = executor.execute(
        "create_package_candidate",
        {
            "title": "Runtime helper",
            "purpose": "Explain runtime support.",
            "area_keys": ["runtime"],
            "finding_ids": [refined_id],
            "evidence_ids": [records[0].evidence_id],
            "question_ids": [],
            "priority": 2,
        },
    )
    merged = executor.execute(
        "merge_package_candidates",
        {
            "source_candidate_ids": [second.entity_ids[0]],
            "target_candidate_id": candidate_id,
        },
    )
    discarded = executor.execute(
        "discard_package_candidate", {"candidate_id": candidate_id}
    )
    restored = executor.execute(
        "restore_package_candidate", {"candidate_id": candidate_id}
    )

    assert updated.status == "completed"
    assert merged.status == "completed"
    assert discarded.status == "completed"
    assert restored.status == "completed"
    statuses = {
        item.candidate_id: item.status for item in service.state.package_candidates
    }
    assert statuses[candidate_id] is PackageCandidateStatus.ACTIVE
    assert statuses[second.entity_ids[0]] is PackageCandidateStatus.MERGED
    assert (tmp_path / "context-plan-working-state.json").is_file()
    assert service.store.checksum is not None
    assert service.store.load() == service.state


def test_relationships_and_questions_are_evidence_backed_and_resolvable(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    records = EvidenceExtractor().extract(
        completed_result(
            "grep_contents",
            {
                "source_artifact": "file-index",
                "results": [
                    {
                        "path": "src/app.py",
                        "line_number": 4,
                        "match": "worker.run()",
                    }
                ],
                "total_matches": 1,
                "limit_applied": 10,
                "truncated": False,
            },
        )
    )
    service.apply_evidence(records, now=NOW)
    executor = WorkingStateOperationExecutor(service)

    relationship = executor.execute(
        "record_relationship",
        {
            "source_entity": "App",
            "relationship_type": "starts",
            "target_entity": "Worker",
            "evidence_ids": [records[0].evidence_id],
            "confidence": 0.8,
            "area_key": "worker",
        },
    )
    question = executor.execute(
        "open_question",
        {
            "question": "Where is the worker stopped?",
            "area_key": "worker",
            "related_evidence_ids": [records[0].evidence_id],
            "priority": 1,
        },
    )
    resolved = executor.execute(
        "resolve_question",
        {
            "question_id": question.entity_ids[0],
            "resolution": "The current evidence does not show shutdown.",
            "resolution_evidence_ids": [records[0].evidence_id],
            "status": "unanswerable",
        },
    )

    assert relationship.status == "completed"
    assert resolved.status == "completed"
    assert service.state.open_questions[0].status.value == "unanswerable"
