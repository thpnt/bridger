import { buildRepoContextArtifacts } from "../../core/context-builder/build-repo-context";
import { buildGraphSummary } from "../../core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../core/repo-graph/build-repo-graph";
import type { GraphSummary, GraphSummaryRankedFile } from "../../core/repo-graph/models/graph-summary";
import type { RepoGraph } from "../../core/repo-graph/models/repo-graph";
import { buildFileIndex } from "../../core/repo-scanner/build-file-index";
import { logger } from "../../shared/logger";
import { resolveRepoRoot } from "../../core/utils/paths";
import type { FileIndex, FileIndexEntry } from "../../core/models/file-index";
import type {
  RepoContext,
  RepoContextCommands,
  RepoContextStack,
} from "../../core/models/repo-context";
import { Command } from "commander";

export interface InspectCommandOptions {
  repo?: string;
  context?: boolean;
  importantFiles?: boolean;
  graph?: boolean;
  json?: boolean;
}

interface InspectSummaryInput {
  repoRoot: string;
  stack: RepoContextStack;
  commands: RepoContextCommands;
  indexedFileCount: number;
}

export interface ImportantFileInspection {
  path: string;
  reason: string;
  sizeBytes?: number;
  tags?: string[];
}

export interface InspectResult {
  repoContext: RepoContext;
  fileIndex: FileIndex;
  inspection: {
    indexedFileCount: number;
    importantFileCount: number;
    estimatedImportantFilesSizeBytes?: number;
    importantFiles: ImportantFileInspection[];
  };
}

const COMMAND_ORDER = [
  "install",
  "dev",
  "build",
  "lint",
  "typecheck",
  "test",
  "format",
] as const;

function formatList(values: string[]): string {
  return values.length > 0 ? values.join(", ") : "none";
}

function formatCommandValue(value: string | undefined): string {
  return value !== undefined ? value : "none";
}

