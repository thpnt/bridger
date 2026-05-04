export interface KnowledgeDocPrompt {
  system: string;
  prompt: string;
}

export type BuildKnowledgeDocPrompt<TInput> = (input: TInput) => KnowledgeDocPrompt;
