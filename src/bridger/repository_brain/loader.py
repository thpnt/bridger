"""Read-only loading of canonical accepted Repository Brain documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import MemoryFleetSpec
from bridger.contracts.repository_brain import RepositoryBrainManifest
from bridger.memory.errors import PersistenceRecoveryError
from bridger.memory.evaluation.acceptance import resolve_accepted_target_result
from bridger.memory.evaluation.fleet_acceptance import (
    resolve_accepted_memory_fleet_result,
)
from bridger.memory.persistence.durability import FleetRuntimeStore
from bridger.memory.persistence.store import require_path_segment

_MANIFEST_NAME = "repository-brain.json"


class RepositoryBrainLoadError(RuntimeError):
    """A published Repository Brain failed provenance or content validation."""


@dataclass(frozen=True)
class BrainDocument:
    document_id: str
    semantic_owner: str
    relative_path: str
    artifact_revision: int
    digest: str
    content: str


@dataclass(frozen=True)
class LoadedRepositoryBrain:
    publication_id: str
    manifest: RepositoryBrainManifest
    documents: tuple[BrainDocument, ...]


def load_repository_brain(publication_path: Path) -> LoadedRepositoryBrain:
    """Resolve one publication through the existing acceptance authorities."""
    try:
        if publication_path.name != _MANIFEST_NAME or not publication_path.is_file():
            raise ValueError("publication path is not a Repository Brain manifest")
        publication_id = publication_path.parent.name
        require_path_segment(publication_id, "publication_id")
        encoded_manifest = publication_path.read_bytes()
        if hashlib.sha256(encoded_manifest).hexdigest()[:16] != publication_id:
            raise ValueError("publication path does not match manifest identity")
        manifest = RepositoryBrainManifest.model_validate_json(encoded_manifest)

        require_path_segment(manifest.fleet_run_id, "fleet_run_id")
        runtime_root = Path(manifest.memory_runtime_root).resolve()
        fleet_spec = MemoryFleetSpec.model_validate_json(
            (runtime_root / manifest.fleet_run_id / "fleet-spec.json").read_bytes()
        )
        _validate_fleet_binding(manifest, fleet_spec, runtime_root)

        store = FleetRuntimeStore(fleet_spec)
        try:
            accepted_fleet = resolve_accepted_memory_fleet_result(
                store,
                manifest.accepted_memory_fleet_result_id,
            )
            if (
                accepted_fleet.accepted_target_result_refs
                != manifest.accepted_target_result_refs
            ):
                raise ValueError("manifest accepted target inventory has drifted")
            target_specs = store.load_target_specs()
            accepted_targets = [
                resolve_accepted_target_result(store, target_spec, accepted_ref)
                for target_spec, accepted_ref in zip(
                    target_specs,
                    accepted_fleet.accepted_target_result_refs,
                    strict=True,
                )
            ]
        finally:
            store.close()

        documents = _load_documents(manifest, accepted_targets)
        return LoadedRepositoryBrain(
            publication_id=publication_id,
            manifest=manifest,
            documents=tuple(documents),
        )
    except RepositoryBrainLoadError:
        raise
    except (
        OSError,
        PersistenceRecoveryError,
        UnicodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise RepositoryBrainLoadError(
            "could not load a coherent published Repository Brain"
        ) from error


def _validate_fleet_binding(
    manifest: RepositoryBrainManifest,
    fleet_spec: MemoryFleetSpec,
    runtime_root: Path,
) -> None:
    source = fleet_spec.source
    if (
        fleet_spec.fleet_run_id != manifest.fleet_run_id
        or source.repository_id != manifest.repository_id
        or source.repository_revision != manifest.repository_revision
        or source.graph_snapshot_id != manifest.graph_snapshot_id
        or source.enrichment_overlay_id != manifest.enrichment_overlay_id
        or fleet_spec.target_catalog_id != manifest.memory_target_catalog_id
        or fleet_spec.target_catalog_version != manifest.memory_target_catalog_version
        or Path(fleet_spec.runtime_root).resolve() != runtime_root
        or Path(fleet_spec.output_root).resolve()
        != Path(manifest.memory_output_root).resolve()
    ):
        raise ValueError("fleet spec does not match Repository Brain provenance")


def _load_documents(
    manifest: RepositoryBrainManifest,
    accepted_targets: list[AcceptedTargetResult],
) -> list[BrainDocument]:
    output_root = Path(manifest.memory_output_root).resolve()
    documents: list[BrainDocument] = []
    document_ids: set[str] = set()
    relative_paths: set[str] = set()
    for accepted_target in accepted_targets:
        target_id = accepted_target.target_id
        require_path_segment(target_id, "target_id")
        workspace = output_root / target_id
        workspace_resolved = workspace.resolve()
        for artifact_ref in accepted_target.artifact_refs:
            artifact_path = workspace / artifact_ref.relative_path
            if artifact_path.is_symlink():
                raise ValueError("accepted artifact must not be a symlink")
            resolved = artifact_path.resolve()
            try:
                resolved.relative_to(workspace_resolved)
            except ValueError as error:
                raise ValueError(
                    "accepted artifact escapes target workspace"
                ) from error
            if not resolved.is_file():
                raise ValueError("accepted artifact is not a regular file")
            if resolved.suffix != ".md":
                raise ValueError("accepted artifact is not Markdown")
            content_bytes = resolved.read_bytes()
            if hashlib.sha256(content_bytes).hexdigest() != artifact_ref.digest:
                raise ValueError("accepted artifact digest mismatch")
            relative_path = f"{target_id}/{artifact_ref.relative_path}"
            if artifact_ref.artifact_id in document_ids:
                raise ValueError("accepted artifact identities must be unique")
            if relative_path in relative_paths:
                raise ValueError("accepted artifact paths must be unique")
            document_ids.add(artifact_ref.artifact_id)
            relative_paths.add(relative_path)
            documents.append(
                BrainDocument(
                    document_id=artifact_ref.artifact_id,
                    semantic_owner=target_id,
                    relative_path=relative_path,
                    artifact_revision=artifact_ref.revision,
                    digest=artifact_ref.digest,
                    content=content_bytes.decode("utf-8"),
                )
            )
    return documents


__all__ = [
    "BrainDocument",
    "LoadedRepositoryBrain",
    "RepositoryBrainLoadError",
    "load_repository_brain",
]
