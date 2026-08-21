"""Bridger-owned V0 enrichment-record construction."""

import uuid

from bridger.contracts.enrichment import CommunityEvidence, EnrichmentRecord
from bridger.graph.enrichment.evidence import community_deterministic_features


def create_community_name_record(
    evidence: CommunityEvidence,
    *,
    member_signature: str,
    name: str,
    enrichment_id: str | None = None,
) -> EnrichmentRecord:
    """Materialize one authoritative community-name annotation record."""
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("community name must be non-empty")
    if not member_signature:
        raise ValueError("community member_signature is required")
    return EnrichmentRecord(
        enrichment_id=enrichment_id or f"enrichment-{uuid.uuid4().hex}",
        target_type="community",
        target_ref={
            "community_id": evidence.community_id,
            "member_signature": member_signature,
        },
        annotation_type="name",
        value=normalized_name,
        deterministic_features=community_deterministic_features(evidence),
    )


__all__ = ["create_community_name_record"]
