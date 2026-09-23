"""Interactive editors for the existing user configuration."""

from typing import Literal

import typer
from rich.text import Text

from bridger.cli_console import console
from bridger.cli_selector import select_option
from bridger.settings.config import (
    MODEL_PRESETS,
    REASONING_EFFORTS,
    BridgerConfigurationError,
    load_config,
    update_openai_setting,
)

config_app = typer.Typer(help="Edit Bridger configuration.", rich_markup_mode="rich")


@config_app.command("model")
def model() -> None:
    """Choose the OpenAI model used by Bridger."""
    _edit_setting(
        setting="model",
        title="Select model",
        options=MODEL_PRESETS,
        setting_key="model",
        label="Model",
    )


@config_app.command("effort")
def effort() -> None:
    """Choose the OpenAI reasoning effort used by Bridger."""
    _edit_setting(
        setting="reasoning",
        title="Select reasoning effort",
        options=REASONING_EFFORTS,
        setting_key="reasoning",
        label="Reasoning effort",
    )


def _edit_setting(
    *,
    setting: Literal["model", "reasoning"],
    title: str,
    options: tuple[str, ...],
    setting_key: Literal["model", "reasoning"],
    label: str,
) -> None:
    try:
        current = getattr(load_config().openai, setting_key)
        selected = select_option(
            title=title,
            options=options,
            current=current,
            console=console,
        )
        if selected is None:
            return
        update_openai_setting(setting, selected)
    except (BridgerConfigurationError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    console.print(Text(f"✓ {label} set to {selected}", style="bold green"))
