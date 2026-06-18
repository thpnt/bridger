from fnmatch import fnmatch
from pathlib import PurePosixPath

from bridger.models.repo_context import (
    CiKind,
    ConfigKind,
    DocsKind,
    InstructionKind,
    ManifestKind,
)

DetectedKind = ManifestKind | ConfigKind | CiKind | InstructionKind | DocsKind

MANIFEST_NAMES: dict[str, ManifestKind] = {
    "pyproject.toml": ManifestKind.PYTHON_PYPROJECT,
    "uv.lock": ManifestKind.UV_LOCK,
    "poetry.lock": ManifestKind.POETRY_LOCK,
    "requirements.txt": ManifestKind.PYTHON_REQUIREMENTS,
    "requirements-dev.txt": ManifestKind.PYTHON_REQUIREMENTS,
    "package.json": ManifestKind.NODE_PACKAGE_JSON,
    "package-lock.json": ManifestKind.NPM_LOCK,
    "pnpm-lock.yaml": ManifestKind.PNPM_LOCK,
    "yarn.lock": ManifestKind.YARN_LOCK,
    "go.mod": ManifestKind.GO_MOD,
    "go.sum": ManifestKind.GO_SUM,
    "composer.json": ManifestKind.PHP_COMPOSER,
    "composer.lock": ManifestKind.COMPOSER_LOCK,
    "symfony.lock": ManifestKind.SYMFONY_LOCK,
    "artisan": ManifestKind.PHP_ARTISAN,
}

CONFIG_NAMES: dict[str, ConfigKind] = {
    "setup.py": ConfigKind.PYTHON_SETUP,
    "setup.cfg": ConfigKind.PYTHON_SETUP,
    "tox.ini": ConfigKind.PYTHON_TOOL_CONFIG,
    "pytest.ini": ConfigKind.PYTHON_TOOL_CONFIG,
    "mypy.ini": ConfigKind.PYTHON_TOOL_CONFIG,
    "ruff.toml": ConfigKind.PYTHON_TOOL_CONFIG,
    "Dockerfile": ConfigKind.DOCKER_CONFIG,
    "docker-compose.yml": ConfigKind.DOCKER_CONFIG,
    "pnpm-workspace.yaml": ConfigKind.NODE_WORKSPACE,
    "tsconfig.json": ConfigKind.TYPESCRIPT_CONFIG,
    "jsconfig.json": ConfigKind.JAVASCRIPT_CONFIG,
    "turbo.json": ConfigKind.TURBO_CONFIG,
    "Makefile": ConfigKind.GO_MAKEFILE,
    "phpunit.xml": ConfigKind.PHPUNIT_CONFIG,
    ".env.example": ConfigKind.PHP_ENV_EXAMPLE,
}

DYNAMIC_CONFIG_PATTERNS: tuple[tuple[str, ConfigKind], ...] = (
    ("vite.config.*", ConfigKind.VITE_CONFIG),
    ("next.config.*", ConfigKind.NEXT_CONFIG),
    ("nuxt.config.*", ConfigKind.NUXT_CONFIG),
    ("svelte.config.*", ConfigKind.SVELTE_CONFIG),
    ("eslint.config.*", ConfigKind.ESLINT_CONFIG),
    ("jest.config.*", ConfigKind.JEST_CONFIG),
    ("vitest.config.*", ConfigKind.VITEST_CONFIG),
    ("playwright.config.*", ConfigKind.PLAYWRIGHT_CONFIG),
)


def detect_file_kind(path: str) -> DetectedKind | None:
    parsed_path = PurePosixPath(path)
    parts = parsed_path.parts

    if len(parts) >= 3 and parts[:2] == (".github", "workflows"):
        return CiKind.GITHUB_ACTIONS_WORKFLOW
    if path == ".gitlab-ci.yml":
        return CiKind.GITLAB_CI
    if path in {"circle.yml", ".circleci/config.yml"}:
        return CiKind.CIRCLE_CI

    if parsed_path.name == "AGENTS.md":
        return InstructionKind.AGENT_INSTRUCTIONS
    if parsed_path.name == "CLAUDE.md":
        return InstructionKind.CLAUDE_INSTRUCTIONS
    if len(parts) >= 3 and parts[:2] == (".cursor", "rules"):
        return InstructionKind.CURSOR_RULE

    if parsed_path.name == "README.md":
        return DocsKind.README
    if parsed_path.name == "CONTRIBUTING.md":
        return DocsKind.CONTRIBUTING
    if parsed_path.name == "CHANGELOG.md":
        return DocsKind.CHANGELOG
    if parts and parts[0] == "docs":
        return DocsKind.DOCUMENTATION
    if parts and parts[0] == "adr":
        return DocsKind.ARCHITECTURE_DECISION_RECORD

    if len(parts) == 3 and parts[0] == "cmd" and parts[2] == "main.go":
        return ManifestKind.GO_MAIN
    if parsed_path.name in MANIFEST_NAMES:
        return MANIFEST_NAMES[parsed_path.name]
    if parsed_path.name in CONFIG_NAMES:
        return CONFIG_NAMES[parsed_path.name]
    for pattern, kind in DYNAMIC_CONFIG_PATTERNS:
        if fnmatch(parsed_path.name, pattern):
            return kind
    return None
