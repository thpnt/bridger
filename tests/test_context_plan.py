import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import bridger.deterministic.context_plan.validation as context_plan_validation
from bridger.artifacts import writer as artifact_writer
from bridger.deterministic.context_plan import (
    ContextPlanValidationError,
    serialize_context_plan,
    validate_context_plan,
    write_context_plan,
)
from bridger.deterministic.context_plan_bootstrap.checksums import sha256_file
from bridger.models.context_plan import (
    ContextPlan,
    ContextPlanFinalizationRequest,
    ContextPlanRun,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)


def make_file_index() -> FileIndexArtifact:
    return FileIndexArtifact(
        generated_at=datetime(2026, 7, 22, tzinfo=UTC),
        repo_root_name="example",
        files=[
            IndexedFile(
                path="src/main.py",
                extension=".py",
                size_bytes=100,
                line_count=20,
                sha256="0" * 64,
                is_binary=False,
                is_symlink=False,
                detected_encoding="utf-8",
            ),
            IndexedFile(
                path="README.md",
                extension=".md",
                size_bytes=0,
                line_count=0,
                sha256="1" * 64,
                is_binary=False,
                is_symlink=False,
                detected_encoding="utf-8",
            ),
        ],
        skipped_files=[SkippedFile(path=".env", skip_reason=SkipReason.SENSITIVE_FILE)],
        stats=FileIndexStats(
            files_seen=3,
            files_included=2,
            files_skipped=1,
            total_included_bytes=100,
        ),
    )


def make_plan_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact": "context-plan",
        "generated_at": "2026-07-22T12:00:00Z",
        "repo": {"root_name": "example", "revision": None},
        "summary": {
            "repository_purpose": None,
            "project_type": "service",
            "detected_stack": [" Python ", "FastAPI", "python"],
            "main_runtime_flow": None,
            "confidence": 0.8,
        },
        "packages": [
            {
                "package_id": "pkg.runtime",
                "title": "Runtime",
                "purpose": "Explain request handling",
                "priority": 2,
                "topics": ["webhook-processing", "runtime", "runtime"],
                "ordered_items": [
                    {
                        "path": "src/main.py",
                        "line_start": 10,
                        "line_end": 20,
                        "role": "handler",
                        "reason": "Receives requests",
                        "expected_use": "Understand control flow",
                    },
                    {
                        "path": "src/main.py",
                        "line_start": 1,
                        "line_end": 5,
                        "role": "bootstrap",
                        "reason": "Creates the app",
                        "expected_use": "Understand initialization",
                    },
                ],
                "provenance": [
                    {
                        "source_type": "file_excerpt",
                        "path": "src/main.py",
                        "line_start": 10,
                        "line_end": 20,
                        "evidence_note": "Handler evidence",
                    },
                    {
                        "source_type": "file_excerpt",
                        "path": "src/main.py",
                        "line_start": 1,
                        "line_end": 5,
                        "evidence_note": "Bootstrap evidence",
                    },
                ],
                "confidence": 0.7,
                "warnings": [" Needs review ", "Needs review"],
                "unknowns": [],
            },
            {
                "package_id": "pkg.bootstrap",
                "title": "Bootstrap",
                "purpose": "Explain startup",
                "priority": 1,
                "topics": ["application-startup"],
                "ordered_items": [
                    {
                        "path": "src/main.py",
                        "line_start": 1,
                        "line_end": 5,
                        "role": "entrypoint",
                        "reason": "Starts the service",
                        "expected_use": "Trace startup",
                    }
                ],
                "provenance": [
                    {
                        "source_type": "file_excerpt",
                        "path": "src/main.py",
                        "line_start": 1,
                        "line_end": 5,
                        "evidence_note": "Startup evidence",
                    }
                ],
                "confidence": 0.9,
                "warnings": [],
                "unknowns": ["Deployment path", "Deployment path"],
            },
        ],
        "intentionally_excluded": [
            {"path_or_pattern": "*.lock", "reason": "Generated dependency data"},
            {"path_or_pattern": ".env", "reason": "Sensitive configuration"},
        ],
        "global_warnings": ["Partial repository", "Partial repository"],
        "global_unknowns": [],
    }


def issue_codes(error: ContextPlanValidationError) -> set[str]:
    return {issue.code for issue in error.issues}


