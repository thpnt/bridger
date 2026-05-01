export type KnowledgeDocKey =
  | "repoAnalysis"
  | "architecture"
  | "businessLogic"
  | "conventions"
  | "testing"
  | "agentRules";

export type KnowledgeDocSpec = {
  key: KnowledgeDocKey;
  filename: string;
  displayName: string;
  requiredSections: readonly string[];
};
