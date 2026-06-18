import type { ReadingPlanKind } from "./models/reading-plans";

export const READING_PLAN_BATCH_BUDGET = {
  maxFiles: 10,
  maxBytes: 60_000,
} as const;

export const READING_PLAN_BUDGETS: Record<
  ReadingPlanKind,
  { maxFiles: number; maxBytes: number }
> = {
  "repo-analysis": { maxFiles: 40, maxBytes: 240_000 },
  architecture: { maxFiles: 60, maxBytes: 360_000 },
  "business-logic": { maxFiles: 50, maxBytes: 300_000 },
  conventions: { maxFiles: 50, maxBytes: 300_000 },
  testing: { maxFiles: 50, maxBytes: 300_000 },
};