def test_validate_context_plan_normalizes_set_like_fields_and_preserves_items() -> None:
    plan = validate_context_plan(make_plan_payload(), make_file_index())

    assert [package.package_id for package in plan.packages] == [
        "pkg.bootstrap",
        "pkg.runtime",
    ]
    runtime = plan.packages[1]
    assert runtime.topics == ["runtime", "webhook-processing"]
    assert [item.line_start for item in runtime.ordered_items] == [10, 1]
    assert [item.line_start for item in runtime.provenance] == [1, 10]
    assert runtime.warnings == ["Needs review"]
    assert plan.summary.detected_stack == ["FastAPI", "Python"]
    assert plan.global_warnings == ["Partial repository"]
    assert [item.path_or_pattern for item in plan.intentionally_excluded] == [
        "*.lock",
        ".env",
    ]


def test_context_plan_serialization_is_canonical() -> None:
    plan = validate_context_plan(make_plan_payload(), make_file_index())

    first = serialize_context_plan(plan)
    second = serialize_context_plan(plan)

    assert first == second
    assert first.endswith(b"\n")
    assert (
        first
        == json.dumps(
            json.loads(first), indent=2, sort_keys=True, separators=(",", ": ")
        ).encode()
        + b"\n"
    )


def test_duplicate_package_ids_and_items_are_aggregated() -> None:
    payload = make_plan_payload()
    packages = payload["packages"]
    assert isinstance(packages, list)
    packages[1]["package_id"] = "pkg.runtime"
    packages[0]["ordered_items"].append(packages[0]["ordered_items"][0].copy())

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {
        "duplicate_package_id",
        "duplicate_package_item",
    }


@pytest.mark.parametrize(
    ("path", "expected_code"),
    [
        ("missing.py", "unknown_path"),
        (".env", "skipped_path"),
        ("/absolute.py", "absolute_path"),
        ("../outside.py", "path_traversal"),
        ("src\\main.py", "non_posix_path"),
        ("./src/main.py", "non_posix_path"),
        ("src/main.py\0ignored", "non_posix_path"),
    ],
)
def test_referenced_paths_fail_with_stable_codes(path: str, expected_code: str) -> None:
    payload = make_plan_payload()
    payload["packages"][0]["ordered_items"][0]["path"] = path

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert expected_code in issue_codes(caught.value)


@pytest.mark.parametrize(
    ("line_start", "line_end", "expected_code"),
    [
        (0, 1, "invalid_line_range"),
        (10, 9, "invalid_line_range"),
        (1, 21, "line_range_out_of_bounds"),
    ],
)
def test_invalid_line_ranges_fail_with_stable_codes(
    line_start: int, line_end: int, expected_code: str
) -> None:
    payload = make_plan_payload()
    item = payload["packages"][0]["ordered_items"][0]
    item["line_start"] = line_start
    item["line_end"] = line_end

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert expected_code in issue_codes(caught.value)


def test_empty_indexed_file_cannot_be_referenced() -> None:
    payload = make_plan_payload()
    payload["packages"][0]["ordered_items"][0]["path"] = "README.md"
    payload["packages"][0]["ordered_items"][0]["line_start"] = 1
    payload["packages"][0]["ordered_items"][0]["line_end"] = 1

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert "line_range_out_of_bounds" in issue_codes(caught.value)


@pytest.mark.parametrize(
    "legacy_field",
    [
        "target_memory_kind",
        "memory_target",
        "package_ids",
        "expected_use_by_memory_agent",
        "coverage",
    ],
)
def test_context_plan_rejects_legacy_assignment_and_coverage_fields(
    legacy_field: str,
) -> None:
    payload = make_plan_payload()
    payload["packages"][0][legacy_field] = "legacy"

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


def test_required_package_fields_and_lists_are_enforced() -> None:
    payload = make_plan_payload()
    package = payload["packages"][0]
    del package["warnings"]
    package["ordered_items"] = []
    package["provenance"] = []

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert len(caught.value.issues) == 3
    assert issue_codes(caught.value) == {"schema_validation_error"}


@pytest.mark.parametrize("field", ["role", "reason", "expected_use"])
def test_required_package_item_text_fields_are_enforced(field: str) -> None:
    payload = make_plan_payload()
    del payload["packages"][0]["ordered_items"][0][field]

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


def test_required_provenance_evidence_note_is_enforced() -> None:
    payload = make_plan_payload()
    del payload["packages"][0]["provenance"][0]["evidence_note"]

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


@pytest.mark.parametrize(
    "topics",
    [
        [],
        ["Uppercase"],
        ["under_score"],
        ["x" * 65],
        [f"topic-{index}" for index in range(13)],
    ],
)
def test_topics_enforce_only_mechanical_slug_and_count_constraints(
    topics: list[str],
) -> None:
    payload = make_plan_payload()
    payload["packages"][0]["topics"] = topics

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


