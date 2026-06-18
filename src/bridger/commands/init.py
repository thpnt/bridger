from bridger.artifacts import write_artifact
from bridger.console import console
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.repo_context import build_repo_context_for_project
from bridger.paths import ProjectPaths
from bridger.project import initialize_project


def run(fresh: bool) -> None:
    paths = ProjectPaths.from_cwd()
    already_exists, _ = initialize_project(paths, fresh)
    file_index = build_file_index_for_project(paths.root)
    write_artifact(paths.file_index_artifact, file_index)
    repo_context = build_repo_context_for_project(paths.root)
    write_artifact(paths.repo_context_artifact, repo_context)

    if already_exists:
        console.print(
            "[green]Bridger project is ready.[/green] Existing files preserved."
        )
    else:
        console.print("[green]Bridger project initialized.[/green]")

    console.print(
        f"Indexed {file_index.stats.files_included} files; "
        f"skipped {file_index.stats.files_skipped}. "
        f"Artifact: {paths.file_index_artifact.relative_to(paths.root).as_posix()}"
    )
    console.print(
        f"Found {len(repo_context.manifests)} manifests, "
        f"{len(repo_context.config_files)} config files, "
        f"{len(repo_context.ci_files)} CI files, "
        f"{len(repo_context.instruction_files)} instruction files, "
        f"{len(repo_context.docs_files)} docs files, and "
        f"{len(repo_context.parse_errors)} parse errors. "
        f"Artifact: {paths.repo_context_artifact.relative_to(paths.root).as_posix()}"
    )

    if fresh:
        console.print("Fresh mode is currently a placeholder.")
