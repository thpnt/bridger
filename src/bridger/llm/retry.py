import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from bridger.llm.errors import LLMError
from bridger.llm.profiles import RetryPolicy

ResultT = TypeVar("ResultT")
SleepCallable = Callable[[float], Awaitable[None]]


async def run_with_retries(
    operation: Callable[[], Awaitable[ResultT]],
    *,
    policy: RetryPolicy,
    sleep: SleepCallable = asyncio.sleep,
) -> tuple[ResultT, int]:
    """Run an async operation with bounded retries for retryable LLM errors."""
    attempt = 1
    delay = policy.initial_backoff_seconds
    while True:
        try:
            return await operation(), attempt - 1
        except LLMError as error:
            if not error.retryable or attempt >= policy.max_attempts:
                error.attempt_count = attempt
                raise
            retry_after = getattr(error, "retry_after_seconds", None)
            sleep_seconds = retry_after if retry_after is not None else delay
            await sleep(float(sleep_seconds))
            delay = min(delay * 2, policy.max_backoff_seconds)
            attempt += 1
