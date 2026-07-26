from datetime import UTC, datetime

import pytest

from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanRunStatus,
    FinalizationContext,
    FinalizationDecisionCode,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)
from bridger.tools.services.path_safety import PathSafetyService


def make_policy() -> ContextPlanCompletionPolicy:
    file_index = FileIndexArtifact(
        generated_at=datetime(2026, 7, 23, tzinfo=UTC),
        repo_root_name="example",
        files=[
            IndexedFile(
                path="src/main.py",
                extension=".py",
                size_bytes=10,
                line_count=2,
                sha256="0" * 64,
                is_binary=False,
                is_symlink=False,
                detected_encoding="utf-8",
            )
        ],
        skipped_files=[SkippedFile(path=".env", skip_reason=SkipReason.SENSITIVE_FILE)],
        stats=FileIndexStats(
            files_seen=2,
            files_included=1,
            files_skipped=1,
            total_included_bytes=10,
        ),
    )
    return ContextPlanCompletionPolicy(PathSafetyService(file_index))


def make_request(paths: list[str] | None = None) -> ContextPlanFinalizationRequest:
    return ContextPlanFinalizationRequest(
        explored_areas=["entrypoint"],
        key_evidence_paths=paths or ["src/main.py"],
        unresolved_areas=[],
        sufficiency_reason="The inspected evidence is sufficient for synthesis.",
    )


def make_context(
    *,
    status: ContextPlanRunStatus = ContextPlanRunStatus.RUNNING,
    evidence_paths: list[str] | None = None,
    stalled: bool = False,
    hard_budget_exhausted: bool = False,
) -> FinalizationContext:
    return FinalizationContext(
        run_status=status,
        stalled=stalled,
        hard_budget_exhausted=hard_budget_exhausted,
        evidence_paths=(["src/main.py"] if evidence_paths is None else evidence_paths),
        finalization_request_count=0,
    )


def test_accepts_grounded_request_for_active_run() -> None:
    decision = make_policy().evaluate(make_request(), make_context())

    assert decision.accepted is True
    assert decision.code is FinalizationDecisionCode.ACCEPTED
    assert decision.issues == []


def test_rejects_structurally_invalid_request() -> None:
    decision = make_policy().evaluate({}, make_context())

    assert decision.accepted is False
    assert decision.code is FinalizationDecisionCode.INVALID_REQUEST
    assert {issue.code for issue in decision.issues} == {"invalid_request"}


@pytest.mark.parametrize(
    ("path", "expected_code", "expected_issue"),
    [
        (
            "/etc/passwd",
            FinalizationDecisionCode.UNSAFE_EVIDENCE_PATH,
            "unsafe_evidence_path",
        ),
        (
            "unknown.py",
            FinalizationDecisionCode.UNKNOWN_EVIDENCE_PATH,
            "unknown_evidence_path",
        ),
        (
            ".env",
            FinalizationDecisionCode.UNSAFE_EVIDENCE_PATH,
            "skipped_evidence_path",
        ),
    ],
)
def test_rejects_invalid_evidence_paths(
    path: str,
    expected_code: FinalizationDecisionCode,
    expected_issue: str,
) -> None:
    request = make_request(["src/main.py"])
    request.key_evidence_paths = [path]

    decision = make_policy().evaluate(request, make_context())

    assert decision.accepted is False
    assert decision.code is expected_code
    assert [issue.code for issue in decision.issues] == [expected_issue]


def test_rejects_discovered_only_path_as_uninspected() -> None:
    decision = make_policy().evaluate(make_request(), make_context(evidence_paths=[]))

    assert decision.accepted is False
    assert decision.code is FinalizationDecisionCode.UNINSPECTED_EVIDENCE_PATH
    assert [issue.code for issue in decision.issues] == ["uninspected_evidence_path"]


@pytest.mark.parametrize(
    ("status", "stalled", "exhausted", "expected_code"),
    [
        (
            ContextPlanRunStatus.STALLED,
            False,
            False,
            FinalizationDecisionCode.RUN_STALLED,
        ),
        (
            ContextPlanRunStatus.FAILED,
            False,
            False,
            FinalizationDecisionCode.RUN_FAILED,
        ),
        (
            ContextPlanRunStatus.INTERRUPTED,
            False,
            False,
            FinalizationDecisionCode.RUN_NOT_SYNTHESIZABLE,
        ),
        (
            ContextPlanRunStatus.COMPLETED,
            False,
            False,
            FinalizationDecisionCode.RUN_NOT_SYNTHESIZABLE,
        ),
        (
            ContextPlanRunStatus.BUDGET_EXHAUSTED,
            False,
            False,
            FinalizationDecisionCode.BUDGET_EXHAUSTED,
        ),
        (
            ContextPlanRunStatus.RUNNING,
            True,
            False,
            FinalizationDecisionCode.RUN_STALLED,
        ),
        (
            ContextPlanRunStatus.RUNNING,
            False,
            True,
            FinalizationDecisionCode.BUDGET_EXHAUSTED,
        ),
    ],
)
def test_rejects_non_synthesizable_runs(
    status: ContextPlanRunStatus,
    stalled: bool,
    exhausted: bool,
    expected_code: FinalizationDecisionCode,
) -> None:
    decision = make_policy().evaluate(
        make_request(),
        make_context(
            status=status,
            stalled=stalled,
            hard_budget_exhausted=exhausted,
        ),
    )

    assert decision.accepted is False
    assert decision.code is expected_code


def test_returns_all_invalid_evidence_path_issues() -> None:
    request = make_request(["src/main.py"])
    request.key_evidence_paths = ["unknown.py", ".env"]

    decision = make_policy().evaluate(request, make_context())

    assert [issue.code for issue in decision.issues] == [
        "unknown_evidence_path",
        "skipped_evidence_path",
    ]


def test_does_not_apply_semantic_or_file_count_thresholds() -> None:
    request = ContextPlanFinalizationRequest(
        explored_areas=["one area"],
        key_evidence_paths=["src/main.py"],
        unresolved_areas=["not inspected"],
        sufficiency_reason="Enough factual evidence is available.",
    )

    decision = make_policy().evaluate(request, make_context())

    assert decision.accepted is True
