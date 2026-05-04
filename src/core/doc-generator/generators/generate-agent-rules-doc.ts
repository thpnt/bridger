import { buildAgentRulesPrompt } from "../../llm/prompts/docs/agent-rules-prompt";
import {
  GenerateAgentRulesDocInputSchema,
  type GenerateAgentRulesDocInput,
} from "../../models/agent-rules-doc";
import { KNOWLEDGE_DOC_SPECS } from "../doc-specs";
import { generateKnowledgeDoc } from "./generate-knowledge-doc";

export async function generateAgentRulesDoc(
  input: GenerateAgentRulesDocInput,
): Promise<string> {
  const parsedInput = GenerateAgentRulesDocInputSchema.parse(input);
  return generateKnowledgeDoc({
    spec: KNOWLEDGE_DOC_SPECS.agentRules,
    generationInput: parsedInput,
    buildPrompt: buildAgentRulesPrompt,
  });
}
