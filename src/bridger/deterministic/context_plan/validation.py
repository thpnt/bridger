from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import orjson
from pydantic import JsonValue, ValidationError

from bridger.artifacts import write_artifact
from bridger.deterministic.context_plan.working_state import (
    WorkingStateValidationError,
    merge_line_ranges,
    validate_working_state,
)
from bridger.deterministic.context_plan_bootstrap.checksums import sha256_file
from bridger.models.context_plan import (
    ContextPackageItem,
    ContextPlan,
    ContextPlanValidationIssue,
)
from bridger.models.file_index import FileIndexArtifact
from bridger.models.working_state import (
    ContextPlanWorkingState,
    EvidenceKind,
    EvidenceLineRange,
    EvidenceStatus,
)

__all__ = [
    "ContextPlanValidationError",
    "ContextPlanWriteResult",
    "WorkingStateValidationError",
    "validate_context_plan",
    "validate_context_plan_inspection",
    "validate_working_state",
    "write_context_plan",
]


def validate_context_plan_inspection(
    plan: ContextPlan,
    working_state: ContextPlanWorkingState,
) -> ContextPlan:
    """Require every synthesized range to be backed by an inspected excerpt."""

    ranges_by_path: dict[str, list[tuple[int, int]]] = {}
    for evidence in working_state.evidence:
        if (
            evidence.status is EvidenceStatus.ACTIVE
            and evidence.kind is EvidenceKind.FILE_EXCERPT
            and evidence.path is not None
        ):
            ranges_by_path.setdefault(evidence.path, []).extend(
                (item.line_start, item.line_end) for item in evidence.line_ranges
            )
    for path, ranges in ranges_by_path.items():
        merged = merge_line_ranges(
            [
                EvidenceLineRange(line_start=line_start, line_end=line_end)
                for line_start, line_end in ranges
            ]
        )
        ranges_by_path[path] = [(item.line_start, item.line_end) for item in merged]

    issues: list[ContextPlanValidationIssue] = []
    for package_index, package in enumerate(plan.packages):
        values = [
            *(
                (
                    ["packages", package_index, "ordered_items", item_index],
                    item.path,
                    item.line_start,
                    item.line_end,
                )
                for item_index, item in enumerate(package.ordered_items)
            ),
            *(
                (
                    ["packages", package_index, "provenance", item_index],
                    item.path,
                    item.line_start,
                    item.line_end,
                )
                for item_index, item in enumerate(package.provenance)
            ),
        ]
        for location, path, line_start, line_end in values:
            if any(
                observed_start <= line_start and line_end <= observed_end
                for observed_start, observed_end in ranges_by_path.get(path, [])
            ):
                continue
            issues.append(
                ContextPlanValidationIssue(
                    code=(
                        "range_not_inspected"
                        if path in ranges_by_path
                        else "unknown_path"
                    ),
                    location=cast(list[str | int], location),
                    message=(
                        f"line range {line_start}-{line_end} is not covered by an "
                        f"inspected excerpt for {path}"
                    ),
                    context={
                        "path": path,
                        "line_start": line_start,
                        "line_end": line_end,
                    },
                )
            )
    if issues:
        raise ContextPlanValidationError(issues)
    return plan


@dataclass(frozen=True)
class ContextPlanWriteResult:
    path: Path
    sha256: str


class ContextPlanValidationError(ValueError):
    def __init__(self, issues: list[ContextPlanValidationIssue]) -> None:
        self.issues = issues
        codes = ", ".join(issue.code for issue in issues)
        super().__init__(
            f"context plan validation failed with {len(issues)} issue(s): {codes}"
        )


def validate_context_plan(
    payload_or_plan: ContextPlan | dict[str, Any],
    file_index: FileIndexArtifact,
) -> ContextPlan:
    try:
        plan = ContextPlan.model_validate(payload_or_plan)
    except ValidationError as error:
        raise ContextPlanValidationError(_schema_issues(error)) from error

    issues = _cross_object_issues(plan, file_index)
    if issues:
        raise ContextPlanValidationError(issues)
    return normalize_context_plan(plan)


def normalize_context_plan(plan: ContextPlan) -> ContextPlan:
    normalized = plan.model_copy(deep=True)
    normalized.summary.detected_stack = _normalized_strings(
        normalized.summary.detected_stack, case_insensitive=True
    )
    normalized.packages.sort(key=lambda package: (package.priority, package.package_id))
    for package in normalized.packages:
        package.topics = sorted(set(package.topics))
        package.provenance.sort(
            key=lambda item: (
                item.path,
                item.line_start,
                item.line_end,
                item.evidence_note,
            )
        )
        package.warnings = _normalized_strings(package.warnings)
        package.unknowns = _normalized_strings(package.unknowns)
    normalized.intentionally_excluded.sort(
        key=lambda exclusion: (exclusion.path_or_pattern, exclusion.reason)
    )
    normalized.global_warnings = _normalized_strings(normalized.global_warnings)
    normalized.global_unknowns = _normalized_strings(normalized.global_unknowns)
    return normalized


