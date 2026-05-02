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
import { ensureOutputDirs } from "../../core/output/ensure-output-dirs";
import { upsertGeneratedMarkdownBlock } from "../../core/output/upsert-generated-markdown-block";
import { writeJson } from "../../core/output/write-json";
import { writeMarkdown } from "../../core/output/write-markdown";
import {
  getAgentsGeneratedPath,
  getAgentsMdPath,
  getFileIndexPath,
  getGeneratedKnowledgeDocPath,
  getRepoContextPath,
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
    "bridger init complete",
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

  for (const filePath of input.skippedFiles) {
    lines.push(`- ${filePath}`);
  }

  return lines.join("\n");
}

function getGeneratedFilePaths(repoRoot: string, writeAgentsMd: boolean): string[] {
  const filePaths = [
    getRepoContextPath(repoRoot),
    getFileIndexPath(repoRoot),
    getGeneratedKnowledgeDocPath(repoRoot, "architecture"),
    getGeneratedKnowledgeDocPath(repoRoot, "repoAnalysis"),
    getGeneratedKnowledgeDocPath(repoRoot, "conventions"),
    getGeneratedKnowledgeDocPath(repoRoot, "businessLogic"),
    getGeneratedKnowledgeDocPath(repoRoot, "testing"),
    getGeneratedKnowledgeDocPath(repoRoot, "agentRules"),
    getAgentsGeneratedPath(repoRoot),
  ];

  if (writeAgentsMd) {
    filePaths.push(getAgentsMdPath(repoRoot));
  }

  return filePaths.map((filePath) => path.relative(repoRoot, filePath));
}

export async function runInitCommand(
  options: InitCommandOptions = {},
): Promise<void> {
  const repoRoot = resolveRepoRoot(options.repo);

  try {
    await ensureOutputDirs(repoRoot);

    const { repoContext, fileIndex, importantFiles } =
      await buildRepoContextArtifacts(repoRoot);

    await writeJson(getRepoContextPath(repoRoot), repoContext);
    await writeJson(getFileIndexPath(repoRoot), fileIndex);

    const generatedDocs = await generateDocs({
      repoContext,
      fileIndex,
      importantFiles,
    });

    await writeGeneratedDocs({
      repoRoot,
      generatedDocs,
    });

    const agentsMarkdown = renderAgentsMd({
      repoContext,
      agentRulesMarkdown: generatedDocs.agentRulesMarkdown,
    });

    await writeMarkdown(getAgentsGeneratedPath(repoRoot), agentsMarkdown);

    if (options.writeAgentsMd) {
      await upsertGeneratedMarkdownBlock({
        filePath: getAgentsMdPath(repoRoot),
        content: agentsMarkdown,
        startMarker: BRIDGER_GENERATED_START_MARKER,
        endMarker: BRIDGER_GENERATED_END_MARKER,
      });
    }

    const generatedFiles = getGeneratedFilePaths(repoRoot, Boolean(options.writeAgentsMd));
    const skippedFiles = options.writeAgentsMd
      ? [".bridger/generated/ticket-template.md not generated in this ticket."]
      : [
          "AGENTS.md unchanged. Run `bridger init --write-agents-md` to append/update the generated Bridger section.",
          ".bridger/generated/ticket-template.md not generated in this ticket.",
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
