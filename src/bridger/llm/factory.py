import os

from openai import AsyncOpenAI

from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMConfigurationError
from bridger.llm.profiles import resolve_llm_profile
from bridger.llm.providers.openai import OpenAILLMClient


def create_llm_client(profile_name: str = "balanced") -> LLMClient:
    """Construct a provider-independent LLM client from environment settings."""
    profile = resolve_llm_profile(profile_name)
    if profile.provider != "openai":
        raise LLMConfigurationError(f"Unsupported LLM provider: {profile.provider}")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is required for OpenAI LLM calls")

    client = AsyncOpenAI(api_key=api_key, max_retries=0)
    return OpenAILLMClient(openai_client=client, profile=profile)