def serialize_context_plan(plan: ContextPlan) -> bytes:
    return (
        orjson.dumps(
            plan.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )


def write_context_plan(
    destination: Path,
    payload_or_plan: ContextPlan | dict[str, Any],
    file_index: FileIndexArtifact,
) -> ContextPlanWriteResult:
    plan = validate_context_plan(payload_or_plan, file_index)
    serialize_context_plan(plan)
    write_artifact(destination, plan)
    return ContextPlanWriteResult(path=destination, sha256=sha256_file(destination))


def _normalized_strings(
    values: list[str], *, case_insensitive: bool = False
) -> list[str]:
    unique: dict[str, str] = {}
    for value in values:
        key = value.casefold() if case_insensitive else value
        unique.setdefault(key, value)
    sort_key = str.casefold if case_insensitive else None
    return sorted(unique.values(), key=sort_key)


def _schema_issues(error: ValidationError) -> list[ContextPlanValidationIssue]:
    issues: list[ContextPlanValidationIssue] = []
    for item in error.errors(include_url=False):
        location = list(item["loc"])
        input_value = item.get("input")
        code = _schema_issue_code(location, input_value, item["msg"])
        context: dict[str, JsonValue] = {}
        if isinstance(input_value, (str, int, float, bool)) or input_value is None:
            context["input"] = input_value
        issues.append(
            ContextPlanValidationIssue(
                code=code,
                location=location,
                message=item["msg"],
                context=context,
            )
        )
    return issues


def _schema_issue_code(
    location: list[str | int], input_value: object, message: str
) -> str:
    field = location[-1] if location else None
    if field in {"path", "key_evidence_paths"} and isinstance(input_value, str):
        return _path_issue_code(input_value)
    if field in {"line_start", "line_end"} or "line_end must" in message:
        return "invalid_line_range"
    return "schema_validation_error"


def _path_issue_code(path: str) -> str:
    if PurePosixPath(path).is_absolute():
        return "absolute_path"
    if ".." in PurePosixPath(path).parts:
        return "path_traversal"
    return "non_posix_path"


def _cross_object_issues(
    plan: ContextPlan, file_index: FileIndexArtifact
) -> list[ContextPlanValidationIssue]:
    issues: list[ContextPlanValidationIssue] = []
    included = {item.path: item for item in file_index.files}
    skipped = {item.path: item for item in file_index.skipped_files}
    seen_package_ids: set[str] = set()

    for package_index, package in enumerate(plan.packages):
        package_location: list[str | int] = ["packages", package_index]
        if package.package_id in seen_package_ids:
            issues.append(
                ContextPlanValidationIssue(
                    code="duplicate_package_id",
                    location=[*package_location, "package_id"],
                    message=f"duplicate package ID: {package.package_id}",
                    context={"package_id": package.package_id},
                )
            )
        seen_package_ids.add(package.package_id)

        seen_items: set[tuple[object, ...]] = set()
        for item_index, item in enumerate(package.ordered_items):
            item_location = [*package_location, "ordered_items", item_index]
            identity = _item_identity(item)
            if identity in seen_items:
                issues.append(
                    ContextPlanValidationIssue(
                        code="duplicate_package_item",
                        location=item_location,
                        message="exact duplicate package item",
                        context={"path": item.path},
                    )
                )
            seen_items.add(identity)
            issues.extend(
                _reference_issues(
                    item.path,
                    item.line_start,
                    item.line_end,
                    item_location,
                    included,
                    skipped,
                )
            )

        for provenance_index, provenance in enumerate(package.provenance):
            issues.extend(
                _reference_issues(
                    provenance.path,
                    provenance.line_start,
                    provenance.line_end,
                    [*package_location, "provenance", provenance_index],
                    included,
                    skipped,
                )
            )
    return issues


def _item_identity(item: ContextPackageItem) -> tuple[object, ...]:
    return (
        item.path,
        item.line_start,
        item.line_end,
        item.role,
        item.reason,
        item.expected_use,
    )


def _reference_issues(
    path: str,
    line_start: int,
    line_end: int,
    location: list[str | int],
    included: dict[str, Any],
    skipped: dict[str, Any],
) -> list[ContextPlanValidationIssue]:
    if path in skipped:
        return [
            ContextPlanValidationIssue(
                code="skipped_path",
                location=[*location, "path"],
                message=f"path was skipped from the file index: {path}",
                context={
                    "path": path,
                    "skip_reason": skipped[path].skip_reason.value,
                },
            )
        ]
    indexed_file = included.get(path)
    if indexed_file is None:
        return [
            ContextPlanValidationIssue(
                code="unknown_path",
                location=[*location, "path"],
                message=f"path is not present in the included file index: {path}",
                context={"path": path},
            )
        ]
    if indexed_file.line_count == 0 or line_end > indexed_file.line_count:
        return [
            ContextPlanValidationIssue(
                code="line_range_out_of_bounds",
                location=[*location, "line_end"],
                message=(
                    f"line range {line_start}-{line_end} exceeds indexed line count "
                    f"{indexed_file.line_count} for {path}"
                ),
                context={
                    "path": path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "line_count": indexed_file.line_count,
                },
            )
        ]
    return []
