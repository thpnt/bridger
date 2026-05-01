import { generateText } from "../llm/client";
import { buildArchitecturePrompt } from "../llm/prompts/architecture-prompt";
import { GenerateRepoKnowledgeDocInputSchema } from "../models/repo-knowledge-doc";
import type { GenerateRepoKnowledgeDocInput } from "../models/repo-knowledge-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_ARCHITECTURE_SECTIONS = [
  "## Project overview",
  "## Detected stack",
  "## App structure",
  "## Core domains",
  "## Important folders",
  "## Data flow assumptions",
  "## Commands",
  "## Risky areas",
  "## Unknowns",
] as const;

export async function generateArchitectureDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const { system, prompt } = buildArchitecturePrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertArchitectureDoc(markdown);

  return markdown;
}

export function assertArchitectureDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_ARCHITECTURE_SECTIONS,
    documentName: "Architecture doc",
  });
}
