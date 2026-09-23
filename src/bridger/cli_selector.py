"""Small inline single-choice selector for interactive CLI commands."""

import sys
from collections.abc import Sequence

from readchar import key, readkey
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.text import Text


def render_selector(
    title: str,
    options: Sequence[str],
    selected_index: int,
    current_value: str,
) -> RenderableType:
    rows: list[Text] = [Text(title, style="bold")]
    rows.append(Text())
    for index, option in enumerate(options):
        focused = index == selected_index
        row = Text("❯ " if focused else "  ")
        row.append(option, style="bold cyan" if focused else "")
        if option == current_value:
            row.append("  current", style="dim")
        rows.append(row)
    rows.extend((Text(), Text("↑/↓ navigate   Enter select   Esc cancel", style="dim")))
    return Group(*rows)


def select_option(
    *,
    title: str,
    options: Sequence[str],
    current: str,
    console: Console,
) -> str | None:
    """Return the selected option, or None when the user cancels."""
    if not console.is_terminal or not sys.stdin.isatty():
        raise RuntimeError("Interactive selection requires a terminal.")
    if not options or current not in options:
        raise ValueError("The current value must be one of the selector options.")

    selected = options.index(current)
    with Live(
        render_selector(title, options, selected, current),
        console=console,
        auto_refresh=False,
        transient=True,
    ) as live:
        while True:
            pressed = readkey()
            if pressed == key.UP:
                selected = (selected - 1) % len(options)
            elif pressed == key.DOWN:
                selected = (selected + 1) % len(options)
            elif pressed == key.ENTER:
                return options[selected]
            elif pressed == key.ESC:
                return None
            elif pressed == key.CTRL_C:
                raise KeyboardInterrupt
            else:
                continue
            live.update(
                render_selector(title, options, selected, current), refresh=True
            )
