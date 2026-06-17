import fs from "node:fs/promises";

import { Command } from "commander";

import { buildRepoContextArtifacts } from "../../core/context-builder/build-repo-context";
import {
  getAgentsGeneratedExportPath,
  getArtifactsDir,
  getBridgerConfigPath,
  getClaudeGeneratedExportPath,
  getCodebaseMapPath,
  getExportsDir,
  getFileIndexPath,
  getGeneratedKnowledgeDocPath,
  getGraphSummaryPath,
  getMemoryDir,
  getReadingPlansPath,
  getRepoContextPath,
  getRepoGraphPath,
  getRootAgentsPath,
  getSelectedSkillsPath,
  getSkillsDir,
  getTemplatesDir,
  getTicketTemplatePath,
} from "../../core/project/bridger-paths";
import {
  loadBridgerProject,
  type LoadBridgerProjectResult,
} from "../../core/project/load-bridger-project";
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
  projectState: ProjectStateInspection;
  inspection: {
    indexedFileCount: number;
    importantFileCount: number;
    estimatedImportantFilesSizeBytes?: number;
    importantFiles: ImportantFileInspection[];
  };
}

export interface ProjectStateInspection {
  status: LoadBridgerProjectResult["status"];
  reason?: string;
  message?: string;
  configPath: string;
  projectName?: string;
  projectMode?: string;
  detectedStack?: string[];
  packageManager?: string;
  artifactsDir: string;
  memoryDir: string;
  skillsDir: string;
  templatesDir: string;
  exportsDir: string;
  artifactFiles: CanonicalFileInspection[];
  memoryFiles: CanonicalFileInspection[];
  supportFiles: CanonicalFileInspection[];
  exists: {
    config: boolean;
    artifactsDir: boolean;
    memoryDir: boolean;
    skillsDir: boolean;
    templatesDir: boolean;
    exportsDir: boolean;
  };
}

export interface CanonicalFileInspection {
  label: string;
  path: string;
  exists: boolean;
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
  const projectState = await buildProjectStateInspection(repoRoot);
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
    projectState,
    inspection: {
      indexedFileCount: fileIndex.files.length,
      importantFileCount: importantFiles.length,
      estimatedImportantFilesSizeBytes,
      importantFiles,
    },
  };
}

