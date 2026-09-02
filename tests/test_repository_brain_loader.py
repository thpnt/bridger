"""Focused canonical Repository Brain loader tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import bridger.repository_brain.loader as loader_module
from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import (
    CandidateArtifactRef,
    ExecutionBudget,
    MemoryFleetSpec,
    SourceBinding,
    TargetTaskSpec,
)
from bridger.contracts.memory.fleet_acceptance import AcceptedMemoryFleetResult
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.repository_brain.loader import (
    RepositoryBrainLoadError,
    _load_documents,
    _validate_fleet_binding,
    load_repository_brain,
)


def test_loader_reuses_acceptance_resolvers_and_loads_only_canonical_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _loader_fixture(tmp_path)
    extra = Path(fixture.spec.output_root) / "architecture" / "unaccepted.md"
    extra.write_text("not accepted", encoding="utf-8")
    calls: list[str] = []
    stores: list[_FakeStore] = []

    class TrackingStore(_FakeStore):
        def __init__(self, spec: MemoryFleetSpec) -> None:
            super().__init__(spec, fixture.target_spec)
            stores.append(self)

    def resolve_fleet(
        store: _FakeStore,
        result_id: str,
    ) -> AcceptedMemoryFleetResult:
        calls.append(f"fleet:{result_id}")
        return fixture.accepted_fleet

    def resolve_target(
        store: _FakeStore,
        target_spec: TargetTaskSpec,
        result_id: str,
    ) -> AcceptedTargetResult:
        calls.append(f"target:{result_id}")
        assert target_spec == fixture.target_spec
        return fixture.accepted_target

    monkeypatch.setattr(loader_module, "FleetRuntimeStore", TrackingStore)
    monkeypatch.setattr(
        loader_module,
        "resolve_accepted_memory_fleet_result",
        resolve_fleet,
    )
    monkeypatch.setattr(loader_module, "resolve_accepted_target_result", resolve_target)

    brain = load_repository_brain(fixture.publication_path)

    assert calls == ["fleet:accepted-fleet-1", "target:accepted-target-1"]
    assert stores[0].closed
    assert brain.publication_id == fixture.publication_path.parent.name
    assert [document.document_id for document in brain.documents] == ["artifact-1"]
    assert [document.relative_path for document in brain.documents] == [
        "architecture/runtime.md"
    ]
    assert all(document.content != "not accepted" for document in brain.documents)


@pytest.mark.parametrize(
    "case",
    ["missing", "digest", "symlink", "escape", "non-markdown"],
)
def test_loader_rejects_accepted_artifact_integrity_failures(
    tmp_path: Path,
    case: str,
) -> None:
    output_root = tmp_path / "memory"
    workspace = output_root / "architecture"
    workspace.mkdir(parents=True)
    artifact = workspace / "runtime.md"
    artifact.write_text("# Runtime\n", encoding="utf-8")
    reference = _artifact_ref(artifact, "runtime.md")

    if case == "missing":
        artifact.unlink()
    elif case == "digest":
        artifact.write_text("drifted", encoding="utf-8")
    elif case == "symlink":
        target = workspace / "real.md"
        target.write_text("# Runtime\n", encoding="utf-8")
        artifact.unlink()
        artifact.symlink_to(target)
    elif case == "escape":
        artifact = output_root / "outside.md"
        artifact.write_text("# Runtime\n", encoding="utf-8")
        reference = _artifact_ref(artifact, "../outside.md")
    else:
        artifact = workspace / "runtime.txt"
        artifact.write_text("# Runtime\n", encoding="utf-8")
        reference = _artifact_ref(artifact, "runtime.txt")

    manifest = _manifest(tmp_path, output_root)
    accepted = AcceptedTargetResult.model_construct(
        target_id="architecture",
        artifact_refs=[reference],
    )

    with pytest.raises(ValueError):
        _load_documents(manifest, [accepted])


def test_loader_rejects_manifest_and_fleet_revision_mismatch(tmp_path: Path) -> None:
    fixture = _loader_fixture(tmp_path)
    mismatched = fixture.spec.model_copy(
        update={
            "source": fixture.spec.source.model_copy(
                update={"repository_revision": "other-revision"}
            )
        }
    )

    with pytest.raises(ValueError, match="does not match"):
        _validate_fleet_binding(
            fixture.manifest,
            mismatched,
            Path(fixture.spec.runtime_root).resolve(),
        )


def test_loader_rejects_manifest_outside_its_content_address(tmp_path: Path) -> None:
    fixture = _loader_fixture(tmp_path)
    invalid_root = tmp_path / "published" / "wrong-publication"
    invalid_root.mkdir(parents=True)
    invalid_path = invalid_root / "repository-brain.json"
    invalid_path.write_bytes(fixture.publication_path.read_bytes())

    with pytest.raises(RepositoryBrainLoadError) as caught:
        load_repository_brain(invalid_path)

    assert isinstance(caught.value.__cause__, ValueError)


def test_manifest_rejects_empty_and_duplicate_accepted_refs(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, tmp_path / "memory")

    with pytest.raises(ValidationError):
        RepositoryBrainManifest.model_validate(
            {
                **manifest.model_dump(),
                "accepted_target_result_refs": [],
            }
        )
    with pytest.raises(ValidationError, match="must be unique"):
        RepositoryBrainManifest.model_validate(
            {
                **manifest.model_dump(),
                "accepted_target_result_refs": ["same", "same"],
            }
        )


class _LoaderFixture:
    def __init__(
        self,
        *,
        publication_path: Path,
        manifest: RepositoryBrainManifest,
        spec: MemoryFleetSpec,
        target_spec: TargetTaskSpec,
        accepted_fleet: AcceptedMemoryFleetResult,
        accepted_target: AcceptedTargetResult,
    ) -> None:
        self.publication_path = publication_path
        self.manifest = manifest
        self.spec = spec
        self.target_spec = target_spec
        self.accepted_fleet = accepted_fleet
        self.accepted_target = accepted_target


class _FakeStore:
    def __init__(
        self,
        spec: MemoryFleetSpec,
        target_spec: TargetTaskSpec | None = None,
    ) -> None:
        self.fleet_spec = spec
        self.target_spec = target_spec
        self.closed = False

    def load_target_specs(self) -> list[TargetTaskSpec]:
        assert self.target_spec is not None
        return [self.target_spec]

    def close(self) -> None:
        self.closed = True


def _loader_fixture(tmp_path: Path) -> _LoaderFixture:
    runtime_root = tmp_path / "runtime"
    output_root = tmp_path / "memory"
    workspace = output_root / "architecture"
    workspace.mkdir(parents=True)
    artifact = workspace / "runtime.md"
    artifact.write_text("# Runtime\n\nCanonical content.\n", encoding="utf-8")
    artifact_ref = _artifact_ref(artifact, "runtime.md")
    source = SourceBinding(
        repository_id="repository-1",
        repository_revision="revision-1",
        graph_snapshot_id="snapshot-1",
        enrichment_overlay_id="overlay-1",
    )
    budget = ExecutionBudget(
        max_cycles=1,
        max_model_calls=1,
        max_tool_calls=1,
        max_repair_cycles=1,
    )
    spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=source,
        target_catalog_id="catalog-1",
        target_catalog_version="1",
        target_ids=["architecture"],
        runtime_profile_id="runtime-profile",
        default_worker_profile_id="worker-profile",
        default_reviewer_profile_id="reviewer-profile",
        default_permission_profile_id="permission-profile",
        fleet_budget=budget,
        default_target_budget=budget,
        runtime_root=str(runtime_root),
        output_root=str(output_root),
    )
    run_root = runtime_root / spec.fleet_run_id
    run_root.mkdir(parents=True)
    (run_root / "fleet-spec.json").write_text(
        spec.model_dump_json(),
        encoding="utf-8",
    )
    target_spec = TargetTaskSpec(
        target_task_id="task-1",
        fleet_run_id=spec.fleet_run_id,
        target_id="architecture",
        target_contract_version="1",
        source=source,
        worker_profile_id="worker-profile",
        reviewer_profile_id="reviewer-profile",
        permission_profile_id="permission-profile",
        budget=budget,
        target_workspace=str(workspace),
    )
    accepted_target = AcceptedTargetResult.model_construct(
        target_id="architecture",
        artifact_refs=[artifact_ref],
    )
    accepted_fleet = AcceptedMemoryFleetResult.model_construct(
        accepted_memory_fleet_result_id="accepted-fleet-1",
        fleet_run_id=spec.fleet_run_id,
        accepted_target_result_refs=["accepted-target-1"],
    )
    manifest = _manifest(tmp_path, output_root)
    encoded = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    publication_id = hashlib.sha256(encoded).hexdigest()[:16]
    publication_root = tmp_path / "published" / publication_id
    publication_root.mkdir(parents=True)
    publication_path = publication_root / "repository-brain.json"
    publication_path.write_bytes(encoded)
    return _LoaderFixture(
        publication_path=publication_path,
        manifest=manifest,
        spec=spec,
        target_spec=target_spec,
        accepted_fleet=accepted_fleet,
        accepted_target=accepted_target,
    )


def _manifest(tmp_path: Path, output_root: Path) -> RepositoryBrainManifest:
    return RepositoryBrainManifest(
        repository_id="repository-1",
        repository_revision="revision-1",
        graph_snapshot_id="snapshot-1",
        graph_snapshot_root=str(tmp_path / "graph"),
        enrichment_overlay_id="overlay-1",
        fleet_run_id="fleet-1",
        memory_runtime_root=str(tmp_path / "runtime"),
        memory_output_root=str(output_root),
        accepted_memory_fleet_result_id="accepted-fleet-1",
        memory_target_catalog_id="catalog-1",
        memory_target_catalog_version="1",
        accepted_target_result_refs=["accepted-target-1"],
    )


def _artifact_ref(path: Path, relative_path: str) -> CandidateArtifactRef:
    return CandidateArtifactRef(
        artifact_id="artifact-1",
        relative_path=relative_path,
        revision=3,
        digest=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
