import json
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.markdown import Markdown
from rich.text import Text

from bridger.auth_cli import app as auth_app
from bridger.cli_console import console, error_console
from bridger.cli_progress import RichInitProgressPresenter
from bridger.config_cli import config_app
from bridger.contracts.consumption import ImpactResult, UnderstandResult
from bridger.init_pipeline import (
    InitMode,
    ReasoningEffort,
    RepositoryBrainBuildError,
    build_repository_brain,
    resolve_init_configuration,
)
from bridger.navigation.bootstrap import load_bridger_navigator
from bridger.presentation import render_intelligence_json, render_intelligence_markdown
from bridger.settings.config import BridgerConfigurationError, load_config
from bridger.settings.credentials import (
    BridgerCredentialError,
    resolve_openai_credential,
)

app = typer.Typer(
    help="Build and query evidence-backed repository knowledge.",
    rich_markup_mode="rich",
)
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")


@app.command("init")
def init(
    mode: Annotated[
        InitMode,
        typer.Option(
            "--mode",
            help=(
                "Execution mode: full builds the complete Brain; deterministic "
                "stops before model stages; test runs the full pipeline with "
                "reduced budgets."
            ),
            rich_help_panel="Execution",
        ),
    ] = InitMode.FULL,
    reasoning: Annotated[
        ReasoningEffort | None,
        typer.Option(
            "--reasoning",
            help="Memory-agent reasoning effort.",
            rich_help_panel="Execution",
        ),
    ] = None,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Ignore compatible persisted state and run a new pipeline.",
            rich_help_panel="Execution",
        ),
    ] = False,
) -> None:
    """Build the Repository Brain for the current Git repository."""
    try:
        user_config = load_config()
        resolved_reasoning = reasoning or ReasoningEffort(user_config.openai.reasoning)
        if mode is not InitMode.DETERMINISTIC:
            resolve_openai_credential()
    except (BridgerConfigurationError, BridgerCredentialError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    configuration = resolve_init_configuration(
        mode,
        reasoning_effort=resolved_reasoning,
        fresh=fresh,
        openai_model=user_config.openai.model,
    )
    presenter = RichInitProgressPresenter(
        console=console,
        mode=mode,
        reasoning=resolved_reasoning,
    )
    _present(presenter.start)
    try:
        result = build_repository_brain(
            configuration,
            progress=presenter,
        )
    except RepositoryBrainBuildError as error:
        _present(partial(presenter.failed, error))
        raise typer.Exit(code=1) from error
    except Exception as error:
        _present(partial(presenter.failed, error))
        raise typer.Exit(code=1) from error
    else:
        _present(lambda: presenter.succeeded(result))
    finally:
        _present(presenter.close)


@app.command()
def understand(
    query: Annotated[
        str,
        typer.Argument(help="Repository question to understand."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output the canonical result as JSON."),
    ] = False,
) -> None:
    """Retrieve repository knowledge and structural context."""
    try:
        with load_bridger_navigator(Path.cwd()) as navigator:
            result = navigator.understand(query)
        _print_consumption_result(result, json_output=json_output)
    except Exception as error:
        _fail_consumption(error)


@app.command()
def impact(
    symbols: Annotated[
        list[str],
        typer.Argument(help="Exact repository symbols to analyze."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output the canonical result as JSON."),
    ] = False,
) -> None:
    """Analyze potential structural impact for exact repository symbols."""
    try:
        with load_bridger_navigator(Path.cwd()) as navigator:
            result = navigator.impact(symbols)
        _print_consumption_result(result, json_output=json_output)
    except Exception as error:
        _fail_consumption(error)


def _print_consumption_result(
    result: UnderstandResult | ImpactResult,
    *,
    json_output: bool,
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                render_intelligence_json(result),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    rendered = render_intelligence_markdown(result)
    if console.is_terminal:
        console.print(Markdown(rendered))
    else:
        typer.echo(rendered, nl=False)


def _fail_consumption(error: Exception) -> NoReturn:
    message = str(error) or type(error).__name__
    if error_console.is_terminal:
        error_console.print(Text(f"Error: {message}", style="bold red"))
    else:
        typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1) from error


def _present(action: Callable[[], None]) -> None:
    """Keep best-effort presentation failures outside command authority."""
    try:
        action()
    except Exception:
        pass


@app.command("mcp")
def mcp_command(
    repository: Annotated[
        Path | None,
        typer.Option("--repository", help="Repository location (defaults to cwd)."),
    ] = None,
) -> None:
    """Serve the current repository to coding agents over MCP stdio."""
    from bridger.mcp_server import run_mcp_server

    run_mcp_server(repository or Path.cwd())


@app.command()
def update() -> None:
    """Reserved for repository updates."""
    pass


@app.command()
def prompt(task: str = typer.Argument(..., help="Coding task to include.")) -> None:
    """Reserved for prompt generation."""
    pass


@app.command("inspect")
def inspect_project() -> None:
    """Reserved for repository inspection."""
    pass


if __name__ == "__main__":
    app()
