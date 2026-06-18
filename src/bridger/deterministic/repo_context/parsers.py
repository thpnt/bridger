import shlex
import tomllib
from collections.abc import Callable

import orjson
from pydantic import JsonValue, TypeAdapter

from bridger.models.repo_context import ManifestKind

ParsedManifest = dict[str, JsonValue]
ManifestParser = Callable[[bytes], ParsedManifest]
JSON_VALUE_ADAPTER = TypeAdapter(dict[str, JsonValue])


class ManifestParseFailure(ValueError):
    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


def _selected_values(
    source: dict[str, object], names: tuple[str, ...]
) -> dict[str, object]:
    return {name: source[name] for name in names if name in source}


def parse_pyproject(content: bytes) -> ParsedManifest:
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ManifestParseFailure("invalid_toml") from error

    parsed: dict[str, object] = {}
    project = document.get("project")
    if isinstance(project, dict):
        project_values = _selected_values(
            project,
            ("dependencies", "optional-dependencies", "scripts", "entry-points"),
        )
        if "name" in project:
            parsed["project_name"] = project["name"]
        parsed.update(
            {key.replace("-", "_"): value for key, value in project_values.items()}
        )

    dependency_groups = document.get("dependency-groups")
    if dependency_groups is not None:
        parsed["dependency_groups"] = dependency_groups

    tool = document.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    if isinstance(poetry, dict):
        if "project_name" not in parsed and "name" in poetry:
            parsed["project_name"] = poetry["name"]
        if "dependencies" in poetry:
            parsed["poetry_dependencies"] = poetry["dependencies"]
        if "dev-dependencies" in poetry:
            parsed["poetry_dev_dependencies"] = poetry["dev-dependencies"]
        groups = poetry.get("group")
        if isinstance(groups, dict):
            group_dependencies = {
                name: group["dependencies"]
                for name, group in groups.items()
                if isinstance(group, dict) and "dependencies" in group
            }
            if group_dependencies:
                parsed["poetry_group_dependencies"] = group_dependencies

    try:
        return JSON_VALUE_ADAPTER.validate_python(parsed)
    except ValueError as error:
        raise ManifestParseFailure("invalid_toml_data") from error


def _parse_json_manifest(content: bytes, fields: dict[str, str]) -> ParsedManifest:
    try:
        document = orjson.loads(content)
    except orjson.JSONDecodeError as error:
        raise ManifestParseFailure("invalid_json") from error
    if not isinstance(document, dict):
        raise ManifestParseFailure("invalid_json")
    selected = {
        output_name: document[source_name]
        for output_name, source_name in fields.items()
        if source_name in document
    }
    return JSON_VALUE_ADAPTER.validate_python(selected)


def parse_package_json(content: bytes) -> ParsedManifest:
    return _parse_json_manifest(
        content,
        {
            "name": "name",
            "version": "version",
            "scripts": "scripts",
            "dependencies": "dependencies",
            "dev_dependencies": "devDependencies",
            "peer_dependencies": "peerDependencies",
            "optional_dependencies": "optionalDependencies",
            "bin": "bin",
            "workspaces": "workspaces",
        },
    )


def parse_composer_json(content: bytes) -> ParsedManifest:
    return _parse_json_manifest(
        content,
        {
            "name": "name",
            "type": "type",
            "require": "require",
            "require_dev": "require-dev",
            "autoload": "autoload",
            "autoload_dev": "autoload-dev",
            "scripts": "scripts",
            "bin": "bin",
        },
    )


def _go_tokens(line: str) -> list[str]:
    try:
        return shlex.split(line.split(" //", maxsplit=1)[0])
    except ValueError as error:
        raise ManifestParseFailure("invalid_go_mod") from error


def _go_requirement(tokens: list[str]) -> dict[str, JsonValue]:
    if len(tokens) != 2:
        raise ManifestParseFailure("invalid_go_mod")
    return {"module": tokens[0], "version": tokens[1]}


def _go_replacement(tokens: list[str]) -> dict[str, JsonValue]:
    if "=>" not in tokens:
        raise ManifestParseFailure("invalid_go_mod")
    separator = tokens.index("=>")
    old, new = tokens[:separator], tokens[separator + 1 :]
    if len(old) not in {1, 2} or len(new) not in {1, 2}:
        raise ManifestParseFailure("invalid_go_mod")
    replacement: dict[str, JsonValue] = {"old": old[0], "new": new[0]}
    if len(old) == 2:
        replacement["old_version"] = old[1]
    if len(new) == 2:
        replacement["new_version"] = new[1]
    return replacement


def parse_go_mod(content: bytes) -> ParsedManifest:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ManifestParseFailure("invalid_go_mod") from error

    parsed: ParsedManifest = {}
    requirements: list[JsonValue] = []
    replacements: list[JsonValue] = []
    section: str | None = None
    for raw_line in lines:
        tokens = _go_tokens(raw_line.strip())
        if not tokens:
            continue
        if tokens == [")"]:
            if section is None:
                raise ManifestParseFailure("invalid_go_mod")
            section = None
            continue
        if tokens in (["require", "("], ["replace", "("]):
            if section is not None:
                raise ManifestParseFailure("invalid_go_mod")
            section = tokens[0]
            continue
        if section == "require":
            requirements.append(_go_requirement(tokens))
        elif section == "replace":
            replacements.append(_go_replacement(tokens))
        elif tokens[0] == "module" and len(tokens) == 2:
            parsed["module_name"] = tokens[1]
        elif tokens[0] == "go" and len(tokens) == 2:
            parsed["go_version"] = tokens[1]
        elif tokens[0] == "require":
            requirements.append(_go_requirement(tokens[1:]))
        elif tokens[0] == "replace":
            replacements.append(_go_replacement(tokens[1:]))

    if section is not None:
        raise ManifestParseFailure("invalid_go_mod")
    if requirements:
        parsed["requirements"] = requirements
    if replacements:
        parsed["replacements"] = replacements
    return parsed


PARSERS: dict[ManifestKind, ManifestParser] = {
    ManifestKind.PYTHON_PYPROJECT: parse_pyproject,
    ManifestKind.NODE_PACKAGE_JSON: parse_package_json,
    ManifestKind.PHP_COMPOSER: parse_composer_json,
    ManifestKind.GO_MOD: parse_go_mod,
}


def parse_manifest(kind: ManifestKind, content: bytes) -> ParsedManifest:
    parser = PARSERS.get(kind)
    return parser(content) if parser is not None else {}
