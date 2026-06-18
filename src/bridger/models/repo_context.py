from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import JsonValue, field_validator

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)


class ManifestKind(StrEnum):
    PYTHON_PYPROJECT = "python_pyproject"
    PYTHON_REQUIREMENTS = "python_requirements"
    UV_LOCK = "uv_lock"
    POETRY_LOCK = "poetry_lock"
    NODE_PACKAGE_JSON = "node_package_json"
    NPM_LOCK = "npm_lock"
    PNPM_LOCK = "pnpm_lock"
    YARN_LOCK = "yarn_lock"
    GO_MOD = "go_mod"
    GO_SUM = "go_sum"
    GO_MAIN = "go_main"
    PHP_COMPOSER = "php_composer"
    COMPOSER_LOCK = "composer_lock"
    SYMFONY_LOCK = "symfony_lock"
    PHP_ARTISAN = "php_artisan"


class ConfigKind(StrEnum):
    PYTHON_SETUP = "python_setup"
    PYTHON_TOOL_CONFIG = "python_tool_config"
    DOCKER_CONFIG = "docker_config"
    NODE_WORKSPACE = "node_workspace"
    TYPESCRIPT_CONFIG = "typescript_config"
    JAVASCRIPT_CONFIG = "javascript_config"
    VITE_CONFIG = "vite_config"
    NEXT_CONFIG = "next_config"
    NUXT_CONFIG = "nuxt_config"
    SVELTE_CONFIG = "svelte_config"
    ESLINT_CONFIG = "eslint_config"
    JEST_CONFIG = "jest_config"
    VITEST_CONFIG = "vitest_config"
    PLAYWRIGHT_CONFIG = "playwright_config"
    TURBO_CONFIG = "turbo_config"
    GO_MAKEFILE = "go_makefile"
    PHPUNIT_CONFIG = "phpunit_config"
    PHP_ENV_EXAMPLE = "php_env_example"


class CiKind(StrEnum):
    GITHUB_ACTIONS_WORKFLOW = "github_actions_workflow"
    GITLAB_CI = "gitlab_ci"
    CIRCLE_CI = "circle_ci"


class InstructionKind(StrEnum):
    AGENT_INSTRUCTIONS = "agent_instructions"
    CLAUDE_INSTRUCTIONS = "claude_instructions"
    CURSOR_RULE = "cursor_rule"


class DocsKind(StrEnum):
    README = "readme"
    CONTRIBUTING = "contributing"
    CHANGELOG = "changelog"
    DOCUMENTATION = "documentation"
    ARCHITECTURE_DECISION_RECORD = "architecture_decision_record"


class ManifestFile(ArtifactModel):
    path: RepositoryPath
    kind: ManifestKind
    parsed: dict[str, JsonValue]

    _validate_path = field_validator("path")(validate_repository_path)


class ConfigFile(ArtifactModel):
    path: RepositoryPath
    kind: ConfigKind

    _validate_path = field_validator("path")(validate_repository_path)


class CiFile(ArtifactModel):
    path: RepositoryPath
    kind: CiKind

    _validate_path = field_validator("path")(validate_repository_path)


class InstructionFile(ArtifactModel):
    path: RepositoryPath
    kind: InstructionKind

    _validate_path = field_validator("path")(validate_repository_path)


class DocsFile(ArtifactModel):
    path: RepositoryPath
    kind: DocsKind

    _validate_path = field_validator("path")(validate_repository_path)


class ManifestParseError(ArtifactModel):
    path: RepositoryPath
    error: str

    _validate_path = field_validator("path")(validate_repository_path)


class RepoContextArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    manifests: list[ManifestFile]
    config_files: list[ConfigFile]
    ci_files: list[CiFile]
    instruction_files: list[InstructionFile]
    docs_files: list[DocsFile]
    parse_errors: list[ManifestParseError]
