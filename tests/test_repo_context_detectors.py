import pytest

from bridger.deterministic.repo_context.detectors import detect_file_kind
from bridger.models.repo_context import (
    CiKind,
    ConfigKind,
    DocsKind,
    InstructionKind,
    ManifestKind,
)


@pytest.mark.parametrize(
    ("path", "expected_kind"),
    [
        ("pyproject.toml", ManifestKind.PYTHON_PYPROJECT),
        ("package.json", ManifestKind.NODE_PACKAGE_JSON),
        ("composer.json", ManifestKind.PHP_COMPOSER),
        ("go.mod", ManifestKind.GO_MOD),
        ("tsconfig.json", ConfigKind.TYPESCRIPT_CONFIG),
        ("next.config.ts", ConfigKind.NEXT_CONFIG),
        ("vite.config.ts", ConfigKind.VITE_CONFIG),
        ("phpunit.xml", ConfigKind.PHPUNIT_CONFIG),
        ("cmd/api/main.go", ManifestKind.GO_MAIN),
        ("README.md", DocsKind.README),
        ("AGENTS.md", InstructionKind.AGENT_INSTRUCTIONS),
        (".github/workflows/test.yml", CiKind.GITHUB_ACTIONS_WORKFLOW),
    ],
)
def test_detect_file_kind(path: str, expected_kind: object) -> None:
    assert detect_file_kind(path) == expected_kind
