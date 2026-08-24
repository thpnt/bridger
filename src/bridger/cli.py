from collections.abc import Callable
from functools import partial
from typing import Annotated

import typer
from rich.console import Console

from bridger.cli_progress import RichInitProgressPresenter
from bridger.init_pipeline import (
    InitMode,
    ReasoningEffort,
    RepositoryBrainBuildError,
    build_repository_brain,
    resolve_init_configuration,
)

app = typer.Typer(
    help="Build evidence-backed Repository Brains from Git repositories.",
    rich_markup_mode="rich",
)
console = Console()


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
        ReasoningEffort,
        typer.Option(
            "--reasoning",
            help="Memory-agent reasoning effort.",
            rich_help_panel="Execution",
        ),
    ] = ReasoningEffort.XHIGH,
) -> None:
    """Build the Repository Brain for the current Git repository."""
    configuration = resolve_init_configuration(mode, reasoning_effort=reasoning)
    presenter = RichInitProgressPresenter(
        console=console,
        mode=mode,
        reasoning=reasoning,
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


def _present(action: Callable[[], None]) -> None:
    """Keep best-effort presentation failures outside command authority."""
    try:
        action()
    except Exception:
        pass


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
