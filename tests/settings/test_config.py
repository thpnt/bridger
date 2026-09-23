from pathlib import Path

import pytest

from bridger.settings import config


@pytest.fixture
def config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    return tmp_path / "config.toml"


def test_missing_config_uses_existing_reasoning_default(config_path: Path) -> None:
    loaded = config.load_config()
    assert loaded.schema_version == 1
    assert loaded.openai.reasoning == "xhigh"
    assert loaded.openai.model == "gpt-5.6"
    assert not config_path.exists()


def test_valid_config_loads_values(config_path: Path) -> None:
    config_path.write_text(
        'schema_version = 1\n[openai]\nmodel = "test-model"\nreasoning = "medium"\n'
    )
    loaded = config.load_config()
    assert loaded.openai.model == "test-model"
    assert loaded.openai.reasoning == "medium"


def test_partial_user_config_inherits_bundled_model(config_path: Path) -> None:
    config_path.write_text('schema_version = 1\n[openai]\nreasoning = "medium"\n')
    loaded = config.load_config()
    assert loaded.openai.model == "gpt-5.6"
    assert loaded.openai.reasoning == "medium"


def test_setup_copies_bundled_config_once(config_path: Path) -> None:
    assert config.ensure_user_config() == config_path
    original = config_path.read_text()
    assert 'model = "gpt-5.6"' in original
    assert 'reasoning = "xhigh"' in original
    config_path.write_text('schema_version = 1\n[openai]\nmodel = "custom"\n')
    config.ensure_user_config()
    assert config_path.read_text() == 'schema_version = 1\n[openai]\nmodel = "custom"\n'


@pytest.mark.parametrize(
    "content, expected",
    [
        ("[openai\n", "Invalid Bridger configuration"),
        ("schema_version = 2\n", "schema_version"),
        ('[openai]\nmodel = "test"\n', "schema_version"),
        ('schema_version = 1\n[openai]\nmodel = ""\n', "openai.model"),
        (
            'schema_version = 1\n[openai]\nreasoning = "super-high"\n',
            "openai.reasoning",
        ),
        ("schema_version = 1\n[openai]\nmodel = 4\n", "openai.model"),
        ('schema_version = 1\n[openai]\napi_key = "secret"\n', "openai.api_key"),
    ],
)
def test_invalid_config_is_explicit_and_does_not_echo_values(
    config_path: Path, content: str, expected: str
) -> None:
    config_path.write_text(content)
    with pytest.raises(config.BridgerConfigurationError) as failure:
        config.load_config()
    assert str(config_path) in str(failure.value)
    assert expected in str(failure.value)
    assert "secret" not in str(failure.value)
