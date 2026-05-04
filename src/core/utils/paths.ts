import path from "node:path";

import { GENERATED_DOC_FILENAMES } from "../doc-generator/doc-filenames";
import type { KnowledgeDocKey } from "../doc-generator/doc-types";

export const BRIDGER_DIR_NAME = ".bridger";
export const GENERATED_DIR_NAME = "generated";
export const TICKETS_DIR_NAME = "tickets";

export function resolveRepoRoot(input?: string): string {
  return path.resolve(input ?? process.cwd());
}

export function getBridgerDir(repoRoot: string): string {
  return path.join(repoRoot, BRIDGER_DIR_NAME);
}

export function getGeneratedDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), GENERATED_DIR_NAME);
}

export function getTicketsDir(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), TICKETS_DIR_NAME);
}

export function getRepoContextPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "repo-context.json");
}

export function getFileIndexPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "file-index.json");
}

export function getRepoGraphPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "repo-graph.json");
}

export function getGraphSummaryPath(repoRoot: string): string {
  return path.join(getBridgerDir(repoRoot), "graph-summary.json");
}

export function getGeneratedDocPath(
  repoRoot: string,
  filename: string,
): string {
  return path.join(getGeneratedDir(repoRoot), filename);
}

export function getGeneratedKnowledgeDocPath(
  repoRoot: string,
  key: KnowledgeDocKey,
): string {
  return getGeneratedDocPath(repoRoot, GENERATED_DOC_FILENAMES[key]);
}

export function getAgentsGeneratedPath(repoRoot: string): string {
  return path.join(repoRoot, "AGENTS.generated.md");
}

export function getAgentsMdPath(repoRoot: string): string {
  return path.join(repoRoot, "AGENTS.md");
}

export function getAgentReadyDir(repoRoot: string): string {
  return getBridgerDir(repoRoot);
}
