"""Layer 3 deterministic graph construction."""

from bridger.graph.enrichment import (
    COMMUNITY_REPRESENTATIVE_LIMIT,
    ENRICHMENT_SCHEMA_VERSION,
    LAYER5_GENERATOR_VERSION,
    InvalidGraphEnrichment,
    build_all_community_evidence,
    build_community_evidence,
    canonical_serialize_community_evidence,
    community_deterministic_features,
    community_name_input_fingerprint,
    create_community_name_record,
    create_graph_enrichment,
    enrich_graph_snapshot,
    load_graph_enrichment,
    validate_graph_enrichment,
)
from bridger.graph.errors import FullRebuildRequired, InvalidGraphSnapshot
from bridger.graph.intelligence import (
    analyze_graph_structure,
    build_graph_intelligence,
    compute_community_structure,
    construct_repository_graph,
)
from bridger.graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot,
    load_graph_snapshot_structural_state,
    update_graph_snapshot,
    validate_graph_snapshot,
)
from bridger.graph.validation import validate_graph_intelligence

__all__ = [
    "analyze_graph_structure",
    "build_all_community_evidence",
    "build_community_evidence",
    "build_graph_intelligence",
    "compute_community_structure",
    "construct_repository_graph",
    "create_graph_snapshot",
    "create_community_name_record",
    "create_graph_enrichment",
    "canonical_serialize_community_evidence",
    "community_deterministic_features",
    "community_name_input_fingerprint",
    "COMMUNITY_REPRESENTATIVE_LIMIT",
    "ENRICHMENT_SCHEMA_VERSION",
    "LAYER5_GENERATOR_VERSION",
    "FullRebuildRequired",
    "InvalidGraphSnapshot",
    "InvalidGraphEnrichment",
    "enrich_graph_snapshot",
    "load_graph_enrichment",
    "load_graph_snapshot",
    "load_graph_snapshot_structural_state",
    "update_graph_snapshot",
    "validate_graph_enrichment",
    "validate_graph_intelligence",
    "validate_graph_snapshot",
]
