import { z } from "zod";

export const TicketSuggestedFileSchema = z.object({
  path: z.string(),
  reason: z.string(),
});

export const TicketAgentSuitabilitySchema = z.object({
  score: z.number().min(0).max(100),
  reason: z.string(),
});

export const EnrichedTicketSchema = z.object({
  title: z.string(),
  sourceRequest: z.string(),
  goal: z.string(),
  userImpact: z.string().optional(),
  currentBehavior: z.string().optional(),
  desiredBehavior: z.string(),
  repoContext: z.array(z.string()),
  acceptanceCriteria: z.array(z.string()),
  constraints: z.array(z.string()),
  suggestedFiles: z.array(TicketSuggestedFileSchema),
  testExpectations: z.array(z.string()),
  missingQuestions: z.array(z.string()),
  assumptions: z.array(z.string()),
  riskLevel: z.enum(["low", "medium", "high"]),
  agentSuitability: TicketAgentSuitabilitySchema,
  handoffPrompt: z.string(),
  supportingEvidence: z.array(
    z.object({
      path: z.string(),
      claim: z.string(),
      confidence: z.enum(["low", "medium", "high"]),
    }),
  ),
  metadata: z
    .object({
      slug: z.string(),
      createdAt: z.iso.datetime(),
      generatedBy: z.string().optional(),
    })
    .optional(),
});

export type TicketSuggestedFile = z.infer<typeof TicketSuggestedFileSchema>;
export type TicketAgentSuitability = z.infer<
  typeof TicketAgentSuitabilitySchema
>;
export type EnrichedTicket = z.infer<typeof EnrichedTicketSchema>;
