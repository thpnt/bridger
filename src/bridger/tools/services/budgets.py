from bridger.models.repo_discovery import RepoDiscoveryBudgets


class BudgetService:
    def __init__(self, budgets: RepoDiscoveryBudgets | None = None) -> None:
        self.values = budgets or RepoDiscoveryBudgets()

    def apply_limit(self, requested: int | None, maximum: int) -> int:
        if requested is None:
            return maximum
        return min(requested, maximum)

    def file_limit(self, requested: int | None = None) -> int:
        return self.apply_limit(requested, self.values.max_files_read)

    def grep_limit(self, requested: int | None = None) -> int:
        return self.apply_limit(requested, self.values.max_grep_results)

    def symbol_limit(self, requested: int | None = None) -> int:
        return self.apply_limit(requested, self.values.max_symbol_results)

    def graph_limit(self, requested: int | None = None) -> int:
        return self.apply_limit(requested, self.values.max_graph_neighbors)
