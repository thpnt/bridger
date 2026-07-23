from typing import Any

from pydantic import JsonValue, ValidationError

from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanRunStatus,
    ContextPlanValidationIssue,
    FinalizationContext,
    FinalizationDecision,
    FinalizationDecisionCode,
)
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.path_safety import PathSafetyService


class ContextPlanCompletionPolicy:
    """Evaluate whether a finalization request is safely grounded in inspection."""

    def __init__(self, paths: PathSafetyService) -> None:
        self._paths = paths

    def evaluate(
        self, request: object, context: FinalizationContext
    ) -> FinalizationDecision:
        """Return a deterministic decision without evaluating repository semantics."""
        validated_request, request_issues = self._validate_request(request)
        if request_issues:
            return FinalizationDecision(
                accepted=False,
                code=self._request_decision_code(request_issues),
                issues=request_issues,
            )

        assert validated_request is not None
        issues = [
            *self._run_issues(context),
            *self._evidence_issues(validated_request, context),
        ]
        if not issues:
            return FinalizationDecision(
                accepted=True,
                code=FinalizationDecisionCode.ACCEPTED,
            )

        return FinalizationDecision(
            accepted=False,
            code=self._decision_code(issues),
            issues=issues,
        )

    def _validate_request(
        self, request: object
    ) -> tuple[ContextPlanFinalizationRequest | None, list[ContextPlanValidationIssue]]:
        try:
            return ContextPlanFinalizationRequest.model_validate(request), []
        except ValidationError as error:
            return None, [self._validation_issue(item) for item in error.errors()]

    def _validation_issue(self, error: Any) -> ContextPlanValidationIssue:
        location = list(error["loc"])
        field = location[0] if location else "request"
        is_path_error = field == "key_evidence_paths" and len(location) > 1
        return ContextPlanValidationIssue(
            code="unsafe_evidence_path" if is_path_error else "invalid_request",
            location=location,
            message=(
                "evidence path must be a safe repository-relative path"
                if is_path_error
                else error["msg"]
            ),
            context={"error_type": str(error["type"])},
        )

    def _run_issues(
        self, context: FinalizationContext
    ) -> list[ContextPlanValidationIssue]:
        if context.stalled or context.run_status is ContextPlanRunStatus.STALLED:
            return [
                self._issue(
                    "run_stalled",
                    "run is stalled and cannot start synthesis",
                    {"run_status": context.run_status.value},
                )
            ]
        if (
            context.hard_budget_exhausted
            or context.run_status is ContextPlanRunStatus.BUDGET_EXHAUSTED
        ):
            return [
                self._issue(
                    "budget_exhausted",
                    "run budget is exhausted and cannot start synthesis",
                    {"run_status": context.run_status.value},
                )
            ]
        if context.run_status is ContextPlanRunStatus.FAILED:
            return [
                self._issue(
                    "run_failed",
                    "failed run cannot start synthesis",
                    {"run_status": context.run_status.value},
                )
            ]
        if context.run_status is ContextPlanRunStatus.INITIALIZED:
            return [
                self._issue(
                    "run_not_active",
                    "run must be active before finalization",
                    {"run_status": context.run_status.value},
                )
            ]
        if context.run_status is not ContextPlanRunStatus.RUNNING:
            return [
                self._issue(
                    "run_not_synthesizable",
                    "run cannot start synthesis in its current state",
                    {"run_status": context.run_status.value},
                )
            ]
        return []

    def _evidence_issues(
        self,
        request: ContextPlanFinalizationRequest,
        context: FinalizationContext,
    ) -> list[ContextPlanValidationIssue]:
        inspected_paths = set(context.evidence_paths)
        issues: list[ContextPlanValidationIssue] = []

        for index, path in enumerate(request.key_evidence_paths):
            location: list[str | int] = ["key_evidence_paths", index]
            try:
                normalized = self._paths.validate_file(path)
            except BridgerToolError as error:
                issues.append(self._path_safety_issue(path, location, error))
                continue

            if normalized not in inspected_paths:
                issues.append(
                    ContextPlanValidationIssue(
                        code="uninspected_evidence_path",
                        location=location,
                        message="evidence path was not substantively inspected",
                        context={"path": normalized},
                    )
                )

        return issues

    def _path_safety_issue(
        self,
        path: str,
        location: list[str | int],
        error: BridgerToolError,
    ) -> ContextPlanValidationIssue:
        if error.payload.error == "path_not_indexed":
            code = "unknown_evidence_path"
            message = "evidence path is not in the safe file index"
        elif error.payload.error == "path_skipped":
            code = "skipped_evidence_path"
            message = "evidence path was skipped from the safe file index"
        else:
            code = "unsafe_evidence_path"
            message = "evidence path must be a safe repository-relative path"

        context: dict[str, JsonValue] = {"path": path}
        if error.payload.error == "path_skipped":
            details = error.payload.details or {}
            skip_reason = details.get("skip_reason")
            if isinstance(skip_reason, str):
                context["skip_reason"] = skip_reason
        return ContextPlanValidationIssue(
            code=code,
            location=location,
            message=message,
            context=context,
        )

    def _request_decision_code(
        self, issues: list[ContextPlanValidationIssue]
    ) -> FinalizationDecisionCode:
        if any(issue.code == "unsafe_evidence_path" for issue in issues):
            return FinalizationDecisionCode.UNSAFE_EVIDENCE_PATH
        return FinalizationDecisionCode.INVALID_REQUEST

    def _decision_code(
        self, issues: list[ContextPlanValidationIssue]
    ) -> FinalizationDecisionCode:
        code_by_issue = {
            "run_stalled": FinalizationDecisionCode.RUN_STALLED,
            "budget_exhausted": FinalizationDecisionCode.BUDGET_EXHAUSTED,
            "run_failed": FinalizationDecisionCode.RUN_FAILED,
            "run_not_active": FinalizationDecisionCode.RUN_NOT_ACTIVE,
            "run_not_synthesizable": FinalizationDecisionCode.RUN_NOT_SYNTHESIZABLE,
            "unsafe_evidence_path": FinalizationDecisionCode.UNSAFE_EVIDENCE_PATH,
            "skipped_evidence_path": FinalizationDecisionCode.UNSAFE_EVIDENCE_PATH,
            "unknown_evidence_path": FinalizationDecisionCode.UNKNOWN_EVIDENCE_PATH,
            "uninspected_evidence_path": (
                FinalizationDecisionCode.UNINSPECTED_EVIDENCE_PATH
            ),
        }
        for issue in issues:
            decision_code = code_by_issue.get(issue.code)
            if decision_code is not None:
                return decision_code
        return FinalizationDecisionCode.INVALID_REQUEST

    @staticmethod
    def _issue(
        code: str, message: str, context: dict[str, JsonValue]
    ) -> ContextPlanValidationIssue:
        return ContextPlanValidationIssue(
            code=code,
            location=["run"],
            message=message,
            context=context,
        )
