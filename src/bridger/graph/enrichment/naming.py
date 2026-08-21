"""V0 community-naming prompt, request, and response policy."""

import orjson

from bridger.contracts.enrichment import CommunityEvidence, CommunityNameBatch
from bridger.llm.models import LLMMessage, LLMOperation, LLMRequest

COMMUNITY_NAME_BATCH_SIZE = 100
COMMUNITY_NAME_MAX_ATTEMPTS = 3

_COMMUNITY_NAMING_PROMPT = (
    "You are naming clusters in a software repository knowledge graph.\n\n"
    "Give each community a concise 2-5 word plain-language name.\n\n"
    'Examples:\n"Order Management"\n"Payment Flow"\n"Auth Middleware"\n\n'
    "Important representatives are structurally prominent members and should "
    "receive greater weight. Other representatives provide diverse supporting "
    "coverage. Return exactly one name for every supplied community ID."
)


class InvalidCommunityNameBatch(ValueError):
    """Raised when typed model output violates the requested batch contract."""


def build_community_name_request(
    evidence: tuple[CommunityEvidence, ...],
    *,
    profile_version: str,
) -> LLMRequest:
    """Build one structured naming request containing only canonical evidence."""
    payload = orjson.dumps(
        [item.model_dump(mode="json", exclude_none=True) for item in evidence],
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")
    return LLMRequest(
        operation=LLMOperation.COMMUNITY_NAMING,
        profile=profile_version,
        messages=[
            LLMMessage.system(_COMMUNITY_NAMING_PROMPT),
            LLMMessage.user(payload),
        ],
    )


def validate_community_name_batch(
    response: CommunityNameBatch,
    evidence: tuple[CommunityEvidence, ...],
) -> dict[int, str]:
    """Require one valid 2-5 word name for every requested community."""
    requested_ids = {item.community_id for item in evidence}
    names: dict[int, str] = {}
    for community in response.communities:
        community_id = community.community_id
        if community_id not in requested_ids:
            raise InvalidCommunityNameBatch("response contains an unknown community")
        if community_id in names:
            raise InvalidCommunityNameBatch("response contains a duplicate community")
        normalized_name = " ".join(community.name.split())
        word_count = len(normalized_name.split())
        if not normalized_name or not 2 <= word_count <= 5:
            raise InvalidCommunityNameBatch(
                "community name must contain between 2 and 5 words"
            )
        names[community_id] = normalized_name
    if set(names) != requested_ids:
        raise InvalidCommunityNameBatch("response is missing a requested community")
    return names


__all__ = [
    "COMMUNITY_NAME_BATCH_SIZE",
    "COMMUNITY_NAME_MAX_ATTEMPTS",
    "InvalidCommunityNameBatch",
    "build_community_name_request",
    "validate_community_name_batch",
]
