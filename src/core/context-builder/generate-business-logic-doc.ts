import { generateText } from "../llm/client";
import { buildBusinessLogicPrompt } from "../llm/prompts/business-logic-prompt";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
} from "../models/repo-knowledge-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_BUSINESS_LOGIC_SECTIONS = [
  "## Product/domain overview",
  "## Observed domain concepts",
  "## Observed entities and models",
  "## Observed business rules",
  "## Observed workflows",
  "## Data ownership and persistence",
  "## External integrations",
  "## Assumptions",
  "## Unknowns",
  "## Evidence map",
] as const;

export async function generateBusinessLogicDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const { system, prompt } = buildBusinessLogicPrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertBusinessLogicDoc(markdown);

  return markdown;
}

export function assertBusinessLogicDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_BUSINESS_LOGIC_SECTIONS,
    documentName: "Business logic doc",
  });
}
