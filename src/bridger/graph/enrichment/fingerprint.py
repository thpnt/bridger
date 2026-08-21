"""Canonical naming-input fingerprints and private reuse primitives."""

import hashlib
from collections.abc import Iterable

import orjson

from bridger.contracts.enrichment import (
    CommunityEvidence,
    EnrichmentRecord,
    GraphEnrichmentOverlay,
)


def canonical_serialize_community_evidence(evidence: CommunityEvidence) -> bytes:
    """Serialize model-visible community evidence in a canonical JSON form."""
    return orjson.dumps(
        evidence.model_dump(mode="json", exclude_none=True),
        option=orjson.OPT_SORT_KEYS,
    )


def community_name_input_fingerprint(
    evidence: CommunityEvidence,
    *,
    member_signature: str,
    profile_version: str,
    provider: str,
    model: str,
    annotation_type: str = "name",
) -> str:
    """Hash exactly the locked effective community-naming inputs."""
    hasher = hashlib.sha256()
    for value in (
        annotation_type.encode("utf-8"),
        member_signature.encode("utf-8"),
        canonical_serialize_community_evidence(evidence),
        profile_version.encode("utf-8"),
        provider.encode("utf-8"),
        model.encode("utf-8"),
    ):
        hasher.update(value)
        hasher.update(b"\0")
    return hasher.hexdigest()


def _find_reusable_community_name(
    overlays: Iterable[GraphEnrichmentOverlay],
    evidence: CommunityEvidence,
    *,
    member_signature: str,
    profile_version: str,
    provider: str,
    model: str,
) -> str | None:
    fingerprint = community_name_input_fingerprint(
        evidence,
        member_signature=member_signature,
        profile_version=profile_version,
        provider=provider,
        model=model,
    )
    return _index_reusable_community_names(overlays).get(fingerprint)


def _index_reusable_community_names(
    overlays: Iterable[GraphEnrichmentOverlay],
) -> dict[str, str]:
    """Index compatible persisted names without exposing overlay discovery."""
    ordered = sorted(
        overlays,
        key=lambda overlay: (overlay.created_at, overlay.overlay_id),
        reverse=True,
    )
    reusable: dict[str, str] = {}
    for overlay in ordered:
        for record in overlay.records:
            candidate = _reuse_candidate(overlay, record)
            if candidate is not None:
                fingerprint, name = candidate
                reusable.setdefault(fingerprint, name)
    return reusable


def _reuse_candidate(
    overlay: GraphEnrichmentOverlay,
    record: EnrichmentRecord,
) -> tuple[str, str] | None:
    if (
        record.target_type != "community"
        or record.annotation_type != "name"
        or not isinstance(record.target_ref, dict)
        or not isinstance(record.value, str)
    ):
        return None
    community_id = record.target_ref.get("community_id")
    member_signature = record.target_ref.get("member_signature")
    if (
        isinstance(community_id, bool)
        or not isinstance(community_id, int)
        or not isinstance(member_signature, str)
    ):
        return None
    try:
        evidence = CommunityEvidence.model_validate(
            {"community_id": community_id, **record.deterministic_features}
        )
    except ValueError:
        return None
    return (
        community_name_input_fingerprint(
            evidence,
            member_signature=member_signature,
            profile_version=overlay.profile_version,
            provider=overlay.provider,
            model=overlay.model,
        ),
        record.value,
    )


__all__ = [
    "canonical_serialize_community_evidence",
    "community_name_input_fingerprint",
]
