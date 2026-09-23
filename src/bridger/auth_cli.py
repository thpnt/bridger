"""Local OpenAI credential commands."""

import typer

from bridger.settings.config import BridgerConfigurationError, ensure_user_config
from bridger.settings.credentials import (
    BridgerCredentialError,
    CredentialSource,
    OpenAICredentialNotFoundError,
    environment_openai_api_key,
    get_stored_openai_api_key,
    remove_openai_api_key,
    resolve_openai_credential,
    set_openai_api_key,
)

app = typer.Typer(help="Manage the local OpenAI API key.")


@app.command("set-key")
def set_key() -> None:
    """Store an OpenAI API key in the system credential store."""
    try:
        if get_stored_openai_api_key() and not typer.confirm(
            "An OpenAI API key is already stored. Replace it?", default=False
        ):
            return
        value = typer.prompt("OpenAI API key", hide_input=True).strip()
        if not value:
            typer.echo("OpenAI API key must not be empty.", err=True)
            raise typer.Exit(code=1)
        ensure_user_config()
        set_openai_api_key(value)
    except (BridgerConfigurationError, BridgerCredentialError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo("OpenAI API key stored in the system credential store.")
    if environment_openai_api_key():
        typer.echo("OPENAI_API_KEY is currently set and takes precedence.")


@app.command("status")
def status() -> None:
    """Report the local credential source without contacting OpenAI."""
    try:
        credential = resolve_openai_credential()
    except OpenAICredentialNotFoundError:
        typer.echo(
            "OpenAI authentication: not configured\n\n"
            "Run:\n  bridger auth set-key\n\nor set OPENAI_API_KEY."
        )
        return
    except BridgerCredentialError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    source = (
        "OPENAI_API_KEY"
        if credential.source is CredentialSource.ENVIRONMENT
        else "system credential store"
    )
    typer.echo(f"OpenAI authentication: configured\nSource: {source}")


@app.command("remove")
def remove() -> None:
    """Remove only the Bridger-managed keyring credential."""
    try:
        removed = remove_openai_api_key()
    except BridgerCredentialError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        "Stored OpenAI API key removed."
        if removed
        else "No stored OpenAI API key found."
    )
    if environment_openai_api_key():
        typer.echo("OPENAI_API_KEY is still set and remains active.")
