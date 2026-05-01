import { generateText } from "../llm/client";
import { buildRepoAnalysisPrompt } from "../llm/prompts/repo-analysis-prompt";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
} from "../models/repo-knowledge-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_REPO_ANALYSIS_SECTIONS = [
  "## Project overview",
  "## Detected stack",
  "## File and folder evidence",
  "## Important files",
  "## Observed structure",
  "## Observed domains",
  "## Assumptions",
  "## Unknowns",
] as const;

export async function generateRepoAnalysisDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const { system, prompt } = buildRepoAnalysisPrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertRepoAnalysisDoc(markdown);

  return markdown;
}

export function assertRepoAnalysisDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_REPO_ANALYSIS_SECTIONS,
    documentName: "Repo analysis doc",
  });
}
