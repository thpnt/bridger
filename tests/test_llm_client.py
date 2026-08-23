"""Focused provider-neutral LLM client lifecycle tests."""

import asyncio

from bridger.llm.profiles import LLMProfile
from bridger.llm.providers.openai import OpenAILLMClient


def test_openai_client_close_awaits_underlying_client() -> None:
    closed = False

    class FakeAsyncOpenAI:
        async def close(self) -> None:
            nonlocal closed
            closed = True

    client = OpenAILLMClient(
        openai_client=FakeAsyncOpenAI(),
        profile=LLMProfile(
            name="test",
            provider="openai",
            model="test-model",
        ),
    )

    asyncio.run(client.close())

    assert closed
