from types import SimpleNamespace

from bridger.cli_output import InitRunSummary, render_init_summary
from bridger.console import console


def test_render_init_summary_hides_zero_value_noise() -> None:
    summary = make_summary()

    with console.capture() as capture:
        render_init_summary(summary, verbose=False)

    output = capture.get()

    assert "Repository substrate ready" in output
    assert "Deterministic substrate" in output
    assert "0 parse errors" not in output
    assert "0 unresolved imports" not in output
    assert "Warnings" not in output
    assert "file-index.json" not in output


def test_render_init_summary_shows_warnings() -> None:
    summary = make_summary(symbol_parse_errors=2, unresolved_imports=12)

    with console.capture() as capture:
        render_init_summary(summary, verbose=False)

    output = capture.get()

    assert "Repository substrate ready with warnings" in output
    assert "2 parse errors" in output
    assert "12 unresolved imports" in output
    assert "Warnings" in output
    assert "2 files could not be parsed" in output
    assert "12 local imports could not be resolved" in output


def test_render_init_summary_verbose_shows_artifact_paths() -> None:
    summary = make_summary()

    with console.capture() as capture:
        render_init_summary(summary, verbose=True)

    output = capture.get()

    assert "Artifacts" in output
    assert ".bridger/artifacts/file-index.json" in output
    assert ".bridger/artifacts/repo-discovery.json" in output


def make_summary(
    *, symbol_parse_errors: int = 0, unresolved_imports: int = 0
) -> InitRunSummary:
    return InitRunSummary(
        file_index=SimpleNamespace(
            stats=SimpleNamespace(files_included=227, files_skipped=9244)
        ),
        repo_context=SimpleNamespace(
            manifests=[object()] * 3,
            config_files=[object()],
            ci_files=[],
            instruction_files=[object()] * 3,
            docs_files=[object()] * 2,
            parse_errors=[],
        ),
        symbol_index=SimpleNamespace(
            symbols=[object()] * 791,
            parse_errors=[object()] * symbol_parse_errors,
        ),
        repo_graph=SimpleNamespace(
            nodes=[object()] * 1089,
            edges=[object()] * 1097,
            unresolved_imports=[object()] * unresolved_imports,
        ),
        repo_discovery=SimpleNamespace(
            artifact_checksums={str(index): "checksum" for index in range(5)},
            available_tools=[f"tool-{index}" for index in range(18)],
        ),
        supported_file_count=110,
        artifacts_dir=".bridger/artifacts/",
        artifact_paths={
            "file-index": ".bridger/artifacts/file-index.json",
            "repo-context": ".bridger/artifacts/repo-context.json",
            "symbol-index": ".bridger/artifacts/symbol-index.json",
            "repo-graph": ".bridger/artifacts/repo-graph.json",
            "graph-summary": ".bridger/artifacts/graph-summary.json",
            "repo-discovery": ".bridger/artifacts/repo-discovery.json",
        },
        next_step="agentic repository discovery is not implemented yet",
        already_exists=False,
    )
