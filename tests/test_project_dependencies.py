from pathlib import Path
from tomllib import loads

import pytest

from bridger.deterministic.symbols import registry


def test_tree_sitter_stays_compatible_with_language_bindings() -> None:
    project_root = Path(__file__).parent.parent
    configuration = loads((project_root / "pyproject.toml").read_text())

    assert "tree-sitter>=0.25.2,<0.26" in configuration["project"]["dependencies"]


def test_incompatible_tree_sitter_fails_before_parser_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry.metadata, "version", lambda _: "0.26.0")

    with pytest.raises(
        registry.TreeSitterCompatibilityError,
        match="Tree-sitter 0.26.0 is incompatible",
    ):
        registry.build_extractor_registry()
