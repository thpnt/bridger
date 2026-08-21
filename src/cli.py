from typing import Annotated

import typer
from rich.console import Console

from init_pipeline import (
    InitMode,
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
) -> None:
    """Build the Repository Brain for the current Git repository."""
    configuration = resolve_init_configuration(mode)
    console.print(f"[cyan]Bridger[/cyan] building Repository Brain ({mode.value})")
    try:
        result = build_repository_brain(
            configuration,
            on_stage=lambda stage: console.print(
                f"[cyan]:hourglass_flowing_sand:[/cyan] {stage}"
            ),
        )
    except RepositoryBrainBuildError as error:
        console.print(f"[red]:x:[/red] Repository Brain build failed: {error}")
        raise typer.Exit(code=1) from error
    except Exception as error:
        console.print(f"[red]:x:[/red] Repository Brain build failed: {error}")
        raise typer.Exit(code=1) from error

    if result.publication_path is None:
        console.print(
            "[green]:white_check_mark:[/green] "
            "Deterministic graph snapshot published at "
            f"{result.graph_build.snapshot_root}"
        )
        return
    console.print(
        "[green]:white_check_mark:[/green] Repository Brain published at "
        f"{result.publication_path}"
    )


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
