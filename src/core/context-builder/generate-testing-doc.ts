import { generateText } from "../llm/client";
import { buildTestingPrompt } from "../llm/prompts/testing-prompt";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
} from "../models/repo-knowledge-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_TESTING_SECTIONS = [
  "## Testing philosophy",
  "## Test types and when to use them",
  "## Unit testing conventions",
  "## Integration testing conventions",
  "## Regression testing conventions",
  "## Component and UI testing conventions",
  "## Manual QA expectations",
  "## Existing test evidence",
  "## Testing gaps and unknowns",
  "## Things agents should avoid",
] as const;

export async function generateTestingDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const { system, prompt } = buildTestingPrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertTestingDoc(markdown);

  return markdown;
}

export function assertTestingDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_TESTING_SECTIONS,
    documentName: "Testing doc",
  });
}
