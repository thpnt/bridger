import { generateText } from "../../llm/client";
import type { KnowledgeDocSpec } from "../doc-types";
import { validateMarkdownSections } from "../validation/markdown-section-validation";
import type { BuildKnowledgeDocPrompt } from "../knowledge-doc-prompt";

export type GenerateKnowledgeDocInput<TInput> = {
  spec: KnowledgeDocSpec;
  generationInput: TInput;
  buildPrompt: BuildKnowledgeDocPrompt<TInput>;
};

export async function generateKnowledgeDoc<TInput>({
  spec,
  generationInput,
  buildPrompt,
}: GenerateKnowledgeDocInput<TInput>): Promise<string> {
  const { system, prompt } = buildPrompt(generationInput);
  const markdown = await generateText({
    system,
    prompt,
  });
  const trimmedMarkdown = markdown.trim();

  if (trimmedMarkdown.length === 0) {
    throw new Error(`${spec.displayName} generation returned empty Markdown.`);
  }

  //validateMarkdownSections({
  //  markdown: trimmedMarkdown,
  //  requiredSections: spec.requiredSections,
  //  documentName: spec.displayName,
  //});

  return trimmedMarkdown;
}
