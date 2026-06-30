from bridger.deterministic.repo_context.parsers import (
    parse_composer_json,
    parse_go_mod,
    parse_package_json,
    parse_pyproject,
)


def test_parse_pyproject_extracts_explicit_project_facts() -> None:
    parsed = parse_pyproject(
        b"""
[project]
name = "example"
dependencies = ["typer>=0.15"]

[project.scripts]
example = "example.cli:app"
"""
    )

    assert parsed["project_name"] == "example"
    assert parsed["dependencies"] == ["typer>=0.15"]
    assert parsed["scripts"] == {"example": "example.cli:app"}


def test_parse_package_json_extracts_explicit_package_facts() -> None:
    parsed = parse_package_json(
        b"""
        {
          "name": "example",
          "scripts": {"test": "vitest"},
          "dependencies": {"next": "15.0.0"},
          "devDependencies": {"vitest": "3.0.0"},
          "bin": {"example": "bin/example.js"}
        }
        """
    )

    assert parsed["scripts"] == {"test": "vitest"}
    assert parsed["dependencies"] == {"next": "15.0.0"}
    assert parsed["dev_dependencies"] == {"vitest": "3.0.0"}
    assert parsed["bin"] == {"example": "bin/example.js"}


def test_parse_composer_json_extracts_explicit_package_facts() -> None:
    parsed = parse_composer_json(
        b"""
        {
          "require": {"php": "^8.3"},
          "require-dev": {"phpunit/phpunit": "^11"},
          "autoload": {"psr-4": {"App\\\\": "src/"}},
          "scripts": {"test": "phpunit"}
        }
        """
    )

    assert parsed["require"] == {"php": "^8.3"}
    assert parsed["require_dev"] == {"phpunit/phpunit": "^11"}
    assert parsed["autoload"] == {"psr-4": {"App\\": "src/"}}
    assert parsed["scripts"] == {"test": "phpunit"}


def test_parse_go_mod_extracts_explicit_module_facts() -> None:
    parsed = parse_go_mod(
        b"""
module example.com/service

go 1.23

require (
    github.com/example/library v1.2.3
)
"""
    )

    assert parsed["module_name"] == "example.com/service"
    assert parsed["go_version"] == "1.23"
    assert parsed["requirements"] == [
        {"module": "github.com/example/library", "version": "v1.2.3"}
    ]
