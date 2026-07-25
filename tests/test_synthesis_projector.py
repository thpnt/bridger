from datetime import UTC, datetime

from bridger.deterministic.context_plan.evidence import stable_id
from bridger.deterministic.context_plan.synthesis_projector import SynthesisProjector
from bridger.models.synthesis_manifest import SynthesisSelectionLimits
from bridger.models.working_state import (
    ContextPlanWorkingState,
    EvidenceKind,
    EvidenceLineRange,
    EvidenceRecord,
    InspectionLevel,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def evidence(sequence: int, area: str) -> EvidenceRecord:
    path = f"src/{area}/file_{sequence}.py"
    identity = {"path": path, "sequence": sequence, "area": area}
    return EvidenceRecord(
        evidence_id=stable_id("ev", identity),
        kind=EvidenceKind.FILE_EXCERPT,
        source_tool="read_file_excerpt",
        source_call_id=f"call-{sequence}",
        path=path,
        line_ranges=[EvidenceLineRange(line_start=1, line_end=1)],
        structured_payload={"path": path},
        content=f"value_{sequence}",
        content_digest=stable_id("digest", identity).split(".", 1)[1],
        inspection_level=InspectionLevel.EXCERPT_INSPECTED,
        sequence_number=sequence,
        area_key=area,
    )


def test_projection_is_deterministic_balanced_and_keeps_records_after_40() -> None:
    areas = ["websocket", "worker", "persistence", "configuration", "testing"]
    records = [evidence(index, areas[index % len(areas)]) for index in range(1, 61)]
    state = ContextPlanWorkingState(
        run_id="run-project",
        evidence=list(reversed(records)),
        mutation_sequence=60,
        updated_at=NOW,
    )
    projector = SynthesisProjector(
        SynthesisSelectionLimits(
            max_evidence_records=45,
            max_estimated_characters=1_000_000,
            max_verbatim_excerpts=45,
        )
    )

    first = projector.project(state)
    second = projector.project(state)

    assert first.manifest == second.manifest
    assert first.manifest.selected_record_count == 45
    assert first.manifest.omitted_record_count == 15
    assert set(first.manifest.represented_area_keys) == set(areas)
    assert any(item.sequence_number > 40 for item in first.evidence)
    assert first.manifest.omitted_by_area
    assert first.manifest.omission_reasons


def test_priority_path_does_not_delete_other_areas() -> None:
    records = [
        evidence(1, "websocket"),
        evidence(2, "worker"),
        evidence(3, "persistence"),
        evidence(4, "configuration"),
        evidence(5, "testing"),
    ]
    state = ContextPlanWorkingState(
        run_id="run-priority",
        evidence=records,
        mutation_sequence=5,
        updated_at=NOW,
    )

    projection = SynthesisProjector().project(
        state,
        priority_paths=[records[0].path],
    )

    assert projection.manifest.priority_paths == [records[0].path]
    assert {item.area_key for item in projection.evidence} == {
        "websocket",
        "worker",
        "persistence",
        "configuration",
        "testing",
    }
