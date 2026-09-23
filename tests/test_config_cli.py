from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

import bridger.cli as cli
import bridger.cli_selector as selector
import bridger.config_cli as config_cli
from bridger.settings import config

runner = CliRunner()


@pytest.fixture
def config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(config.platformdirs, "user_config_path", lambda _: tmp_path)
    path = tmp_path / "config.toml"
    path.write_text(
        'schema_version = 1\n[openai]\nmodel = "gpt-6-sol"\nreasoning = "medium"\n'
    )
    return path


def test_config_commands_are_registered() -> None:
    assert runner.invoke(cli.app, ["config", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["config", "model", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["config", "effort", "--help"]).exit_code == 0


def test_model_presets_are_exact_and_ordered() -> None:
    assert config.MODEL_PRESETS == ("gpt-6-luna", "gpt-6-sol", "gpt-5.6-terra")


def test_selector_initially_focuses_current_value() -> None:
    console_output = Console(record=True, width=80)
    console_output.print(
        selector.render_selector("Select model", config.MODEL_PRESETS, 1, "gpt-6-sol")
    )
    output = console_output.export_text()
    assert "❯ gpt-6-sol  current" in output


@pytest.mark.parametrize(
    "start, keys, expected",
    [
        (1, [selector.key.DOWN, selector.key.ENTER], "gpt-5.6-terra"),
        (1, [selector.key.UP, selector.key.ENTER], "gpt-6-luna"),
        (0, [selector.key.UP, selector.key.ENTER], "gpt-5.6-terra"),
        (2, [selector.key.DOWN, selector.key.ENTER], "gpt-6-luna"),
    ],
)
def test_selector_navigation_and_wrap(
    monkeypatch: pytest.MonkeyPatch,
    start: int,
    keys: list[str],
    expected: str,
) -> None:
    monkeypatch.setattr(
        selector.sys, "stdin", type("TTY", (), {"isatty": lambda _: True})()
    )
    pressed = iter(keys)
    monkeypatch.setattr(selector, "readkey", lambda: next(pressed))
    console_output = Console(force_terminal=True, width=80)
    options = config.MODEL_PRESETS
    result = selector.select_option(
        title="Select model",
        options=options,
        current=options[start],
        console=console_output,
    )
    assert result == expected


@pytest.mark.parametrize("cancel_key", [selector.key.ESC, selector.key.CTRL_C])
def test_selector_cancellation(
    monkeypatch: pytest.MonkeyPatch, cancel_key: str
) -> None:
    monkeypatch.setattr(
        selector.sys, "stdin", type("TTY", (), {"isatty": lambda _: True})()
    )
    monkeypatch.setattr(selector, "readkey", lambda: cancel_key)
    console_output = Console(force_terminal=True, width=80)
    if cancel_key == selector.key.CTRL_C:
        with pytest.raises(KeyboardInterrupt):
            selector.select_option(
                title="Select model",
                options=config.MODEL_PRESETS,
                current="gpt-6-sol",
                console=console_output,
            )
    else:
        assert (
            selector.select_option(
                title="Select model",
                options=config.MODEL_PRESETS,
                current="gpt-6-sol",
                console=console_output,
            )
            is None
        )


def test_selector_restores_cursor_after_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        selector.sys, "stdin", type("TTY", (), {"isatty": lambda _: True})()
    )
    monkeypatch.setattr(selector, "readkey", lambda: selector.key.CTRL_C)
    console_output = Console(force_terminal=True, width=80)
    cursor_states: list[bool] = []
    monkeypatch.setattr(console_output, "show_cursor", cursor_states.append)
    with pytest.raises(KeyboardInterrupt):
        selector.select_option(
            title="Select model",
            options=config.MODEL_PRESETS,
            current="gpt-6-sol",
            console=console_output,
        )
    assert cursor_states[0] is False
    assert cursor_states[-1] is True


def test_model_selection_persists_only_model(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    selection: list[tuple[tuple[str, ...], str]] = []

    def select(*, options: tuple[str, ...], current: str, **_: object) -> str:
        selection.append((options, current))
        return "gpt-6-luna"

    monkeypatch.setattr(config_cli, "select_option", select)
    result = runner.invoke(config_cli.config_app, ["model"])
    loaded = config.load_config()
    assert result.exit_code == 0, result.output
    assert selection == [(config.MODEL_PRESETS, "gpt-6-sol")]
    assert loaded.openai.model == "gpt-6-luna"
    assert loaded.openai.reasoning == "medium"


def test_effort_selection_persists_only_effort(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    selection: list[tuple[tuple[str, ...], str]] = []

    def select(*, options: tuple[str, ...], current: str, **_: object) -> str:
        selection.append((options, current))
        return "high"

    monkeypatch.setattr(config_cli, "select_option", select)
    result = runner.invoke(config_cli.config_app, ["effort"])
    loaded = config.load_config()
    assert result.exit_code == 0, result.output
    assert selection == [(config.REASONING_EFFORTS, "medium")]
    assert loaded.openai.model == "gpt-6-sol"
    assert loaded.openai.reasoning == "high"


def test_cancelled_command_leaves_configuration_unchanged(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    before = config_path.read_text()
    monkeypatch.setattr(config_cli, "select_option", lambda **_: None)
    result = runner.invoke(config_cli.config_app, ["model"])
    assert result.exit_code == 0
    assert config_path.read_text() == before


def test_interrupted_command_leaves_configuration_unchanged(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    before = config_path.read_text()

    def interrupt(**_: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(config_cli, "select_option", interrupt)
    result = runner.invoke(config_cli.config_app, ["model"])
    assert result.exit_code != 0
    assert config_path.read_text() == before


def test_invalid_persisted_model_fails_without_opening_selector(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    config_path.write_text(
        'schema_version = 1\n[openai]\nmodel = "custom-model"\nreasoning = "medium"\n'
    )
    monkeypatch.setattr(
        config_cli, "select_option", lambda **_: pytest.fail("selector should not run")
    )
    result = runner.invoke(config_cli.config_app, ["model"])
    assert result.exit_code == 1
    assert "Invalid Bridger configuration" in result.output
    assert "openai.model" in result.output
