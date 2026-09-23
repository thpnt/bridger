from openai import AsyncOpenAI

from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMConfigurationError
from bridger.llm.profiles import LLMProfile, resolve_llm_profile
from bridger.llm.providers.openai import OpenAILLMClient
from bridger.settings.config import load_config
from bridger.settings.credentials import resolve_openai_api_key


def create_llm_client(profile_name: str = "balanced") -> LLMClient:
    """Construct a provider-independent LLM client from user settings."""
    profile = resolve_llm_profile(profile_name, model=load_config().openai.model)
    return create_llm_client_from_profile(profile)


def create_llm_client_from_profile(profile: LLMProfile) -> LLMClient:
    """Construct a provider-independent client from an explicit typed profile."""
    if profile.provider != "openai":
        raise LLMConfigurationError(f"Unsupported LLM provider: {profile.provider}")

    client = AsyncOpenAI(api_key=resolve_openai_api_key(), max_retries=0)
    return OpenAILLMClient(openai_client=client, profile=profile)
