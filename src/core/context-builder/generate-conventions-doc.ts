import { generateText } from "../llm/client";
import { buildConventionsPrompt } from "../llm/prompts/conventions-prompt";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
} from "../models/repo-knowledge-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_CONVENTIONS_SECTIONS = [
  "## TypeScript conventions",
  "## Component conventions",
  "## Server/client boundary conventions",
  "## Validation conventions",
  "## Styling conventions",
  "## Data access conventions",
  "## Testing conventions",
  "## Naming conventions",
  "## Observed conventions",
  "## Recommended conventions",
  "## Things agents should avoid",
  "## Unknowns",
] as const;

export async function generateConventionsDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const { system, prompt } = buildConventionsPrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertConventionsDoc(markdown);

  return markdown;
}

export function assertConventionsDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_CONVENTIONS_SECTIONS,
    documentName: "Conventions doc",
  });
}
