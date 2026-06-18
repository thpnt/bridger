from bridger.console import console
from bridger.paths import ProjectPaths
from bridger.project import initialize_project


def run(fresh: bool) -> None:
    paths = ProjectPaths.from_cwd()
    already_exists, _ = initialize_project(paths, fresh)

    if already_exists:
        console.print(
            "[green]Bridger project is ready.[/green] Existing files preserved."
        )
    else:
        console.print("[green]Bridger project initialized.[/green]")

    if fresh:
        console.print("Fresh mode is currently a placeholder.")
