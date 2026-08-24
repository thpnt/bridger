"""Stable asynchronous execution for V0 community-name batches."""

import asyncio
from dataclasses import dataclass

from bridger.contracts.enrichment import CommunityEvidence, CommunityNameBatch
from bridger.contracts.token_usage import TokenUsage
from bridger.graph.enrichment.naming import (
    COMMUNITY_NAME_BATCH_SIZE,
    COMMUNITY_NAME_MAX_ATTEMPTS,
    InvalidCommunityNameBatch,
    build_community_name_request,
    validate_community_name_batch,
)
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMError, LLMStructuredOutputError
from bridger.llm.models import LLMUsage


@dataclass(frozen=True)
class CommunityNameBatchRequest:
    """One deterministic bounded unit of community-name work."""

    batch_id: str
    evidence: tuple[CommunityEvidence, ...]


@dataclass(frozen=True)
class CommunityNameBatchResult:
    """Isolated terminal result returned by one batch worker."""

    batch: CommunityNameBatchRequest
    attempts: int
    names: dict[int, str] | None = None
    error_category: str | None = None
    usage: TokenUsage = TokenUsage()


def build_community_name_batches(
    evidence: list[CommunityEvidence],
) -> list[CommunityNameBatchRequest]:
    """Sort generation targets and partition them into stable bounded batches."""
    ordered = sorted(evidence, key=lambda item: item.community_id)
    return [
        CommunityNameBatchRequest(
            batch_id=f"community-names-{index // COMMUNITY_NAME_BATCH_SIZE:04d}",
            evidence=tuple(ordered[index : index + COMMUNITY_NAME_BATCH_SIZE]),
        )
        for index in range(0, len(ordered), COMMUNITY_NAME_BATCH_SIZE)
    ]


async def execute_community_name_batches(
    client: LLMClient,
    batches: list[CommunityNameBatchRequest],
    *,
    profile_version: str,
    max_concurrency: int,
) -> list[CommunityNameBatchResult]:
    """Execute every batch with isolated retries and bounded model concurrency."""
    semaphore = asyncio.Semaphore(max_concurrency)
    pending = [
        _execute_community_name_batch(
            client,
            batch,
            profile_version=profile_version,
            semaphore=semaphore,
        )
        for batch in batches
    ]
    outcomes = await asyncio.gather(*pending, return_exceptions=True)
    results: list[CommunityNameBatchResult] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)
    return sorted(results, key=lambda result: result.batch.batch_id)


async def _execute_community_name_batch(
    client: LLMClient,
    batch: CommunityNameBatchRequest,
    *,
    profile_version: str,
    semaphore: asyncio.Semaphore,
) -> CommunityNameBatchResult:
    error_category = "provider_error"
    usage = TokenUsage()
    for attempts in range(1, COMMUNITY_NAME_MAX_ATTEMPTS + 1):
        try:
            request = build_community_name_request(
                batch.evidence,
                profile_version=profile_version,
            )
            async with semaphore:
                response = await client.generate(
                    request,
                    output_type=CommunityNameBatch,
                )
            usage = usage.add(_token_usage(response.usage))
            if response.structured_output is None:
                error_category = "structured_output_error"
                continue
            names = validate_community_name_batch(
                response.structured_output,
                batch.evidence,
            )
        except LLMStructuredOutputError as error:
            usage = usage.add(_token_usage(error.usage))
            error_category = "structured_output_error"
        except LLMError as error:
            usage = usage.add(_token_usage(getattr(error, "usage", None)))
            error_category = "provider_error"
        except InvalidCommunityNameBatch:
            error_category = "response_validation_error"
        else:
            return CommunityNameBatchResult(
                batch=batch,
                attempts=attempts,
                names=names,
                usage=usage,
            )
    return CommunityNameBatchResult(
        batch=batch,
        attempts=COMMUNITY_NAME_MAX_ATTEMPTS,
        error_category=error_category,
        usage=usage,
    )


def _token_usage(usage: LLMUsage | None) -> TokenUsage:
    """Convert reported provider usage without estimating missing fields."""
    if usage is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=usage.input_tokens or 0,
        cached_input_tokens=usage.cached_input_tokens or 0,
        cache_write_tokens=usage.cache_write_tokens or 0,
        output_tokens=usage.output_tokens or 0,
    )


__all__ = [
    "CommunityNameBatchRequest",
    "CommunityNameBatchResult",
    "build_community_name_batches",
    "execute_community_name_batches",
]
