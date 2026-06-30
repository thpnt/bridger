import typer

from bridger.commands import init as init_command
from bridger.commands import inspect as inspect_command
from bridger.commands import prompt as prompt_command
from bridger.commands import update as update_command

app = typer.Typer(help="Compile repository context for AI coding agents.")


@app.command("init")
def init(
    fresh: bool = typer.Option(False, "--fresh", help="Use fresh project mode."),
    verbose: bool = typer.Option(False, "--verbose", help="Show artifact paths."),
) -> None:
    """Initialize Bridger project context files."""
    init_command.run(fresh, verbose)


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
