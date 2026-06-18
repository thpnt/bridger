import path from "node:path";

import { Command } from "commander";

import { buildCodebaseMap } from "../../core/codebase-map/build-codebase-map";
import { writeCodebaseMapArtifact } from "../../core/codebase-map/write-codebase-map";
import { buildRepoContextArtifacts } from "../../core/context-builder/build-repo-context";
import { ensureOutputDirs } from "../../core/output/ensure-output-dirs";
import { createBridgerConfig } from "../../core/project/create-bridger-config";
import { writeBridgerConfig } from "../../core/project/write-bridger-config";
import { buildReadingPlans } from "../../core/reading-plans/build-reading-plans";
import { writeReadingPlansArtifact } from "../../core/reading-plans/write-reading-plans";
import { buildGraphSummary } from "../../core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../core/repo-graph/build-repo-graph";
import { writeRepoGraphArtifacts } from "../../core/repo-graph/write-repo-graph";
import {
  getBridgerConfigPath,
  getCodebaseMapPath,
  getFileIndexPath,
  getGraphSummaryPath,
  getReadingPlansPath,
  getRepoContextPath,
  getRepoGraphPath,
  getTicketTemplatePath,
  resolveRepoRoot,
} from "../../core/utils/paths";
import { writeJson } from "../../core/output/write-json";
import { logger } from "../../shared/logger";

interface InitCommandOptions {
  repo?: string;
}

interface InitSummaryInput {
  repoRoot: string;
  indexedFileCount: number;
  generatedFiles: string[];
}

function logInitStep(message: string): void {
  logger.debug(`bridger init: ${message}`);
}

function formatInitSummary(input: InitSummaryInput): string {
  const lines: string[] = [
    "SUCCESS: bridger init complete",
    "",
    `Repo: ${input.repoRoot}`,
    `Indexed files: ${input.indexedFileCount}`,
    "",
    "Generated:",
  ];

  for (const filePath of input.generatedFiles) {
    lines.push(`- ${filePath}`);
  }

  return lines.join("\n");
}

function getGeneratedFilePaths(repoRoot: string): string[] {
  return [
    getBridgerConfigPath(repoRoot),
    getRepoContextPath(repoRoot),
    getFileIndexPath(repoRoot),
    getRepoGraphPath(repoRoot),
    getGraphSummaryPath(repoRoot),
    getCodebaseMapPath(repoRoot),
    getReadingPlansPath(repoRoot),
    getTicketTemplatePath(repoRoot),
  ].map((filePath) => path.relative(repoRoot, filePath));
}

function getDetectedStackNames(
  stack: Awaited<
    ReturnType<typeof buildRepoContextArtifacts>
  >["repoContext"]["stack"],
): string[] {
  return [
    stack.framework,
    stack.language,
    ...stack.styling,
    ...stack.validation,
    ...stack.database,
    ...stack.testFramework,
  ].filter((value) => value.length > 0 && value !== "unknown");
}

export async function runInitCommand(
  options: InitCommandOptions = {},
): Promise<void> {
  const repoRoot = resolveRepoRoot(options.repo);

  try {
    logInitStep(`starting for ${repoRoot}`);
    logInitStep("ensuring output directories");
    await ensureOutputDirs(repoRoot);
    logInitStep("output directories ready");

    logInitStep("building repo context");
    const { repoContext, fileIndex, importantFiles } =
      await buildRepoContextArtifacts(repoRoot);
    logInitStep(
      `repo context ready (${fileIndex.files.length} indexed files, ${importantFiles.length} important files)`,
    );

    logInitStep("writing project config");
    await writeBridgerConfig(
      repoRoot,
      createBridgerConfig({
        repoRoot,
        mode: fileIndex.files.length > 0 ? "existing" : "unknown",
        detectedStack: getDetectedStackNames(repoContext.stack),
        packageManager: repoContext.stack.packageManager || undefined,
      }),
    );
    logInitStep("project config written");

    logInitStep("building deterministic artifacts");
    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex,
    });
    const graphSummary = buildGraphSummary(graph);
    const codebaseMap = buildCodebaseMap({
      repoRoot,
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary,
    });
    const readingPlans = buildReadingPlans({
      repoRoot,
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary,
      codebaseMap,
    });
    logInitStep("deterministic artifacts ready");

    logInitStep("writing deterministic artifacts");
    await writeJson(getRepoContextPath(repoRoot), repoContext);
    await writeJson(getFileIndexPath(repoRoot), fileIndex);
    await writeRepoGraphArtifacts({
      repoRoot,
      graph,
      summary: graphSummary,
    });
    await writeCodebaseMapArtifact({ repoRoot, codebaseMap });
    await writeReadingPlansArtifact({ repoRoot, readingPlans });
    logInitStep("deterministic artifacts written");

    logger.info(
      formatInitSummary({
        repoRoot,
        indexedFileCount: fileIndex.files.length,
        generatedFiles: getGeneratedFilePaths(repoRoot),
      }),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`bridger init failed: ${message}`);
    process.exitCode = 1;
  }
}

export const initCommand = new Command("init")
  .description("Generate deterministic Bridger repository artifacts")
  .option("--repo <path>", "Path to the repository to initialize")
  .action(async (options: InitCommandOptions) => {
    await runInitCommand({
      repo: options.repo,
    });
  });
