import { buildFileIndex } from "../repo-scanner/build-file-index";
import { detectCommands } from "../repo-scanner/detect-commands";
import { detectStack } from "../repo-scanner/detect-stack";
import { readImportantFiles } from "../repo-scanner/read-important-files";
import { RepoRelativePathSchema } from "../models/paths";
import type {
  RepoContext,
  RepoContextGeneratedDocs,
} from "../models/repo-context";
import { RepoContextSchema } from "../models/repo-context";
import {
  RepoContextBuildArtifactsSchema,
  type RepoContextBuildArtifacts,
} from "../models/repo-context-build";

function getGeneratedDocPaths(): RepoContextGeneratedDocs {
  return {
    repoAnalysisPath: RepoRelativePathSchema.parse(
      ".bridger/generated/repo-analysis.md",
    ),
    architecturePath: RepoRelativePathSchema.parse(
      ".bridger/generated/architecture.md",
    ),
    conventionsPath: RepoRelativePathSchema.parse(
      ".bridger/generated/conventions.md",
    ),
    businessLogicPath: RepoRelativePathSchema.parse(
      ".bridger/generated/business-logic.md",
    ),
    testingPath: RepoRelativePathSchema.parse(".bridger/generated/testing.md"),
    agentRulesPath: RepoRelativePathSchema.parse(
      ".bridger/generated/agent-rules.md",
    ),
    ticketTemplatePath: RepoRelativePathSchema.parse(
      ".bridger/generated/ticket-template.md",
    ),
  };
}

export async function buildRepoContextArtifacts(
  repoRoot: string,
): Promise<RepoContextBuildArtifacts> {
  const stack = await detectStack(repoRoot);
  const commands = await detectCommands(repoRoot, stack.packageManager);
  const fileIndex = await buildFileIndex(repoRoot);
  const importantFiles = await readImportantFiles({
    repoRoot,
    fileIndex,
  });

  const repoContext = RepoContextSchema.parse({
    repoRoot,
    generatedAt: new Date().toISOString(),
    stack,
    commands,
    importantFiles: importantFiles.map((file) => ({
      path: file.path,
      reason: file.reason,
    })),
    generatedDocs: getGeneratedDocPaths(),
  });

  return RepoContextBuildArtifactsSchema.parse({
    repoContext,
    fileIndex,
  });
}

export async function buildRepoContext(repoRoot: string): Promise<RepoContext> {
  const { repoContext } = await buildRepoContextArtifacts(repoRoot);

  return repoContext;
}
