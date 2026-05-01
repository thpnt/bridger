import type { KnowledgeDocKey } from "./doc-types";

export const GENERATED_DOC_FILENAMES = {
  repoAnalysis: "repo-analysis.md",
  architecture: "architecture.md",
  businessLogic: "business-logic.md",
  conventions: "conventions.md",
  testing: "testing.md",
  agentRules: "agent-rules.md",
} as const satisfies Record<KnowledgeDocKey, string>;

export type GeneratedDocFilename =
  (typeof GENERATED_DOC_FILENAMES)[keyof typeof GENERATED_DOC_FILENAMES];
