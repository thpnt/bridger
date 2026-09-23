"""Non-secret user configuration."""

import tomllib
from pathlib import Path
from typing import Literal, get_args

import platformdirs
from pydantic import BaseModel, ConfigDict, ValidationError

_BUNDLED_CONFIG_PATH = Path(__file__).with_name("config.toml")
ModelPreset = Literal["gpt-6-luna", "gpt-6-sol", "gpt-5.6-terra"]
ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]
MODEL_PRESETS = get_args(ModelPreset)
REASONING_EFFORTS = get_args(ReasoningEffort)


class BridgerConfigurationError(RuntimeError):
    """User configuration could not be loaded."""


class OpenAIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelPreset
    reasoning: ReasoningEffort


class BridgerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    openai: OpenAIConfig


def get_config_path() -> Path:
    return platformdirs.user_config_path("bridger") / "config.toml"


def load_config() -> BridgerConfig:
    defaults = _parse_config(_BUNDLED_CONFIG_PATH)
    path = get_config_path()
    try:
        values = _read_toml(path)
    except FileNotFoundError:
        return defaults

    openai = values.get("openai")
    if openai is None:
        values["openai"] = defaults.openai.model_dump()
    elif isinstance(openai, dict):
        values["openai"] = {**defaults.openai.model_dump(), **openai}
    return _validate_config(values, path)


def ensure_user_config() -> Path:
    """Create the editable user config from the bundled file if absent."""
    load_config()
    path = get_config_path()
    if path.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(_BUNDLED_CONFIG_PATH.read_bytes())
    except FileExistsError:
        load_config()
    except OSError as error:
        raise BridgerConfigurationError(
            f"Could not create Bridger configuration: {path}\n{error}"
        ) from error
    return path


def update_openai_setting(
    setting: Literal["model", "reasoning"], value: str
) -> BridgerConfig:
    """Update one validated OpenAI setting and persist the full config."""
    config = load_config()
    updated_openai = config.openai.model_copy(update={setting: value})
    updated = config.model_copy(update={"openai": updated_openai})
    # model_copy does not validate updates, so validate before writing.
    path = get_config_path()
    updated = _validate_config(updated.model_dump(), path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "schema_version = 1\n\n"
            "[openai]\n"
            f'model = "{updated.openai.model}"\n'
            f'reasoning = "{updated.openai.reasoning}"\n'
        )
    except OSError as error:
        raise BridgerConfigurationError(
            f"Could not write Bridger configuration: {path}\n{error}"
        ) from error
    return updated


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as source:
            return tomllib.load(source)
    except FileNotFoundError:
        raise
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise BridgerConfigurationError(
            f"Invalid Bridger configuration: {path}\n{error}"
        ) from error


def _parse_config(path: Path) -> BridgerConfig:
    return _validate_config(_read_toml(path), path)


def _validate_config(values: dict[str, object], path: Path) -> BridgerConfig:
    try:
        return BridgerConfig.model_validate(values)
    except ValidationError as error:
        issue = error.errors()[0]
        location = ".".join(str(part) for part in issue["loc"])
        raise BridgerConfigurationError(
            f"Invalid Bridger configuration: {path}\n{location}: {issue['msg']}"
        ) from error