def test_provenance_rejects_provider_specific_source_type() -> None:
    payload = make_plan_payload()
    payload["packages"][0]["provenance"][0]["source_type"] = "github_file"

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


def test_finalization_request_rejects_provider_specific_or_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ContextPlanFinalizationRequest.model_validate(
            {
                "explored_areas": ["runtime"],
                "key_evidence_paths": ["src/main.py"],
                "unresolved_areas": [],
                "sufficiency_reason": "The main flow is supported by evidence",
                "full_prompt": "not allowed",
            }
        )


def test_invalid_candidate_never_replaces_existing_context_plan(tmp_path: Path) -> None:
    destination = tmp_path / "context-plan.json"
    destination.write_text("existing valid artifact\n")
    payload = make_plan_payload()
    payload["packages"][0]["ordered_items"][0]["path"] = "invented.py"

    with pytest.raises(ContextPlanValidationError):
        write_context_plan(destination, payload, make_file_index())

    assert destination.read_text() == "existing valid artifact\n"


def test_serialization_failure_never_replaces_existing_context_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "context-plan.json"
    destination.write_text("existing valid artifact\n")

    def fail_serialization(plan: ContextPlan) -> bytes:
        raise TypeError("serialization failed")

    monkeypatch.setattr(
        context_plan_validation, "serialize_context_plan", fail_serialization
    )

    with pytest.raises(TypeError, match="serialization failed"):
        write_context_plan(destination, make_plan_payload(), make_file_index())

    assert destination.read_text() == "existing valid artifact\n"


def test_temporary_write_failure_never_replaces_existing_context_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "context-plan.json"
    destination.write_text("existing valid artifact\n")

    def fail_temporary_file(*args: object, **kwargs: object) -> None:
        raise OSError("temporary write failed")

    monkeypatch.setattr(
        artifact_writer.tempfile, "NamedTemporaryFile", fail_temporary_file
    )

    with pytest.raises(OSError, match="temporary write failed"):
        write_context_plan(destination, make_plan_payload(), make_file_index())

    assert destination.read_text() == "existing valid artifact\n"


def test_write_context_plan_returns_path_and_serialized_checksum(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "context-plan.json"

    result = write_context_plan(destination, make_plan_payload(), make_file_index())

    assert result.path == destination
    assert result.sha256 == sha256_file(destination)
    assert destination.read_bytes().endswith(b"\n")
    assert json.loads(destination.read_text())["artifact"] == "context-plan"


def test_context_plan_rejects_naive_generated_at() -> None:
    payload = make_plan_payload()
    payload["generated_at"] = "2026-07-22T12:00:00"

    with pytest.raises(ContextPlanValidationError) as caught:
        validate_context_plan(payload, make_file_index())

    assert issue_codes(caught.value) == {"schema_validation_error"}


def test_context_plan_model_forbids_unexpected_top_level_fields() -> None:
    payload = make_plan_payload()
    payload["memory_targets"] = []

    with pytest.raises(ValidationError):
        ContextPlan.model_validate(payload)


def test_context_plan_run_accepts_lightweight_metadata_only_contract() -> None:
    run = ContextPlanRun.model_validate(
        {
            "run_id": "run-2026-07-22",
            "repo": {"root_name": "example", "revision": "abc123"},
            "started_at": "2026-07-22T12:00:00Z",
            "updated_at": "2026-07-22T12:01:00Z",
            "completed_at": None,
            "status": "running",
            "phase": "investigation",
            "model_profile": None,
            "model_name": None,
            "inspection": {
                "safe_file_count": 2,
                "inspected_file_count": 1,
                "remaining_file_count": 1,
                "inspected_files": ["src/main.py"],
                "inspected_excerpts": [
                    {"path": "src/main.py", "line_start": 1, "line_end": 5}
                ],
                "inspected_symbols": [
                    {"identifier": "main:create_app", "path": "src/main.py"}
                ],
                "search_records": [
                    {"tool": "search", "query": "create_app", "result_count": 1}
                ],
            },
            "finalization_requests": [],
            "validation_attempts": [],
            "errors": [],
            "output": None,
        }
    )

    assert run.artifact == "context-plan-run"
    assert run.inspection.inspected_excerpts[0].line_end == 5
    assert "full_prompts" not in ContextPlanRun.model_fields
    assert "model_reasoning" not in ContextPlanRun.model_fields
