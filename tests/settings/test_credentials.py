from types import SimpleNamespace

import pytest
from keyring.errors import NoKeyringError, PasswordDeleteError

from bridger.settings import credentials


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    stored: dict[str, str] = {}

    def get_password(service: str, account: str) -> str | None:
        assert (service, account) == ("bridger", "openai_api_key")
        return stored.get("key")

    def set_password(service: str, account: str, value: str) -> None:
        assert (service, account) == ("bridger", "openai_api_key")
        stored["key"] = value

    def delete_password(service: str, account: str) -> None:
        assert (service, account) == ("bridger", "openai_api_key")
        if "key" not in stored:
            raise PasswordDeleteError("missing")
        del stored["key"]

    backend = SimpleNamespace(
        stored=stored,
        get_password=get_password,
        set_password=set_password,
        delete_password=delete_password,
    )
    monkeypatch.setattr(credentials, "keyring", backend)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return backend


def test_environment_has_precedence_and_skips_keyring(
    fake_keyring: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_keyring.stored["key"] = "stored"
    monkeypatch.setenv("OPENAI_API_KEY", " env ")
    assert credentials.resolve_openai_credential() == credentials.ResolvedCredential(
        "env", credentials.CredentialSource.ENVIRONMENT
    )


def test_stored_key_used_when_environment_is_blank(
    fake_keyring: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_keyring.stored["key"] = "stored"
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    assert credentials.resolve_openai_api_key() == "stored"


def test_missing_key_raises_typed_error(fake_keyring: SimpleNamespace) -> None:
    with pytest.raises(credentials.OpenAICredentialNotFoundError):
        credentials.resolve_openai_api_key()


def test_set_and_remove_are_local_and_idempotent(fake_keyring: SimpleNamespace) -> None:
    credentials.set_openai_api_key(" stored ")
    assert fake_keyring.stored["key"] == "stored"
    assert credentials.remove_openai_api_key() is True
    assert credentials.remove_openai_api_key() is False


def test_unavailable_backend_is_explicit(
    fake_keyring: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_: object) -> None:
        raise NoKeyringError("backend details")

    monkeypatch.setattr(fake_keyring, "get_password", unavailable)
    with pytest.raises(credentials.CredentialStoreUnavailableError) as failure:
        credentials.resolve_openai_api_key()
    assert "OPENAI_API_KEY" in str(failure.value)
    assert "backend details" not in str(failure.value)


def test_write_failure_is_explicit(
    fake_keyring: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_: object) -> None:
        raise NoKeyringError("backend details")

    monkeypatch.setattr(fake_keyring, "set_password", unavailable)
    with pytest.raises(credentials.CredentialStoreUnavailableError):
        credentials.set_openai_api_key("secret")
    assert not fake_keyring.stored


def test_delete_failure_is_not_treated_as_missing(
    fake_keyring: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_keyring.stored["key"] = "stored"

    def unavailable(*_: object) -> None:
        raise PasswordDeleteError("locked")

    monkeypatch.setattr(fake_keyring, "delete_password", unavailable)
    with pytest.raises(credentials.CredentialStoreUnavailableError):
        credentials.remove_openai_api_key()
