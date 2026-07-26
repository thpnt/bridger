from dataclasses import dataclass
from pathlib import Path

from bridger.tools.services import (
    ArtifactStore,
    BudgetService,
    FileIndexService,
    FileReadService,
    PathSafetyService,
    RepoContextService,
    SearchService,
    SymbolService,
)


@dataclass(frozen=True)
class BridgerToolContext:
    repo_root: Path
    artifact_store: ArtifactStore
    path_safety: PathSafetyService
    budgets: BudgetService
    file_index: FileIndexService
    file_read: FileReadService
    search: SearchService
    repo_context: RepoContextService
    symbols: SymbolService


def build_tool_context(repo_root: Path) -> BridgerToolContext:
    root = repo_root.resolve()
    store = ArtifactStore(root)
    file_index_artifact = store.load_file_index()
    repo_context_artifact = store.load_repo_context()
    symbol_index_artifact = store.load_symbol_index()
    context_plan_bootstrap = store.load_context_plan_bootstrap()
    budgets = BudgetService(context_plan_bootstrap.budgets)
    paths = PathSafetyService(file_index_artifact, root)
    file_index = FileIndexService(file_index_artifact, paths, budgets)
    file_read = FileReadService(root, paths, file_index, budgets)
    return BridgerToolContext(
        repo_root=root,
        artifact_store=store,
        path_safety=paths,
        budgets=budgets,
        file_index=file_index,
        file_read=file_read,
        search=SearchService(root, file_index, budgets),
        repo_context=RepoContextService(repo_context_artifact, paths, budgets),
        symbols=SymbolService(symbol_index_artifact, paths, budgets),
    )
