from rich.table import Table

from bridger.console import console
from bridger.paths import ProjectPaths
from bridger.project import read_project_config


def run() -> None:
    paths = ProjectPaths.from_cwd()
    config = read_project_config(paths.config_file)

    table = Table(title="Bridger project status")
    table.add_column("Item")
    table.add_column("Status")
    table.add_row(
        ".bridger directory", "present" if paths.bridger_dir.exists() else "missing"
    )
    table.add_row("config.json", "present" if paths.config_file.exists() else "missing")
    table.add_row("project mode", config.project_mode if config else "unknown")
    console.print(table)
