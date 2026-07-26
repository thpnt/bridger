from bridger.models.context_plan_bootstrap import ContextPlanBootstrapBudgets


class BudgetService:
    def __init__(self, budgets: ContextPlanBootstrapBudgets | None = None) -> None:
        self.values = budgets or ContextPlanBootstrapBudgets()

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
