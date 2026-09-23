from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import bridger.cli as cli
import bridger.llm.factory as factory
from bridger.init_pipeline import ReasoningEffort
from bridger.llm.profiles import LLMProfile
from bridger.settings import config, credentials

runner = CliRunner()


@pytest.mark.parametrize(
    "arguments, expected",
    [([], ReasoningEffort.MEDIUM), (["--reasoning", "low"], ReasoningEffort.LOW)],
)
def test_init_reasoning_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arguments: list[str],
    expected: ReasoningEffort,
) -> None:
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n[openai]\nmodel = "gpt-5.6-terra"\nreasoning = "medium"\n'
    )
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: list[object] = []
    monkeypatch.setattr(
        cli, "build_repository_brain", lambda settings, **_: captured.append(settings)
    )
    result = runner.invoke(cli.app, ["init", *arguments])
    assert result.exit_code == 0, result.output
    assert captured[0].reasoning_effort is expected  # type: ignore[union-attr]
    assert captured[0].openai_model == "gpt-5.6-terra"  # type: ignore[union-attr]


def test_invalid_config_fails_before_init_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.toml").write_text("schema_version = 2\n")
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    started = []
    monkeypatch.setattr(
        cli, "build_repository_brain", lambda *_args, **_kwargs: started.append(True)
    )
    result = runner.invoke(cli.app, ["init"])
    assert result.exit_code == 1
    assert "schema_version" in result.output
    assert str(tmp_path / "config.toml") in result.output
    assert not started


def test_missing_credential_fails_before_init_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_: None)
    started = []
    monkeypatch.setattr(
        cli, "build_repository_brain", lambda *_args, **_kwargs: started.append(True)
    )
    result = runner.invoke(cli.app, ["init"])
    assert result.exit_code == 1
    assert "bridger auth set-key" in result.output
    assert not started


def test_factory_passes_keyring_credential_to_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_: "stored-key")
    calls = []

    def openai_client(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(factory, "AsyncOpenAI", openai_client)
    profile = LLMProfile(name="test", provider="openai", model="model")
    client = factory.create_llm_client_from_profile(profile)
    assert calls == [{"api_key": "stored-key", "max_retries": 0}]
    assert client._profile is profile


def test_injected_client_needs_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bridger.llm.providers.openai import OpenAILLMClient

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda *_: pytest.fail("keyring should not be accessed"),
    )
    profile = LLMProfile(name="test", provider="openai", model="model")
    client = OpenAILLMClient(openai_client=SimpleNamespace(), profile=profile)
    assert client._profile is profile
