from rich.panel import Panel

from bridger.console import console


def run(task: str) -> None:
    prompt = (
        "Work on the following task in the current repository:\n\n"
        f"{task}\n\n"
        "Follow the repository instructions and verify the resulting changes."
    )
    console.print(Panel(prompt, title="Bridger prompt"))
