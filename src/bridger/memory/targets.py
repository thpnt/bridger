"""Loading and cross-artifact validation for static memory target YAML."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from bridger.contracts.memory.core import MemoryTargetCatalog, TargetDefinition
from bridger.memory.errors import InvalidTargetArtifacts

_CATALOG_FILE = "catalog.yaml"
_TARGETS_DIRECTORY = "targets"
_SUPPORTED_SCHEMA_VERSION = 1

ModelT = TypeVar("ModelT", MemoryTargetCatalog, TargetDefinition)


def load_target_artifacts(
    artifact_root: Path,
) -> tuple[MemoryTargetCatalog, list[TargetDefinition]]:
    """Load one exact catalog bundle from its documented YAML layout."""
    root = Path(artifact_root)
    catalog = _load_yaml_model(root / _CATALOG_FILE, MemoryTargetCatalog)
    target_root = root / _TARGETS_DIRECTORY
    target_paths = sorted((*target_root.glob("*.yaml"), *target_root.glob("*.yml")))
    definitions = [
        _load_yaml_model(target_path, TargetDefinition) for target_path in target_paths
    ]
    validated_catalog, definitions_by_target = _resolve_catalog_definitions(
        catalog,
        definitions,
        require_exact=True,
    )
    return validated_catalog, [
        definitions_by_target[entry.target_id] for entry in validated_catalog.targets
    ]


def _resolve_catalog_definitions(
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    *,
    require_exact: bool,
    required_target_ids: set[str] | None = None,
) -> tuple[MemoryTargetCatalog, dict[str, TargetDefinition]]:
    """Validate and resolve each catalog entry to one exact target definition."""
    try:
        validated_catalog = MemoryTargetCatalog.model_validate(
            catalog.model_dump(mode="python")
        )
        validated_definitions = [
            TargetDefinition.model_validate(definition.model_dump(mode="python"))
            for definition in definitions
        ]
    except (AttributeError, ValidationError, ValueError) as error:
        raise InvalidTargetArtifacts("target artifact schema is invalid") from error
    if validated_catalog.schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise InvalidTargetArtifacts("unsupported target catalog schema version")
    if any(
        definition.schema_version != _SUPPORTED_SCHEMA_VERSION
        for definition in validated_definitions
    ):
        raise InvalidTargetArtifacts("unsupported target definition schema version")

    definitions_by_identity: dict[tuple[str, str], TargetDefinition] = {}
    for definition in validated_definitions:
        identity = (definition.target_id, definition.target_contract_version)
        if identity in definitions_by_identity:
            raise InvalidTargetArtifacts(
                "duplicate target definition identity: "
                f"{definition.target_id}@{definition.target_contract_version}"
            )
        definitions_by_identity[identity] = definition

    catalog_target_ids = {entry.target_id for entry in validated_catalog.targets}
    selected_target_ids = (
        catalog_target_ids if required_target_ids is None else required_target_ids
    )
    unknown_target_ids = selected_target_ids - catalog_target_ids
    if unknown_target_ids:
        raise InvalidTargetArtifacts(
            f"target is absent from catalog: {sorted(unknown_target_ids)[0]}"
        )

    definitions_by_target: dict[str, TargetDefinition] = {}
    for entry in validated_catalog.targets:
        if entry.target_id not in selected_target_ids:
            continue
        identity = (entry.target_id, entry.target_contract_version)
        resolved_definition = definitions_by_identity.get(identity)
        if resolved_definition is None:
            raise InvalidTargetArtifacts(
                "catalog target definition is missing or version-mismatched: "
                f"{entry.target_id}@{entry.target_contract_version}"
            )
        definitions_by_target[entry.target_id] = resolved_definition

    if require_exact:
        referenced_identities = {
            (entry.target_id, entry.target_contract_version)
            for entry in validated_catalog.targets
        }
        unexpected = set(definitions_by_identity) - referenced_identities
        if unexpected:
            target_id, version = sorted(unexpected)[0]
            raise InvalidTargetArtifacts(
                f"target definition is not referenced by catalog: {target_id}@{version}"
            )
    return validated_catalog, definitions_by_target


def _load_yaml_model(
    path: Path,
    model_type: type[ModelT],
) -> ModelT:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise InvalidTargetArtifacts(f"invalid target artifact: {path}") from error
    if not isinstance(raw, dict):
        raise InvalidTargetArtifacts(f"target artifact is not an object: {path}")
    try:
        return model_type.model_validate(raw)
    except ValidationError as error:
        raise InvalidTargetArtifacts(
            f"target artifact schema is invalid: {path}"
        ) from error


__all__ = ["load_target_artifacts"]
