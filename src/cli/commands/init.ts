import path from "node:path";

import { Command } from "commander";

import { buildRepoContextArtifacts } from "../../core/context-builder/build-repo-context";
import { generateAgentRulesDoc } from "../../core/doc-generator/generators/generate-agent-rules-doc";
import { generateArchitectureDoc } from "../../core/doc-generator/generators/generate-architecture-doc";
import { generateBusinessLogicDoc } from "../../core/doc-generator/generators/generate-business-logic-doc";
import { generateConventionsDoc } from "../../core/doc-generator/generators/generate-conventions-doc";
import { generateRepoAnalysisDoc } from "../../core/doc-generator/generators/generate-repo-analysis-doc";
import { generateTestingDoc } from "../../core/doc-generator/generators/generate-testing-doc";
import { renderAgentsMd } from "../../core/doc-generator/renderers/render-agents-md";
import { createBridgerConfig } from "../../core/project/create-bridger-config";
import { ensureOutputDirs } from "../../core/output/ensure-output-dirs";
import { writeBridgerConfig } from "../../core/project/write-bridger-config";
import { upsertGeneratedMarkdownBlock } from "../../core/output/upsert-generated-markdown-block";
import { writeJson } from "../../core/output/write-json";
import { writeMarkdown } from "../../core/output/write-markdown";
import { buildGraphSummary } from "../../core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../core/repo-graph/build-repo-graph";
import { readGraphOrderedFiles } from "../../core/repo-graph/read-graph-ordered-files";
import { writeRepoGraphArtifacts } from "../../core/repo-graph/write-repo-graph";
import { IMPORTANT_FILE_BUDGETS } from "../../core/repo-scanner/important-file-rules";
import {
  getAgentsGeneratedPath,
  getAgentsMdPath,
  getBridgerConfigPath,
  getFileIndexPath,
  getGraphSummaryPath,
  getGeneratedKnowledgeDocPath,
  getRepoGraphPath,
  getRepoContextPath,
  getTicketTemplatePath,
  resolveRepoRoot,
} from "../../core/utils/paths";
import { logger } from "../../shared/logger";

interface InitCommandOptions {
  repo?: string;
  writeAgentsMd?: boolean;
}

interface GeneratedDocs {
  architectureMarkdown: string;
  repoAnalysisMarkdown: string;
  conventionsMarkdown: string;
  businessLogicMarkdown: string;
  testingMarkdown: string;
  agentRulesMarkdown: string;
}

interface InitSummaryInput {
  repoRoot: string;
  indexedFileCount: number;
  generatedFiles: string[];
  skippedFiles: string[];
}

const BRIDGER_GENERATED_START_MARKER = "<!-- BRIDGER GENERATED START -->";
const BRIDGER_GENERATED_END_MARKER = "<!-- BRIDGER GENERATED END -->";
const INIT_GRAPH_CONTEXT_MAX_FILES = 40;
const INIT_GRAPH_CONTEXT_MAX_SINGLE_FILE_BYTES =
  IMPORTANT_FILE_BUDGETS.maxSingleFileBytes;
const INIT_GRAPH_CONTEXT_MAX_TOTAL_BYTES =
  IMPORTANT_FILE_BUDGETS.maxTotalContentBytes;

function logInitStep(message: string): void {
  logger.debug(`bridger init: ${message}`);
}

async function generateDocs(input: {
  repoContext: Awaited<ReturnType<typeof buildRepoContextArtifacts>>["repoContext"];
  fileIndex: Awaited<ReturnType<typeof buildRepoContextArtifacts>>["fileIndex"];
  importantFiles: Awaited<ReturnType<typeof buildRepoContextArtifacts>>["importantFiles"];
}): Promise<GeneratedDocs> {
  const generationInput = {
    repoContext: input.repoContext,
    fileIndex: input.fileIndex,
    importantFiles: input.importantFiles,
  };

  const repoAnalysisMarkdown = await generateRepoAnalysisDoc(generationInput);
  const architectureMarkdown = await generateArchitectureDoc(generationInput);
  const conventionsMarkdown = await generateConventionsDoc(generationInput);
  const businessLogicMarkdown = await generateBusinessLogicDoc(generationInput);
  const testingMarkdown = await generateTestingDoc(generationInput);

  const agentRulesMarkdown = await generateAgentRulesDoc({
    repoContext: input.repoContext,
    generatedDocs: {
      repoAnalysis: repoAnalysisMarkdown,
      architecture: architectureMarkdown,
      conventions: conventionsMarkdown,
      businessLogic: businessLogicMarkdown,
      testing: testingMarkdown,
    },
  });

  return {
    architectureMarkdown,
    repoAnalysisMarkdown,
    conventionsMarkdown,
    businessLogicMarkdown,
    testingMarkdown,
    agentRulesMarkdown,
  };
}

