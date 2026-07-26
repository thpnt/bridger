import asyncio
from enum import IntEnum
from pathlib import Path
from uuid import uuid4

from bridger.artifacts import write_artifact
from bridger.cli_output import (
    build_init_run_summary,
    render_context_plan_failure,
    render_context_plan_success,
    render_init_summary,
)
from bridger.console import console
from bridger.deterministic.context_plan import (
    ContextPlanValidationError,
    create_context_plan_builder,
)
from bridger.deterministic.context_plan_bootstrap import (
    build_context_plan_bootstrap_for_project,
)
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.repo_context import build_repo_context_for_project
from bridger.deterministic.symbols import (
    TreeSitterCompatibilityError,
    build_extractor_registry,
    build_symbol_index_for_project,
    extractor_for_path,
)
from bridger.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
)
from bridger.llm.factory import create_llm_client
from bridger.models.context_plan import ContextPlanRun, ContextPlanRunStatus
from bridger.paths import ProjectPaths
from bridger.project import initialize_project
from bridger.tools.errors import BridgerToolError


class InitExitCode(IntEnum):
    SUCCESS = 0
    UNEXPECTED = 1
    CONFIGURATION = 2
    PREREQUISITES = 3
    PROVIDER = 4
    BUDGET_OR_STALLED = 5
    VALIDATION = 6
    INTERRUPTED = 7
    ARTIFACT_WRITE = 8


def run(fresh: bool, verbose: bool, llm_profile: str | None = None) -> int:
    paths = ProjectPaths.from_cwd()
    try:
        already_exists, config = initialize_project(paths, fresh)
        if config is None:
            return _fail(
                "Project configuration is missing or invalid.",
                InitExitCode.CONFIGURATION,
                next_step="Fix .bridger/config.json and run bridger init again.",
            )

        file_index = build_file_index_for_project(paths.root)
        write_artifact(paths.file_index_artifact, file_index)
        repo_context = build_repo_context_for_project(paths.root)
        write_artifact(paths.repo_context_artifact, repo_context)
        symbol_index = build_symbol_index_for_project(paths.root)
        write_artifact(paths.symbol_index_artifact, symbol_index)
        context_plan_bootstrap = build_context_plan_bootstrap_for_project(paths.root)
        write_artifact(paths.context_plan_bootstrap_artifact, context_plan_bootstrap)
        extractor_registry = build_extractor_registry()
        supported_files = sum(
            extractor_for_path(file.path, extractor_registry) is not None
            for file in file_index.files
        )

        summary = build_init_run_summary(
            paths=paths,
            file_index=file_index,
            repo_context=repo_context,
            symbol_index=symbol_index,
            context_plan_bootstrap=context_plan_bootstrap,
            supported_file_count=supported_files,
            already_exists=already_exists,
        )
        render_init_summary(summary, verbose=verbose)

        if config.project_mode == "fresh":
            console.print("Fresh mode is currently a deterministic-only placeholder.")
            return InitExitCode.SUCCESS

        profile = llm_profile or config.llm.default_profile
        console.print("[cyan]● Generating Context Plan[/cyan]")
        client = create_llm_client(profile)
        builder = create_context_plan_builder(
            paths.root,
            llm_client=client,
            model_profile=profile,
        )
        context_plan_run = asyncio.run(builder.build(run_id=uuid4().hex))
        return _render_context_plan_result(paths, context_plan_run, verbose)
    except (KeyboardInterrupt, asyncio.CancelledError):
        return _fail(
            "Context Plan generation was interrupted.",
            InitExitCode.INTERRUPTED,
            paths=paths,
            next_step="Review the run record before retrying.",
        )
    except ContextPlanValidationError as error:
        issue_codes = ", ".join(issue.code for issue in error.issues)
        return _fail(
            f"Context Plan validation failed ({issue_codes}).",
            InitExitCode.VALIDATION,
            paths=paths,
            next_step=(
                "Review the run record and correct the reported validation issues."
            ),
        )
    except BridgerToolError as error:
        return _fail(
            error.payload.message,
            InitExitCode.PREREQUISITES,
            paths=paths,
            next_step="Run bridger init again to regenerate deterministic artifacts.",
        )
    except TreeSitterCompatibilityError as error:
        return _fail(
            str(error),
            InitExitCode.PREREQUISITES,
            paths=paths,
            next_step="Reinstall Bridger so tree-sitter 0.25.x is selected.",
        )
    except LLMConfigurationError as error:
        return _fail(
            error.safe_message,
            InitExitCode.CONFIGURATION,
            paths=paths,
            next_step="Check the selected LLM profile and its environment settings.",
        )
    except LLMAuthenticationError as error:
        return _fail(
            error.safe_message,
            InitExitCode.PROVIDER,
            paths=paths,
            next_step="Check provider credentials and retry.",
        )
    except LLMError as error:
        return _fail(
            error.safe_message,
            InitExitCode.PROVIDER,
            paths=paths,
            next_step="Check provider status, rate limits, and retry.",
        )
    except OSError as error:
        return _fail(
            f"Could not write a Bridger artifact: {error}",
            InitExitCode.ARTIFACT_WRITE,
            paths=paths,
            next_step="Check repository permissions and available disk space.",
        )
    except Exception:
        return _fail(
            "An unexpected internal error occurred.",
            InitExitCode.UNEXPECTED,
            paths=paths,
            next_step=(
                "Re-run with the existing debug workflow and include the run record."
            ),
        )


def _render_context_plan_result(
    paths: ProjectPaths,
    run: ContextPlanRun,
    verbose: bool,
) -> int:
    if run.status is ContextPlanRunStatus.COMPLETED and run.output is not None:
        render_context_plan_success(
            run,
            context_plan_path=_relative_path(paths.root, paths.context_plan_artifact),
            run_artifact_path=_relative_path(
                paths.root, paths.context_plan_run_artifact
            ),
            verbose=verbose,
        )
        return InitExitCode.SUCCESS

    code = (
        InitExitCode.BUDGET_OR_STALLED
        if run.status
        in {ContextPlanRunStatus.BUDGET_EXHAUSTED, ContextPlanRunStatus.STALLED}
        else InitExitCode.UNEXPECTED
    )
    message = {
        ContextPlanRunStatus.BUDGET_EXHAUSTED: "Discovery budget was exhausted.",
        ContextPlanRunStatus.STALLED: "Discovery stalled without sufficient progress.",
    }.get(run.status, "Context Plan generation did not complete.")
    return _fail(
        message,
        code,
        paths=paths,
        next_step="Review the run record before retrying.",
    )


def _fail(
    message: str,
    code: InitExitCode,
    *,
    paths: ProjectPaths | None = None,
    next_step: str | None = None,
) -> int:
    run_artifact_path = None
    if paths is not None and paths.context_plan_run_artifact.is_file():
        run_artifact_path = _relative_path(paths.root, paths.context_plan_run_artifact)
    render_context_plan_failure(
        message,
        run_artifact_path=run_artifact_path,
        next_step=next_step,
    )
    return code


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
