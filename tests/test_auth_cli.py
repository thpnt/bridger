from pathlib import Path
from types import SimpleNamespace

import pytest
from keyring.errors import NoKeyringError, PasswordDeleteError
from typer.testing import CliRunner

import bridger.cli as cli
from bridger.settings import config, credentials

runner = CliRunner()


@pytest.fixture
def auth_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    stored: dict[str, str] = {}

    def get_password(_service: str, _account: str) -> str | None:
        return stored.get("key")

    def set_password(_service: str, _account: str, value: str) -> None:
        stored["key"] = value

    def delete_password(_service: str, _account: str) -> None:
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
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return backend


def test_set_key_hides_input_and_preserves_config(
    auth_backend: SimpleNamespace, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.toml"
    original = 'schema_version = 1\n[openai]\nreasoning = "medium"\n'
    config_path.write_text(original)
    result = runner.invoke(cli.app, ["auth", "set-key"], input="secret-value\n")
    assert result.exit_code == 0, result.output
    assert auth_backend.stored["key"] == "secret-value"
    assert "secret-value" not in result.output
    assert config_path.read_text() == original


def test_set_key_creates_user_config(
    auth_backend: SimpleNamespace, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.toml"
    result = runner.invoke(cli.app, ["auth", "set-key"], input="secret-value\n")
    assert result.exit_code == 0, result.output
    assert config_path.exists()
    assert config.load_config().openai.model == "gpt-6-sol"
    assert "secret-value" not in config_path.read_text()


def test_set_key_confirms_replacement_and_reports_environment(
    auth_backend: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_backend.stored["key"] = "old"
    declined = runner.invoke(cli.app, ["auth", "set-key"], input="n\n")
    assert declined.exit_code == 0
    assert auth_backend.stored["key"] == "old"
    monkeypatch.setenv("OPENAI_API_KEY", "environment")
    replaced = runner.invoke(cli.app, ["auth", "set-key"], input="y\nnew\n")
    assert replaced.exit_code == 0, replaced.output
    assert auth_backend.stored["key"] == "new"
    assert "OPENAI_API_KEY is currently set" in replaced.output


def test_set_key_rejects_blank_input(auth_backend: SimpleNamespace) -> None:
    result = runner.invoke(cli.app, ["auth", "set-key"], input="   \n")
    assert result.exit_code == 1
    assert not auth_backend.stored


def test_status_reports_source_without_secret(
    auth_backend: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = runner.invoke(cli.app, ["auth", "status"])
    assert missing.exit_code == 0
    assert "not configured" in missing.output
    auth_backend.stored["key"] = "stored-secret"
    stored = runner.invoke(cli.app, ["auth", "status"])
    assert "Source: system credential store" in stored.output
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    environment = runner.invoke(cli.app, ["auth", "status"])
    assert "Source: OPENAI_API_KEY" in environment.output
    assert "stored-secret" not in stored.output
    assert "env-secret" not in environment.output


def test_remove_is_idempotent_and_keeps_environment_active(
    auth_backend: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_backend.stored["key"] = "stored"
    monkeypatch.setenv("OPENAI_API_KEY", "environment")
    removed = runner.invoke(cli.app, ["auth", "remove"])
    assert removed.exit_code == 0
    assert "removed" in removed.output
    assert "remains active" in removed.output
    assert "key" not in auth_backend.stored
    missing = runner.invoke(cli.app, ["auth", "remove"])
    assert missing.exit_code == 0
    assert "No stored" in missing.output


def test_backend_error_is_clean(
    auth_backend: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_: object) -> None:
        raise NoKeyringError("private backend detail")

    monkeypatch.setattr(auth_backend, "get_password", unavailable)
    result = runner.invoke(cli.app, ["auth", "set-key"], input="secret\n")
    assert result.exit_code == 1
    assert "System credential storage is unavailable" in result.output
    assert "private backend detail" not in result.output
    assert "secret" not in result.output