async function writeGeneratedDocs(input: {
  repoRoot: string;
  generatedDocs: GeneratedDocs;
}): Promise<void> {
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "architecture"),
    input.generatedDocs.architectureMarkdown,
  );
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "repoAnalysis"),
    input.generatedDocs.repoAnalysisMarkdown,
  );
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "conventions"),
    input.generatedDocs.conventionsMarkdown,
  );
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "businessLogic"),
    input.generatedDocs.businessLogicMarkdown,
  );
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "testing"),
    input.generatedDocs.testingMarkdown,
  );
  await writeMarkdown(
    getGeneratedKnowledgeDocPath(input.repoRoot, "agentRules"),
    input.generatedDocs.agentRulesMarkdown,
  );
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

  lines.push("");
  lines.push("Skipped:");

  if (input.skippedFiles.length === 0) {
    lines.push("- none");
  } else {
    for (const filePath of input.skippedFiles) {
      lines.push(`- ${filePath}`);
    }
  }

  return lines.join("\n");
}

function getGeneratedFilePaths(repoRoot: string, writeAgentsMd: boolean): string[] {
  const filePaths = [
    getBridgerConfigPath(repoRoot),
    getRepoContextPath(repoRoot),
    getFileIndexPath(repoRoot),
    getRepoGraphPath(repoRoot),
    getGraphSummaryPath(repoRoot),
    getGeneratedKnowledgeDocPath(repoRoot, "architecture"),
    getGeneratedKnowledgeDocPath(repoRoot, "repoAnalysis"),
    getGeneratedKnowledgeDocPath(repoRoot, "conventions"),
    getGeneratedKnowledgeDocPath(repoRoot, "businessLogic"),
    getGeneratedKnowledgeDocPath(repoRoot, "testing"),
    getGeneratedKnowledgeDocPath(repoRoot, "agentRules"),
    getTicketTemplatePath(repoRoot),
    getAgentsGeneratedPath(repoRoot),
  ];

  if (writeAgentsMd) {
    filePaths.push(getAgentsMdPath(repoRoot));
  }

  return filePaths.map((filePath) => path.relative(repoRoot, filePath));
}

function getDetectedStackNames(
  stack: Awaited<ReturnType<typeof buildRepoContextArtifacts>>["repoContext"]["stack"],
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
        writeRootAgentsFile: Boolean(options.writeAgentsMd),
      }),
    );
    logInitStep("project config written");

    logInitStep("building repo graph");
    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex,
    });
    const graphSummary = buildGraphSummary(graph);
    logInitStep("repo graph ready");

    logInitStep("writing deterministic artifacts");
    await writeJson(getRepoContextPath(repoRoot), repoContext);
    await writeJson(getFileIndexPath(repoRoot), fileIndex);
    await writeRepoGraphArtifacts({
      repoRoot,
      graph,
      summary: graphSummary,
    });
    logInitStep("deterministic artifacts written");

    logInitStep("reading graph-ordered file context");
    const graphOrderedFileContext = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary: graphSummary,
      mode: "architecture-first",
      maxFiles: INIT_GRAPH_CONTEXT_MAX_FILES,
      maxSingleFileBytes: INIT_GRAPH_CONTEXT_MAX_SINGLE_FILE_BYTES,
      maxTotalBytes: INIT_GRAPH_CONTEXT_MAX_TOTAL_BYTES,
    });
    logInitStep(
      `graph-ordered file context ready (${graphOrderedFileContext.files.length} files)`,
    );

    if (graphOrderedFileContext.diagnostics.length > 0) {
      logger.warn(
        `Skipped ${graphOrderedFileContext.diagnostics.length} graph-ordered context files.`,
      );
    }

    logInitStep("generating documentation");
    const generatedDocs = await generateDocs({
      repoContext,
      fileIndex,
      importantFiles: graphOrderedFileContext.files.map((file) => ({
        path: file.path,
        reason: file.reason,
        content: file.content,
      })),
    });
    logInitStep("documentation generated");

    logInitStep("writing generated files");
    await writeGeneratedDocs({
      repoRoot,
      generatedDocs,
    });

    const agentsMarkdown = renderAgentsMd({
      repoContext,
      agentRulesMarkdown: generatedDocs.agentRulesMarkdown,
    });

    await writeMarkdown(getAgentsGeneratedPath(repoRoot), agentsMarkdown);
    logInitStep("generated files written");

    if (options.writeAgentsMd) {
      logInitStep("updating AGENTS.md");
      await upsertGeneratedMarkdownBlock({
        filePath: getAgentsMdPath(repoRoot),
        content: agentsMarkdown,
        startMarker: BRIDGER_GENERATED_START_MARKER,
        endMarker: BRIDGER_GENERATED_END_MARKER,
      });
      logInitStep("AGENTS.md updated");
    }

    const generatedFiles = getGeneratedFilePaths(repoRoot, Boolean(options.writeAgentsMd));
    const skippedFiles = options.writeAgentsMd
      ? []
      : [
          "AGENTS.md unchanged. Run `bridger init --write-agents-md` to append/update the generated Bridger section.",
        ];

    logger.info(
      formatInitSummary({
        repoRoot,
        indexedFileCount: fileIndex.files.length,
        generatedFiles,
        skippedFiles,
      }),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`bridger init failed: ${message}`);
    process.exitCode = 1;
  }
}

export const initCommand = new Command("init")
  .description("Generate Bridger repo context and agent-ready documentation")
  .option("--repo <path>", "Path to the repository to initialize")
  .option(
    "--write-agents-md",
    "Append/update generated Bridger section in AGENTS.md",
  )
  .action(async (options: InitCommandOptions) => {
    await runInitCommand({
      repo: options.repo,
      writeAgentsMd: Boolean(options.writeAgentsMd),
    });
  });
