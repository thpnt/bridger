"""Bounded Stage 5 retry helpers for classified runtime failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from bridger.llm.errors import LLMError
from bridger.runtime_timing import current_collector

ResultT = TypeVar("ResultT")
Sleep = Callable[[float], Awaitable[None]]
AttemptHook = Callable[[int], Awaitable[None]]
RetryHook = Callable[[int, float, LLMError], Awaitable[None]]


async def run_provider_with_retry(
    operation: Callable[[], Awaitable[ResultT]],
    *,
    before_attempt: AttemptHook,
    on_retry: RetryHook | None = None,
    sleep: Sleep = asyncio.sleep,
) -> ResultT:
    """Run at most three explicitly classified provider attempts."""
    for attempt in range(1, 4):
        await before_attempt(attempt)
        try:
            metrics = current_collector()
            if metrics is None:
                return await operation()
            with metrics.attempt(attempt):
                return await operation()
        except LLMError as error:
            error.attempt_count = attempt
            if not error.retryable or attempt == 3:
                raise
            retry_after = getattr(error, "retry_after_seconds", None)
            delay = float(retry_after) if retry_after is not None else float(attempt)
            if on_retry is not None:
                await on_retry(attempt + 1, delay, error)
            metrics = current_collector()
            started_ns = metrics.clock_ns() if metrics is not None else 0
            try:
                await sleep(delay)
            finally:
                if metrics is not None:
                    metrics.add_backoff(
                        max(0, (metrics.clock_ns() - started_ns) / 1_000_000)
                    )
    raise AssertionError("provider retry loop exhausted without returning or raising")


async def retry_read_only_tool_once(
    operation: Callable[[], Awaitable[ResultT]],
    *,
    is_transient: Callable[[Exception], bool],
) -> ResultT:
    """Retry one identical read-only dispatch only after explicit classification."""
    try:
        return await operation()
    except Exception as error:
        if not is_transient(error):
            raise
    return await operation()


__all__ = ["retry_read_only_tool_once", "run_provider_with_retry"]
