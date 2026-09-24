"""Shared Rich console used by Bridger CLI commands."""

from rich.console import Console

console = Console()
error_console = Console(stderr=True)
