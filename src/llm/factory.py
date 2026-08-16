import os

from openai import AsyncOpenAI

from llm.client import LLMClient
from llm.errors import LLMConfigurationError
from llm.profiles import LLMProfile, resolve_llm_profile
from llm.providers.openai import OpenAILLMClient


def create_llm_client(profile_name: str = "balanced") -> LLMClient:
    """Construct a provider-independent LLM client from environment settings."""
    profile = resolve_llm_profile(profile_name)
    return create_llm_client_from_profile(profile)


def create_llm_client_from_profile(profile: LLMProfile) -> LLMClient:
    """Construct a provider-independent client from an explicit typed profile."""
    if profile.provider != "openai":
        raise LLMConfigurationError(f"Unsupported LLM provider: {profile.provider}")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is required for OpenAI LLM calls")

    client = AsyncOpenAI(api_key=api_key, max_retries=0)
    return OpenAILLMClient(openai_client=client, profile=profile)
