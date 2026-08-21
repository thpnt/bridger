"""Deterministic Stage 13 final memory-fleet acceptance boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import orjson
from pydantic import ValidationError

from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import (
    FindingOrigin,
    FleetPhase,
    FleetRunState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.fleet_acceptance import AcceptedMemoryFleetResult
from bridger.contracts.memory.review import ReviewVerdict
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.memory.errors import FleetAcceptanceError, PersistenceRecoveryError
from bridger.memory.evaluation.acceptance import resolve_accepted_target_result
from bridger.memory.evaluation.fleet_review import resolve_fleet_review_verdict
from bridger.memory.evaluation.fleet_validation import resolve_fleet_validation_report
from bridger.memory.persistence.durability import FleetRuntimeStore, _model_bytes

_FLEET_FINDING_ORIGINS = {
    FindingOrigin.FLEET_VALIDATION,
    FindingOrigin.FLEET_REVIEW,
}


def accept_fleet(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> AcceptedMemoryFleetResult:
    """Freeze the exact fleet that passed Stage 11 and Stage 12."""
    try:
        with store.state_locks():
            current = _load_current_fleet_state(store, fleet_state)
            if current.phase is FleetPhase.ACCEPTED:
                result = _resolve_current_result(store, current)
                _replace_acceptance_state(fleet_state, current)
                return result
            if current.phase is not FleetPhase.REVIEWING:
                raise FleetAcceptanceError("fleet acceptance requires REVIEWING phase")
            target_specs = store.load_target_specs()
            target_states = _load_target_states(store, target_specs)
            accepted_results = _resolve_current_accepted_fleet(
                store,
                current,
                target_specs,
                target_states,
            )
            accepted_refs = [
                result.accepted_target_result_id for result in accepted_results
            ]
            report = resolve_fleet_validation_report(store, accepted_refs)
            if (
                report is None
                or report.verdict is not ValidationVerdict.PASS
                or report.finding_refs
            ):
                raise ValueError(
                    "fleet acceptance requires the exact Stage 11 PASS report"
                )
            review = resolve_fleet_review_verdict(
                store,
                report.fleet_validation_report_id,
            )
            if (
                review is None
                or review.verdict is not ReviewVerdict.PASS
                or review.finding_refs
                or review.fleet_validation_report_ref
                != report.fleet_validation_report_id
            ):
                raise ValueError(
                    "fleet acceptance requires the exact Stage 12 PASS verdict"
                )
            _require_clear_fleet_findings(current, target_states)
            result = _build_accepted_fleet_result(
                store,
                accepted_refs,
                report.fleet_validation_report_id,
                review.fleet_review_id,
            )
            result_path = store.paths.accepted_memory_fleet_result(
                result.accepted_memory_fleet_result_id
            )
            if result_path.exists():
                existing = resolve_accepted_memory_fleet_result(
                    store,
                    result.accepted_memory_fleet_result_id,
                )
                if existing != result:
                    raise ValueError(
                        "accepted fleet identity resolves to different provenance"
                    )
                result = existing
            after = current.model_copy(
                update={
                    "phase": FleetPhase.ACCEPTED,
                    "accepted_result_ref": result.accepted_memory_fleet_result_id,
                }
            )
            store.commit_operation(
                operation_id=_operation_id(result.accepted_memory_fleet_result_id),
                writes={
                    result_path: _model_bytes(result),
                    store.paths.fleet_state: _model_bytes(after),
                },
                event_type="fleet_accepted",
                payload={
                    "accepted_memory_fleet_result_id": (
                        result.accepted_memory_fleet_result_id
                    ),
                    "fleet_validation_report_ref": (result.fleet_validation_report_ref),
                    "fleet_review_verdict_ref": result.fleet_review_verdict_ref,
                    "from_phase": FleetPhase.REVIEWING.value,
                    "to_phase": FleetPhase.ACCEPTED.value,
                },
            )
            _replace_acceptance_state(fleet_state, after)
            return result
    except FleetAcceptanceError:
        raise
    except (OSError, PersistenceRecoveryError, ValidationError, ValueError) as error:
        raise FleetAcceptanceError(
            "could not establish or persist coherent fleet acceptance"
        ) from error


def resolve_accepted_memory_fleet_result(
    store: FleetRuntimeStore,
    result_id: str,
) -> AcceptedMemoryFleetResult:
    """Load and verify one immutable accepted memory-fleet result."""
    try:
        result = AcceptedMemoryFleetResult.model_validate_json(
            store.paths.accepted_memory_fleet_result(result_id).read_bytes()
        )
        if (
            result.accepted_memory_fleet_result_id != result_id
            or result.fleet_run_id != store.fleet_spec.fleet_run_id
            or result.source != store.fleet_spec.source
            or result.target_catalog_id != store.fleet_spec.target_catalog_id
            or result.target_catalog_version != store.fleet_spec.target_catalog_version
        ):
            raise ValueError("accepted fleet identities do not match its run")
        target_specs = store.load_target_specs()
        if len(result.accepted_target_result_refs) != len(target_specs):
            raise ValueError("accepted fleet target inventory is incomplete")
        accepted_results = [
            resolve_accepted_target_result(store, target_spec, accepted_ref)
            for target_spec, accepted_ref in zip(
                target_specs,
                result.accepted_target_result_refs,
                strict=True,
            )
        ]
        if any(item.source != result.source for item in accepted_results):
            raise ValueError("accepted fleet source provenance is inconsistent")
        report = resolve_fleet_validation_report(
            store,
            result.accepted_target_result_refs,
        )
        if (
            report is None
            or report.fleet_validation_report_id != result.fleet_validation_report_ref
            or report.verdict is not ValidationVerdict.PASS
            or report.finding_refs
        ):
            raise ValueError("accepted fleet validation provenance is invalid")
        review = resolve_fleet_review_verdict(
            store,
            result.fleet_validation_report_ref,
        )
        if (
            review is None
            or review.fleet_review_id != result.fleet_review_verdict_ref
            or review.verdict is not ReviewVerdict.PASS
            or review.finding_refs
        ):
            raise ValueError("accepted fleet review provenance is invalid")
        expected = _build_accepted_fleet_result(
            store,
            result.accepted_target_result_refs,
            report.fleet_validation_report_id,
            review.fleet_review_id,
        )
        if result != expected:
            raise ValueError("accepted fleet provenance is not canonical")
        return result
    except PersistenceRecoveryError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise PersistenceRecoveryError(
            "accepted memory fleet result failed integrity validation"
        ) from error


def _load_current_fleet_state(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> FleetRunState:
    current = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    if (
        current.fleet_run_id != store.fleet_spec.fleet_run_id
        or fleet_state.fleet_run_id != current.fleet_run_id
    ):
        raise ValueError("fleet acceptance authorities identify different runs")
    return current


def _replace_acceptance_state(
    current: FleetRunState,
    replacement: FleetRunState,
) -> None:
    """Replace the mutually dependent accepted phase and result atomically."""
    current.__dict__.update(replacement.__dict__)


def _load_target_states(
    store: FleetRuntimeStore,
    target_specs: Sequence[TargetTaskSpec],
) -> list[TargetTaskState]:
    return [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target_spec).read_bytes()
        )
        for target_spec in target_specs
    ]


def _resolve_current_accepted_fleet(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
) -> list[AcceptedTargetResult]:
    if len(target_specs) != len(
        store.fleet_spec.target_ids
    ) or fleet_state.target_task_ids != [
        target_spec.target_task_id for target_spec in target_specs
    ]:
        raise ValueError("fleet acceptance target inventory is inconsistent")
    results: list[AcceptedTargetResult] = []
    for target_id, target_spec, target_state in zip(
        store.fleet_spec.target_ids,
        target_specs,
        target_states,
        strict=True,
    ):
        if (
            target_spec.target_id != target_id
            or target_spec.source != store.fleet_spec.source
            or target_state.target_task_id != target_spec.target_task_id
            or target_state.phase is not TargetPhase.ACCEPTED
        ):
            raise ValueError(
                "fleet acceptance requires every exact target to remain ACCEPTED"
            )
        accepted_ref = target_state.last_accepted_result_ref
        if accepted_ref is None:
            raise ValueError("accepted target has no accepted-result reference")
        results.append(resolve_accepted_target_result(store, target_spec, accepted_ref))
    return results


def _resolve_current_result(
    store: FleetRuntimeStore,
    fleet_state: FleetRunState,
) -> AcceptedMemoryFleetResult:
    result_id = fleet_state.accepted_result_ref
    if result_id is None:
        raise ValueError("accepted fleet state has no accepted-result reference")
    result = resolve_accepted_memory_fleet_result(store, result_id)
    target_specs = store.load_target_specs()
    target_states = _load_target_states(store, target_specs)
    current_refs = [state.last_accepted_result_ref for state in target_states]
    if (
        any(state.phase is not TargetPhase.ACCEPTED for state in target_states)
        or current_refs != result.accepted_target_result_refs
    ):
        raise ValueError("accepted fleet state no longer matches its result")
    return result


def _require_clear_fleet_findings(
    fleet_state: FleetRunState,
    target_states: Sequence[TargetTaskState],
) -> None:
    if any(
        reference.origin in _FLEET_FINDING_ORIGINS
        for reference in fleet_state.open_finding_refs
    ) or any(
        reference.origin in _FLEET_FINDING_ORIGINS
        for target_state in target_states
        for reference in target_state.open_finding_refs
    ):
        raise ValueError("current fleet-level findings block fleet acceptance")


def _build_accepted_fleet_result(
    store: FleetRuntimeStore,
    accepted_refs: Sequence[str],
    validation_report_ref: str,
    review_verdict_ref: str,
) -> AcceptedMemoryFleetResult:
    result = AcceptedMemoryFleetResult(
        accepted_memory_fleet_result_id="pending",
        fleet_run_id=store.fleet_spec.fleet_run_id,
        source=store.fleet_spec.source,
        target_catalog_id=store.fleet_spec.target_catalog_id,
        target_catalog_version=store.fleet_spec.target_catalog_version,
        accepted_target_result_refs=list(accepted_refs),
        fleet_validation_report_ref=validation_report_ref,
        fleet_review_verdict_ref=review_verdict_ref,
    )
    identity = orjson.dumps(
        result.model_dump(
            mode="json",
            exclude={"accepted_memory_fleet_result_id"},
        ),
        option=orjson.OPT_SORT_KEYS,
    )
    return result.model_copy(
        update={
            "accepted_memory_fleet_result_id": (
                f"accepted-memory-fleet-result-{hashlib.sha256(identity).hexdigest()}"
            )
        }
    )


def _operation_id(result_id: str) -> str:
    return f"fleet-acceptance-{hashlib.sha256(result_id.encode()).hexdigest()}"


__all__ = [
    "accept_fleet",
    "resolve_accepted_memory_fleet_result",
]
