import path from "node:path";

import {
  RepoRelativePathSchema,
  type RepoRelativePath,
} from "../models/path";

export type BridgerMemoryFile =
  | "repo-analysis.md"
  | "architecture.md"
  | "business-logic.md"
  | "conventions.md"
  | "testing.md";

export type KnowledgeDocKey =
  | "repoAnalysis"
  | "architecture"
  | "businessLogic"
  | "conventions"
  | "testing";

const MEMORY_FILENAMES = {
  repoAnalysis: "repo-analysis.md",
  architecture: "architecture.md",
  businessLogic: "business-logic.md",
  conventions: "conventions.md",
  testing: "testing.md",
} as const satisfies Record<KnowledgeDocKey, BridgerMemoryFile>;

export interface GeneratedDocPaths {
  repoAnalysisPath: RepoRelativePath;
  architecturePath: RepoRelativePath;
  businessLogicPath: RepoRelativePath;
  conventionsPath: RepoRelativePath;
  testingPath: RepoRelativePath;
}

export function getBridgerDir(repoRoot: string): string {
  return path.join(repoRoot, ".bridger");
}

export function getBridgerConfigPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "config.json");
}

export function getBridgerIndexPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "index.md");
}

export function getBridgerLogPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "log.md");
}

export function getArtifactsDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "artifacts");
}

export function getFileIndexPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "file-index.json");
}

export function getRepoContextPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "repo-context.json");
}

export function getRepoGraphPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "repo-graph.json");
}

export function getGraphSummaryPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "graph-summary.json");
}

export function getCodebaseMapPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "codebase-map.json");
}

export function getReadingPlansPath(repoRoot: string): string {
  return path.join(getArtifactsDir(repoRoot), "reading-plans.json");
}

export function getMemoryDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "memory");
}

export function getMemoryFilePath(
  repoRoot: string,
  file: BridgerMemoryFile,
): string {
  return path.join(getMemoryDir(repoRoot), file);
}

export function getGeneratedKnowledgeDocPath(
  repoRoot: string,
  key: KnowledgeDocKey,
): string {
  return getMemoryFilePath(repoRoot, MEMORY_FILENAMES[key]);
}

export function getGeneratedKnowledgeDocRelativePath(
  key: KnowledgeDocKey,
): RepoRelativePath {
  return RepoRelativePathSchema.parse(
    [".bridger", "memory", MEMORY_FILENAMES[key]].join("/"),
  );
}

export function getSkillsDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "skills");
}

export function getSelectedSkillsPath(repoRoot: string): string {
  return path.join(getSkillsDir(repoRoot), "selected-skills.json");
}

export function getTemplatesDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "templates");
}

export function getTicketTemplatePath(repoRoot: string): string {
  return path.join(getTemplatesDir(repoRoot), "ticket-template.md");
}

export function getTicketTemplateRelativePath(): RepoRelativePath {
  return RepoRelativePathSchema.parse(
    [".bridger", "templates", "ticket-template.md"].join("/"),
  );
}

export function getExportsDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "exports");
}

export function getAgentsGeneratedExportPath(repoRoot: string): string {
  return path.join(getExportsDir(repoRoot), "AGENTS.generated.md");
}

export function getClaudeGeneratedExportPath(repoRoot: string): string {
  return path.join(getExportsDir(repoRoot), "CLAUDE.generated.md");
}

export function getRootAgentsPath(repoRoot: string): string {
  return path.join(repoRoot, "AGENTS.md");
}

export function buildGeneratedDocPaths(): GeneratedDocPaths {
  return {
    repoAnalysisPath: getGeneratedKnowledgeDocRelativePath("repoAnalysis"),
    architecturePath: getGeneratedKnowledgeDocRelativePath("architecture"),
    businessLogicPath: getGeneratedKnowledgeDocRelativePath("businessLogic"),
    conventionsPath: getGeneratedKnowledgeDocRelativePath("conventions"),
    testingPath: getGeneratedKnowledgeDocRelativePath("testing"),
  };
}
