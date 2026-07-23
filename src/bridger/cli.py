from pathlib import Path

import typer
from dotenv import load_dotenv

from bridger.commands import init as init_command
from bridger.commands import inspect as inspect_command
from bridger.commands import prompt as prompt_command
from bridger.commands import update as update_command

BRIDGER_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BRIDGER_ROOT / ".env")

app = typer.Typer(help="Compile repository context for AI coding agents.")


@app.command("init")
def init(
    fresh: bool = typer.Option(False, "--fresh", help="Use fresh project mode."),
    verbose: bool = typer.Option(False, "--verbose", help="Show run details."),
    llm_profile: str | None = typer.Option(
        None,
        "--llm-profile",
        help="Use a configured LLM profile for Context Plan generation.",
    ),
) -> None:
    """Initialize Bridger project context files."""
    raise typer.Exit(init_command.run(fresh, verbose, llm_profile))


@app.command()
def update() -> None:
    """Update Bridger project context files."""
    update_command.run()


@app.command()
def prompt(task: str = typer.Argument(..., help="Coding task to include.")) -> None:
    """Generate a coding-agent prompt for a task."""
    prompt_command.run(task)


@app.command("inspect")
def inspect_project(
    graph: bool = typer.Option(False, "--graph", help="Show graph status."),
) -> None:
    """Inspect Bridger project status."""
    inspect_command.run(graph)


if __name__ == "__main__":
    app()
