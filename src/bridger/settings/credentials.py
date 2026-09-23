"""OpenAI API key storage and resolution."""

import os
from dataclasses import dataclass
from enum import StrEnum

import keyring

KEYRING_SERVICE = "bridger"
KEYRING_ACCOUNT = "openai_api_key"


class BridgerCredentialError(RuntimeError):
    """An OpenAI credential could not be used."""


class OpenAICredentialNotFoundError(BridgerCredentialError):
    """Neither the environment nor keyring contains a credential."""


class CredentialStoreUnavailableError(BridgerCredentialError):
    """The system credential store cannot be accessed."""


class CredentialSource(StrEnum):
    ENVIRONMENT = "environment"
    KEYRING = "keyring"


@dataclass(frozen=True)
class ResolvedCredential:
    value: str
    source: CredentialSource


def environment_openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY", "").strip() or None


def set_openai_api_key(api_key: str) -> None:
    value = api_key.strip()
    if not value:
        raise ValueError("OpenAI API key must not be empty")
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, value)
    except Exception as error:
        raise CredentialStoreUnavailableError(_STORE_ERROR) from error


def get_stored_openai_api_key() -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or None
    except Exception as error:
        raise CredentialStoreUnavailableError(_STORE_ERROR) from error


def remove_openai_api_key() -> bool:
    if get_stored_openai_api_key() is None:
        return False
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception as error:
        raise CredentialStoreUnavailableError(_STORE_ERROR) from error
    return True


def resolve_openai_credential() -> ResolvedCredential:
    environment_key = environment_openai_api_key()
    if environment_key:
        return ResolvedCredential(environment_key, CredentialSource.ENVIRONMENT)
    stored_key = get_stored_openai_api_key()
    if stored_key:
        return ResolvedCredential(stored_key, CredentialSource.KEYRING)
    raise OpenAICredentialNotFoundError(
        "OpenAI API access is not configured.\n\n"
        "Run:\n  bridger auth set-key\n\n"
        "or set:\n  OPENAI_API_KEY"
    )


def resolve_openai_api_key() -> str:
    return resolve_openai_credential().value


_STORE_ERROR = (
    "System credential storage is unavailable.\n\n"
    "You can configure OpenAI through the environment instead:\n\n"
    '  export OPENAI_API_KEY="..."'
)
