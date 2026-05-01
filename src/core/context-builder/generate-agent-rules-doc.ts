import { generateText } from "../llm/client";
import { buildAgentRulesPrompt } from "../llm/prompts/agent-rules-prompt";
import {
  GenerateAgentRulesDocInputSchema,
  type GenerateAgentRulesDocInput,
} from "../models/agent-rules-doc";
import { assertMarkdownSections } from "./markdown-section-validation";

export const REQUIRED_AGENT_RULES_SECTIONS = [
  "## Project overview",
  "## Commands",
  "## Rules for agents",
  "## Coding conventions",
  "## Business logic boundaries",
  "## Testing expectations",
  "## Risky areas",
  "## Task scoping rules",
  "## Files/folders to avoid unless explicitly requested",
  "## Unknowns",
] as const;

export async function generateAgentRulesDoc(
  input: GenerateAgentRulesDocInput,
): Promise<string> {
  const parsedInput = GenerateAgentRulesDocInputSchema.parse(input);
  const { system, prompt } = buildAgentRulesPrompt(parsedInput);
  const markdown = await generateText({
    system,
    prompt,
  });

  assertAgentRulesDoc(markdown);

  return markdown;
}

export function assertAgentRulesDoc(markdown: string): void {
  assertMarkdownSections({
    markdown,
    requiredSections: REQUIRED_AGENT_RULES_SECTIONS,
    documentName: "Agent rules doc",
  });
}
