import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { ImportantFile } from "../../../models/important-file";
import type {
  RepoContextCommands,
  RepoContextImportantFile,
  RepoContextStack,
} from "../../../models/repo-context";
import type { GenerateAgentRulesDocInput } from "../../../models/agent-rules-doc";
import { GenerateAgentRulesDocInputSchema } from "../../../models/agent-rules-doc";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";

export function formatBulletList(
  items: readonly string[],
  emptyFallback = "- Unknown",
): string {
  if (items.length === 0) {
    return emptyFallback;
  }

  return items.map((item) => `- ${item}`).join("\n");
}

export function formatKeyValueLines(
  entries: Record<string, string | undefined | null>,
): string {
  const lines: string[] = [];

  for (const [key, value] of Object.entries(entries)) {
    const normalizedValue = normalizeText(value);
    lines.push(`${key}: ${normalizedValue ?? "unknown"}`);
  }

  return formatBulletList(lines);
}

export function formatStringArrayValue(
  values: readonly string[] | undefined,
  emptyFallback = "unknown",
): string {
  const normalizedValues =
    values?.map((value) => value.trim()).filter((value) => value.length > 0) ??
    [];

  if (normalizedValues.length === 0) {
    return emptyFallback;
  }

  return normalizedValues.join(", ");
}

export function formatDetectedStack(stack: RepoContextStack): string {
  return formatKeyValueLines({
    Framework: stack.framework,
    Language: stack.language,
    "Package manager": stack.packageManager,
    Styling: formatStringArrayValue(stack.styling),
    Validation: formatStringArrayValue(stack.validation),
    Database: formatStringArrayValue(stack.database),
    Testing: formatStringArrayValue(stack.testFramework),
  });
}

export function formatCommands(commands: RepoContextCommands): string {
  const lines: string[] = [];
  const orderedEntries: Array<[string, string | undefined]> = [
    ["install", commands.install],
    ["dev", commands.dev],
    ["build", commands.build],
    ["lint", commands.lint],
    ["typecheck", commands.typecheck],
    ["test", commands.test],
    ["format", commands.format],
  ];

  for (const [name, value] of orderedEntries) {
    const normalizedValue = normalizeText(value);

    if (!normalizedValue) {
      continue;
    }

    lines.push(`${name}: ${normalizedValue}`);
  }

  return formatBulletList(lines);
}

export function formatImportantFiles(
  files: readonly (ImportantFile | RepoContextImportantFile)[],
): string {
  if (files.length === 0) {
    return "none";
  }

  return files
    .map((file) => {
      const lines = [`--- FILE: ${file.path}`, `Reason: ${file.reason}`];

      if ("content" in file && normalizeText(file.content)) {
        lines.push(file.content);
      }

      lines.push("--- END FILE");

      return lines.join("\n");
    })
    .join("\n\n");
}

export function formatFileIndexSummary(
  fileIndexSummary: string | undefined,
): string {
  const normalizedSummary = normalizeText(fileIndexSummary);

  if (!normalizedSummary) {
    return "No file index summary provided.";
  }

  return normalizedSummary;
}

export function formatGroundingRules(): string {
  return formatBulletList([
    "Use only the provided repo context, file index summary, important files, and generated docs included in the prompt.",
    "Do not invent architecture, commands, dependencies, folders, workflows, conventions, integrations, or business behavior.",
    "Treat source files and selected excerpts as stronger evidence than README/docs when they conflict.",
    "When evidence is weak, use cautious language and preserve the uncertainty instead of guessing.",
    "Prefer synthesized, practical guidance over evidence logs, file inventories, or generic filler.",
  ]);
}

export function formatUnknownsRule(): string {
  return "If information is missing or weakly supported, state the uncertainty clearly instead of guessing.";
}

export function formatMarkdownOutputRules(): string {
  return formatBulletList([
    "Return Markdown only.",
    "Use simple headings to make the document easy to scan.",
    "Keep the document concise, practical, and human-readable.",
    "Avoid decorative formatting, excessive bullets, and evidence-log style output.",
    "Do not wrap the full answer in a code block.",
    "Do not include JSON.",
  ]);
}

export function formatRequiredSections(sections: readonly string[]): string {
  return formatBulletList([...sections]);
}

export function formatKnowledgeDocContext(
  input: KnowledgeDocGenerationInput,
): string {
  return [
    "## Repo root",
    input.repoContext.repoRoot,
    "",
    "## Generated at",
    input.repoContext.generatedAt,
    "",
    "## Detected stack",
    formatDetectedStack(input.repoContext.stack),
    "",
    "## Commands",
    formatCommands(input.repoContext.commands),
    "",
    "## File index summary",
    formatFileIndexSummary(input.fileIndexSummary),
    "",
    "## Important files",
    formatImportantFiles(input.importantFiles),
  ].join("\n");
}

export const formatImportantFilesForPrompt = formatImportantFiles;

function normalizeText(value: string | undefined | null): string | undefined {
  const normalizedValue = value?.trim();

  if (!normalizedValue) {
    return undefined;
  }

  return normalizedValue;
}

function formatRepoContext(
  repoContext: GenerateAgentRulesDocInput["repoContext"],
): string {
  return [
    "## Repo root",
    repoContext.repoRoot,
    "",
    "## Generated at",
    repoContext.generatedAt,
    "",
    "## Detected stack",
    formatDetectedStack(repoContext.stack),
    "",
    "## Commands",
    formatCommands(repoContext.commands),
    "",
    "## Important files",
    formatImportantFiles(repoContext.importantFiles),
  ].join("\n");
}

function formatGeneratedDocs(
  generatedDocs: GenerateAgentRulesDocInput["generatedDocs"],
): string {
  return [
    `## ${KNOWLEDGE_DOC_SPECS.repoAnalysis.filename}`,
    generatedDocs.repoAnalysis,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.architecture.filename}`,
    generatedDocs.architecture,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.conventions.filename}`,
    generatedDocs.conventions,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.businessLogic.filename}`,
    generatedDocs.businessLogic,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.testing.filename}`,
    generatedDocs.testing,
  ].join("\n");
}
