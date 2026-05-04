import { buildTestingPrompt } from "../../llm/prompts/docs/testing-prompt";
import { buildKnowledgeDocGenerationInput } from "../knowledge-doc-input";
import { KNOWLEDGE_DOC_SPECS } from "../doc-specs";
import { generateKnowledgeDoc } from "./generate-knowledge-doc";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
} from "../../models/repo-knowledge-doc";

export async function generateTestingDoc(
  input: GenerateRepoKnowledgeDocInput,
): Promise<string> {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  return generateKnowledgeDoc({
    spec: KNOWLEDGE_DOC_SPECS.testing,
    generationInput: buildKnowledgeDocGenerationInput(parsedInput),
    buildPrompt: buildTestingPrompt,
  });
}