async function buildProjectStateInspection(
  repoRoot: string,
): Promise<ProjectStateInspection> {
  const project = await loadBridgerProject(repoRoot);
  const configPath = getBridgerConfigPath(repoRoot);
  const artifactsDir = getArtifactsDir(repoRoot);
  const memoryDir = getMemoryDir(repoRoot);
  const skillsDir = getSkillsDir(repoRoot);
  const templatesDir = getTemplatesDir(repoRoot);
  const exportsDir = getExportsDir(repoRoot);
  const artifactFiles = await buildFileInspections([
    ["file-index.json", getFileIndexPath(repoRoot)],
    ["repo-context.json", getRepoContextPath(repoRoot)],
    ["repo-graph.json", getRepoGraphPath(repoRoot)],
    ["graph-summary.json", getGraphSummaryPath(repoRoot)],
    ["codebase-map.json", getCodebaseMapPath(repoRoot)],
    ["reading-plans.json", getReadingPlansPath(repoRoot)],
  ]);
  const memoryFiles = await buildFileInspections([
    ["repo-analysis.md", getGeneratedKnowledgeDocPath(repoRoot, "repoAnalysis")],
    ["architecture.md", getGeneratedKnowledgeDocPath(repoRoot, "architecture")],
    ["business-logic.md", getGeneratedKnowledgeDocPath(repoRoot, "businessLogic")],
    ["conventions.md", getGeneratedKnowledgeDocPath(repoRoot, "conventions")],
    ["testing.md", getGeneratedKnowledgeDocPath(repoRoot, "testing")],
    ["agent-rules.md", getGeneratedKnowledgeDocPath(repoRoot, "agentRules")],
  ]);
  const supportFiles = await buildFileInspections([
    ["selected-skills.json", getSelectedSkillsPath(repoRoot)],
    ["ticket-template.md", getTicketTemplatePath(repoRoot)],
    ["AGENTS.generated.md", getAgentsGeneratedExportPath(repoRoot)],
    ["CLAUDE.generated.md", getClaudeGeneratedExportPath(repoRoot)],
    ["root AGENTS.md", getRootAgentsPath(repoRoot)],
  ]);

  return {
    status: project.status,
    reason: project.status === "initialized" ? undefined : project.reason,
    message: project.status === "invalid" ? project.message : undefined,
    configPath,
    projectName:
      project.status === "initialized" ? project.config.project.name : undefined,
    projectMode:
      project.status === "initialized" ? project.config.project.mode : undefined,
    detectedStack:
      project.status === "initialized" ? project.config.detected.stack : undefined,
    packageManager:
      project.status === "initialized"
        ? project.config.detected.packageManager
        : undefined,
    artifactsDir,
    memoryDir,
    skillsDir,
    templatesDir,
    exportsDir,
    artifactFiles,
    memoryFiles,
    supportFiles,
    exists: {
      config: await pathExists(configPath),
      artifactsDir: await pathExists(artifactsDir),
      memoryDir: await pathExists(memoryDir),
      skillsDir: await pathExists(skillsDir),
      templatesDir: await pathExists(templatesDir),
      exportsDir: await pathExists(exportsDir),
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

function formatProjectStateSection(projectState: ProjectStateInspection): string {
  const lines = [
    "Project state:",
    `- Status: ${projectState.status}`,
    `- Config: ${projectState.configPath} (${formatExists(projectState.exists.config)})`,
    `- Artifacts dir: ${projectState.artifactsDir} (${formatExists(projectState.exists.artifactsDir)})`,
    `- Memory dir: ${projectState.memoryDir} (${formatExists(projectState.exists.memoryDir)})`,
    `- Skills dir: ${projectState.skillsDir} (${formatExists(projectState.exists.skillsDir)})`,
    `- Templates dir: ${projectState.templatesDir} (${formatExists(projectState.exists.templatesDir)})`,
    `- Exports dir: ${projectState.exportsDir} (${formatExists(projectState.exists.exportsDir)})`,
    "",
    "Canonical artifact files:",
    ...formatCanonicalFileLines(projectState.artifactFiles),
    "",
    "Canonical memory files:",
    ...formatCanonicalFileLines(projectState.memoryFiles),
    "",
    "Canonical skills/templates/exports:",
    ...formatCanonicalFileLines(projectState.supportFiles),
  ];

  if (projectState.packageManager !== undefined) {
    lines.splice(2, 0, `- Config package manager: ${projectState.packageManager}`);
  }

  if (projectState.detectedStack !== undefined) {
    lines.splice(2, 0, `- Config detected stack: ${formatList(projectState.detectedStack)}`);
  }

  if (projectState.projectMode !== undefined) {
    lines.splice(2, 0, `- Project mode: ${projectState.projectMode}`);
  }

  if (projectState.projectName !== undefined) {
    lines.splice(2, 0, `- Project name: ${projectState.projectName}`);
  }

  if (projectState.reason !== undefined) {
    lines.push(`- Reason: ${projectState.reason}`);
  }

  if (projectState.message !== undefined) {
    lines.push(`- Message: ${projectState.message}`);
  }

  return lines.join("\n");
}

function formatExists(exists: boolean): string {
  return exists ? "exists" : "missing";
}

function formatCanonicalFileLines(files: CanonicalFileInspection[]): string[] {
  return files.map((file) => `- ${file.label}: ${formatExists(file.exists)}`);
}

async function buildFileInspections(
  files: Array<[label: string, filePath: string]>,
): Promise<CanonicalFileInspection[]> {
  const inspections: CanonicalFileInspection[] = [];

  for (const [label, filePath] of files) {
    inspections.push({
      label,
      path: filePath,
      exists: await pathExists(filePath),
    });
  }

  return inspections;
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
    [
      formatInspectSummary({
        repoRoot: result.repoContext.repoRoot,
        stack: result.repoContext.stack,
        commands: result.repoContext.commands,
        indexedFileCount: result.inspection.indexedFileCount,
      }),
      "",
      formatProjectStateSection(result.projectState),
    ].join("\n"),
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
    console.error(`bridger inspect failed: ${message}`);
    process.exitCode = 1;
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
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
