import { detectCommands } from "../../core/repo-scanner/detect-commands";
import { detectStack } from "../../core/repo-scanner/detect-stack";
import { buildFileIndex } from "../../core/repo-scanner/build-file-index";
import { logger } from "../../core/utils/logger";
import { resolveRepoRoot } from "../../core/utils/paths";
import type { RepoContextCommands, RepoContextStack } from "../../core/models/repo-context";
import { Command } from "commander";

export interface InspectOptions {
  repo?: string;
}

interface InspectSummaryInput {
  repoRoot: string;
  stack: RepoContextStack;
  commands: RepoContextCommands;
  indexedFileCount: number;
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

export async function runInspectCommand(options?: InspectOptions): Promise<void> {
  try {
    const repoRoot = resolveRepoRoot(options?.repo);
    const stack = await detectStack(repoRoot);
    const commands = await detectCommands(repoRoot, stack.packageManager);
    const fileIndex = await buildFileIndex(repoRoot);

    logger.info(
      formatInspectSummary({
        repoRoot,
        stack,
        commands,
        indexedFileCount: fileIndex.files.length,
      }),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logger.error(`Failed to inspect repository: ${message}`);
    process.exitCode = 1;
  }
}

export const inspectCommand = new Command("inspect")
  .description("Inspect the current repository without using the LLM")
  .option("--repo <path>", "Path to the repository to inspect")
  .action(async (options: InspectOptions) => {
    await runInspectCommand(options);
  });
