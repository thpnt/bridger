"""Deterministic community-name evidence construction."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from bridger.contracts.enrichment import CommunityEvidence, CommunityRepresentative
from bridger.contracts.graph import GraphBuildResult, RepositoryGraph
from bridger.graph.lifecycle import load_graph_snapshot_structural_state

COMMUNITY_REPRESENTATIVE_LIMIT = 12
_LABEL_LIMIT = 160
_NODE_TYPE_LIMIT = 64
_SOURCE_PATH_LIMIT = 512
_DIVERSITY_LIMIT = 2


def build_community_evidence(
    graph_build: GraphBuildResult,
    community_id: int,
) -> CommunityEvidence:
    """Build canonical bounded naming evidence for one persisted community."""
    structural = load_graph_snapshot_structural_state(graph_build)
    return _build_community_evidence(graph_build.graph, structural, community_id)


def build_all_community_evidence(
    graph_build: GraphBuildResult,
) -> list[CommunityEvidence]:
    """Build canonical naming evidence for every persisted community."""
    structural = load_graph_snapshot_structural_state(graph_build)
    return [
        _build_community_evidence(graph_build.graph, structural, community_id)
        for community_id in sorted(structural["communities"])
    ]


def community_deterministic_features(
    evidence: CommunityEvidence,
) -> dict[str, Any]:
    """Return exactly the evidence persisted on a community-name record."""
    dumped = evidence.model_dump(mode="json", exclude_none=True)
    dumped.pop("community_id")
    return dumped


def _build_community_evidence(
    graph: RepositoryGraph,
    structural: dict[str, Any],
    community_id: int,
) -> CommunityEvidence:
    communities = structural["communities"]
    if community_id not in communities:
        raise ValueError(f"unknown community: {community_id}")

    members = set(communities[community_id])
    important_ids = {
        node["id"] for node in structural["god_nodes"] if node["id"] in members
    }
    ranked_important = _rank_nodes(graph, members, important_ids)
    ranked_other = _rank_nodes(graph, members, members - important_ids)

    important: list[CommunityRepresentative] = []
    other: list[CommunityRepresentative] = []
    selected_ids: set[str] = set()
    labels: set[str] = set()
    diversity_counts: dict[str, Counter[str]] = {
        "source": Counter(),
        "owner": Counter(),
        "family": Counter(),
    }

    for node_id in ranked_important:
        representative = _representative(graph, node_id)
        if representative is None or not _is_new_label(representative, labels):
            continue
        important.append(representative)
        selected_ids.add(node_id)
        _increment_diversity(diversity_counts, graph, node_id, representative)
        if len(important) == COMMUNITY_REPRESENTATIVE_LIMIT:
            break

    remaining = COMMUNITY_REPRESENTATIVE_LIMIT - len(important)
    if remaining:
        for enforce_diversity in (True, False):
            for node_id in ranked_other:
                if node_id in selected_ids:
                    continue
                representative = _representative(graph, node_id)
                if enforce_diversity and not _within_diversity_limits(
                    diversity_counts,
                    graph,
                    node_id,
                    representative,
                ):
                    continue
                if representative is None or not _is_new_label(representative, labels):
                    continue
                other.append(representative)
                selected_ids.add(node_id)
                _increment_diversity(
                    diversity_counts,
                    graph,
                    node_id,
                    representative,
                )
                if len(other) == remaining:
                    break
            if len(other) == remaining:
                break

    return CommunityEvidence(
        community_id=community_id,
        important_representatives=important,
        other_representatives=other,
    )


def _rank_nodes(
    graph: RepositoryGraph,
    community_members: set[str],
    candidates: set[str],
) -> list[str]:
    def rank(node_id: str) -> tuple[int, int, str]:
        internal_neighbors = {
            neighbor
            for neighbor in (*graph.predecessors(node_id), *graph.successors(node_id))
            if neighbor in community_members
        }
        return (-len(internal_neighbors), -graph.degree(node_id), node_id)

    return sorted(candidates, key=rank)


def _representative(
    graph: RepositoryGraph,
    node_id: str,
) -> CommunityRepresentative | None:
    attributes = graph.nodes[node_id]
    label = _sanitize_text(attributes.get("label") or node_id, _LABEL_LIMIT)
    if label is None:
        return None
    return CommunityRepresentative(
        label=label,
        node_type=_node_type(attributes),
        source_path=_source_path(attributes.get("source_file")),
    )


def _node_type(attributes: dict[str, Any]) -> str | None:
    metadata = attributes.get("metadata")
    metadata_values = metadata if isinstance(metadata, dict) else {}
    for value in (
        attributes.get("node_type"),
        attributes.get("kind"),
        attributes.get("type"),
        metadata_values.get("node_type"),
        metadata_values.get("kind"),
        metadata_values.get("type"),
    ):
        sanitized = _sanitize_text(value, _NODE_TYPE_LIMIT)
        if sanitized is not None:
            return sanitized
    return None


def _source_path(value: object) -> str | None:
    sanitized = _sanitize_text(value, _SOURCE_PATH_LIMIT, truncate=False)
    if sanitized is None:
        return None
    normalized = sanitized.replace("\\", "/")
    if normalized.startswith("/") or "://" in normalized or normalized in {"", "."}:
        return None
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    result = path.as_posix()
    if result != normalized or len(result) > _SOURCE_PATH_LIMIT:
        return None
    return result


def _sanitize_text(
    value: object,
    limit: int,
    *,
    truncate: bool = True,
) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in normalized
    )
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    if not truncate:
        return None
    return normalized[: limit - 1].rstrip() + "…"


def _is_new_label(
    representative: CommunityRepresentative,
    labels: set[str],
) -> bool:
    key = representative.label.casefold()
    if key in labels:
        return False
    labels.add(key)
    return True


def _within_diversity_limits(
    counts: dict[str, Counter[str]],
    graph: RepositoryGraph,
    node_id: str,
    representative: CommunityRepresentative | None,
) -> bool:
    if representative is None:
        return False
    keys = _diversity_keys(graph, node_id, representative)
    return all(
        key is None or counts[group][key] < _DIVERSITY_LIMIT
        for group, key in keys.items()
    )


def _increment_diversity(
    counts: dict[str, Counter[str]],
    graph: RepositoryGraph,
    node_id: str,
    representative: CommunityRepresentative,
) -> None:
    for group, key in _diversity_keys(graph, node_id, representative).items():
        if key is not None:
            counts[group][key] += 1


def _diversity_keys(
    graph: RepositoryGraph,
    node_id: str,
    representative: CommunityRepresentative,
) -> dict[str, str | None]:
    attributes = graph.nodes[node_id]
    metadata = attributes.get("metadata")
    metadata_values = metadata if isinstance(metadata, dict) else {}
    parent = next(
        (
            value
            for value in (
                attributes.get("parent_qualified_name"),
                metadata_values.get("parent_qualified_name"),
            )
            if isinstance(value, str) and value.strip()
        ),
        None,
    )
    qualified_name = next(
        (
            value
            for value in (
                attributes.get("qualified_name"),
                metadata_values.get("qualified_name"),
            )
            if isinstance(value, str) and value.strip()
        ),
        None,
    )
    owner = parent.strip().casefold() if parent is not None else None
    if owner is None and qualified_name is not None:
        qualified_parts = re.split(r"::|[.#]", qualified_name.strip())
        if len(qualified_parts) > 1:
            owner = ".".join(qualified_parts[:-1]).casefold()
    family = re.sub(r"[\W\d_]+", "", representative.label.casefold()) or None
    return {
        "source": representative.source_path,
        "owner": owner,
        "family": family,
    }


__all__ = [
    "COMMUNITY_REPRESENTATIVE_LIMIT",
    "build_all_community_evidence",
    "build_community_evidence",
    "community_deterministic_features",
]
