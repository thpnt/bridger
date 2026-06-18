from bridger.models.file_index import FileIndexArtifact
from bridger.models.graph_summary import GraphSummaryArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.repo_discovery import RepoDiscoveryCompactContext


def extract_compact_context(
    file_index: FileIndexArtifact,
    repo_context: RepoContextArtifact,
    graph_summary: GraphSummaryArtifact,
) -> RepoDiscoveryCompactContext:
    return RepoDiscoveryCompactContext(
        file_count=len(file_index.files),
        skipped_file_count=len(file_index.skipped_files),
        manifest_files=[manifest.path for manifest in repo_context.manifests],
        config_files=[config.path for config in repo_context.config_files],
        instruction_files=[
            instruction.path for instruction in repo_context.instruction_files
        ],
        docs_files=[docs.path for docs in repo_context.docs_files],
        ci_files=[ci.path for ci in repo_context.ci_files],
        declared_entrypoints=graph_summary.declared_entrypoints,
        graph_counts=graph_summary.counts,
    )