export function formatBytes(bytes: number | undefined): string {
  if (bytes === undefined) {
    return "unknown";
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const units = ["KB", "MB", "GB"] as const;
  let value = bytes / 1024;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function buildImportantFileInspection(
  importantFile: RepoContext["importantFiles"][number],
  fileByPath: Map<string, FileIndexEntry>,
): ImportantFileInspection {
  const indexedFile = fileByPath.get(importantFile.path);

  return {
    path: importantFile.path,
    reason: importantFile.reason,
    sizeBytes: indexedFile?.sizeBytes,
    tags: indexedFile?.tags,
  };
}

export async function buildInspectResult(
  repoRoot: string,
): Promise<InspectResult> {
  const { repoContext, fileIndex } = await buildRepoContextArtifacts(repoRoot);
  const fileByPath = new Map(fileIndex.files.map((file) => [file.path, file]));

  const importantFiles = repoContext.importantFiles.map((importantFile) =>
    buildImportantFileInspection(importantFile, fileByPath),
  );

  const estimatedImportantFilesSizeBytes = importantFiles.reduce((total, file) => {
    return total + (file.sizeBytes ?? 0);
  }, 0);

  return {
    repoContext,
    fileIndex,
    inspection: {
      indexedFileCount: fileIndex.files.length,
      importantFileCount: importantFiles.length,
      estimatedImportantFilesSizeBytes,
      importantFiles,
    },
  };
}

export function formatInspectSummary(input: InspectSummaryInput): string {
  const lines: string[] = [
    "bridger Inspect",
    "",
    `Repo: ${input.repoRoot}`,
    `Framework: ${input.stack.framework || "unknown"}`,
    `Language: ${input.stack.language || "unknown"}`,
    `Package manager: ${input.stack.packageManager || "unknown"}`,
    `Styling: ${formatList(input.stack.styling)}`,
    `Validation: ${formatList(input.stack.validation)}`,
    `Database: ${formatList(input.stack.database)}`,
    `Testing: ${formatList(input.stack.testFramework)}`,
    "",
    "Commands:",
  ];

  const commandLines: string[] = [];

  for (const commandName of COMMAND_ORDER) {
    const value = input.commands[commandName];

    if (value !== undefined) {
      commandLines.push(`- ${commandName}: ${formatCommandValue(value)}`);
    }
  }

  if (commandLines.length === 0) {
    lines.push("- none");
  } else {
    lines.push(...commandLines);
  }

  lines.push("");
  lines.push(`Indexed files: ${input.indexedFileCount}`);

  return lines.join("\n");
}

export function formatGraphInspectOutput(input: {
  graph: RepoGraph;
  summary: GraphSummary;
}): string {
  const { graph, summary } = input;

  return [
    "Repo graph",
    "",
    "Stats",
    `- Files: ${graph.stats.fileCount}`,
    `- Directories: ${graph.stats.directoryCount}`,
    `- Contains edges: ${graph.stats.containsEdgeCount}`,
    `- Import edges: ${graph.stats.importEdgeCount}`,
    `- Unresolved imports: ${graph.stats.unresolvedImportCount}`,
    `- Supported language files: ${graph.stats.supportedLanguageFileCount}`,
    `- Diagnostics: ${graph.diagnostics.length}`,
    "",
    "Entrypoint candidates",
    formatPathList(summary.entrypoints),
    "",
    "Top high fan-in files",
    formatRankedFiles(summary.highFanInFiles, "incoming"),
    "",
    "Top high fan-out files",
    formatRankedFiles(summary.highFanOutFiles, "outgoing"),
    "",
    "Architecture-first order preview",
    formatOrderedPreview(summary.architectureFirstOrder.slice(0, 10)),
  ].join("\n");
}

function formatPathList(paths: string[]): string {
  if (paths.length === 0) {
    return "- None";
  }

  return paths.map((path) => `- ${path}`).join("\n");
}

function formatRankedFiles(
  files: GraphSummaryRankedFile[],
  label: "incoming" | "outgoing",
): string {
  if (files.length === 0) {
    return "- None";
  }

  return files
    .slice(0, 10)
    .map(
      (file) =>
        `- ${file.path} - ${file.count} ${label} import${file.count === 1 ? "" : "s"}`,
    )
    .join("\n");
}

function formatOrderedPreview(paths: string[]): string {
  if (paths.length === 0) {
    return "- None";
  }

  return paths.map((path, index) => `${index + 1}. ${path}`).join("\n");
}

function formatImportantFileInspectionLines(
  importantFile: ImportantFileInspection,
): string[] {
  const lines = [`- ${importantFile.path}`, `  Reason: ${importantFile.reason}`];

  if (importantFile.sizeBytes !== undefined) {
    lines.push(`  Size: ${formatBytes(importantFile.sizeBytes)}`);
  }

  return lines;
}

function formatImportantFileList(result: InspectResult): string {
  if (result.inspection.importantFiles.length === 0) {
    return "- none";
  }

  const lines: string[] = [];

  for (const importantFile of result.inspection.importantFiles) {
    lines.push(...formatImportantFileInspectionLines(importantFile));
    lines.push("");
  }

  lines.pop();

  return lines.join("\n");
}

function formatImportantFilesSection(result: InspectResult): string {
  return [
    `Important files: ${result.inspection.importantFileCount}`,
    "",
    formatImportantFileList(result),
  ].join("\n");
}

function formatContextPreview(result: InspectResult): string {
  const estimatedSelectedContextSize =
    result.inspection.estimatedImportantFilesSizeBytes !== undefined
      ? formatBytes(result.inspection.estimatedImportantFilesSizeBytes)
      : "unknown";

  return [
    "Context preview",
    "",
    `Indexed files: ${result.inspection.indexedFileCount}`,
    `Important files: ${result.inspection.importantFileCount}`,
    `Estimated selected context size: ${estimatedSelectedContextSize}`,
    "",
    "Important files:",
    "",
    formatImportantFileList(result),
  ].join("\n");
}

function printSummary(result: InspectResult): void {
  logger.info(
    formatInspectSummary({
      repoRoot: result.repoContext.repoRoot,
      stack: result.repoContext.stack,
      commands: result.repoContext.commands,
      indexedFileCount: result.inspection.indexedFileCount,
    }),
  );
}

function printImportantFiles(result: InspectResult): void {
  logger.info(formatImportantFilesSection(result));
}

function printContextPreview(result: InspectResult): void {
  logger.info(formatContextPreview(result));
}

async function buildGraphInspectArtifacts(repoRoot: string): Promise<{
  graph: RepoGraph;
  summary: GraphSummary;
}> {
  const fileIndex = await buildFileIndex(repoRoot);
  const graph = await buildRepoGraph({
    repoRoot,
    fileIndex,
  });
  const summary = buildGraphSummary(graph);

  return {
    graph,
    summary,
  };
}

function printGraphInspectOutput(input: {
  graph: RepoGraph;
  summary: GraphSummary;
}): void {
  logger.info(formatGraphInspectOutput(input));
}

export async function runInspectCommand(
  options?: InspectCommandOptions,
): Promise<void> {
  try {
    const repoRoot = resolveRepoRoot(options?.repo);

    if (options?.graph) {
      const graphResult = await buildGraphInspectArtifacts(repoRoot);

      printGraphInspectOutput(graphResult);
      return;
    }

    const result = await buildInspectResult(repoRoot);

    if (options?.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }

    printSummary(result);

    if (options?.context) {
      printContextPreview(result);
      return;
    }

    if (options?.importantFiles) {
      printImportantFiles(result);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logger.error(`Failed to inspect repository: ${message}`);
    process.exitCode = 1;
  }
}

export const inspectCommand = new Command("inspect")
  .description("Inspect the current repository without using the LLM")
  .option("--repo <path>", "Path to the repository to inspect")
  .option("--context", "Show deterministic context preview before LLM generation")
  .option("--important-files", "Show selected important files and selection reasons")
  .option("--graph", "Print repo graph inspection output")
  .option("--json", "Print inspect result as JSON")
  .action(async (options: InspectCommandOptions) => {
    await runInspectCommand(options);
  });
