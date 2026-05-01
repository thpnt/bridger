import { z } from "zod";
import { RepoRelativePathSchema } from "./generated-paths";

export const SkillTriggerSchema = z.object({
  description: z.string(),
  examples: z.array(z.string()).default([]),
});

export const SkillInputSchema = z.object({
  name: z.string(),
  description: z.string(),
  required: z.boolean().default(false),
});

export const SkillOutputSchema = z.object({
  name: z.string(),
  description: z.string(),
});

export const SkillStepSchema = z.object({
  title: z.string(),
  instruction: z.string(),
  filesToInspect: z.array(RepoRelativePathSchema).default([]),
  commandsToRun: z.array(z.string()).default([]),
  expectedOutcome: z.string().optional(),
});

export const SkillGuardrailSchema = z.object({
  rule: z.string(),
  reason: z.string(),
});

export const GeneratedSkillFileSchema = z.object({
  path: RepoRelativePathSchema,
  purpose: z.string(),
  content: z.string(),
});

export const GeneratedSkillSchema = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),

  targetUseCase: z.string(),

  triggers: z.array(SkillTriggerSchema),

  inputs: z.array(SkillInputSchema).default([]),
  outputs: z.array(SkillOutputSchema).default([]),

  repoContext: z.array(z.string()).default([]),

  relevantFiles: z
    .array(
      z.object({
        path: RepoRelativePathSchema,
        reason: z.string(),
      }),
    )
    .default([]),

  steps: z.array(SkillStepSchema),

  guardrails: z.array(SkillGuardrailSchema).default([]),

  verification: z.object({
    commands: z.array(z.string()).default([]),
    manualChecks: z.array(z.string()).default([]),
  }),

  files: z.array(GeneratedSkillFileSchema),
});

export const SkillGenerationRequestSchema = z.object({
  sourceRequest: z.string(),
  repoRoot: z.string(),
  generatedAt: z.string().datetime(),
  maxSkills: z.number().int().min(1).max(10).default(3),
});

export const SkillGenerationPlanSchema = z.object({
  sourceRequest: z.string(),
  generatedAt: z.string().datetime(),

  summary: z.string(),

  recommendedSkills: z.array(
    z.object({
      slug: z.string(),
      title: z.string(),
      description: z.string(),
      reason: z.string(),
      priority: z.enum(["low", "medium", "high"]),
      targetPath: RepoRelativePathSchema,
    }),
  ),

  assumptions: z.array(z.string()).default([]),
  missingQuestions: z.array(z.string()).default([]),
});

export const SkillMetadataSchema = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  targetUseCase: z.string(),
  generatedAt: z.string().datetime(),
  sourceRequest: z.string(),
  relevantFiles: z.array(
    z.object({
      path: RepoRelativePathSchema,
      reason: z.string(),
    }),
  ),
});

export type SkillMetadata = z.infer<typeof SkillMetadataSchema>;
export type SkillGenerationRequest = z.infer<
  typeof SkillGenerationRequestSchema
>;
export type SkillGenerationPlan = z.infer<typeof SkillGenerationPlanSchema>;
export type SkillTrigger = z.infer<typeof SkillTriggerSchema>;
export type SkillInput = z.infer<typeof SkillInputSchema>;
export type SkillOutput = z.infer<typeof SkillOutputSchema>;
export type SkillStep = z.infer<typeof SkillStepSchema>;
export type SkillGuardrail = z.infer<typeof SkillGuardrailSchema>;
export type GeneratedSkillFile = z.infer<typeof GeneratedSkillFileSchema>;
export type GeneratedSkill = z.infer<typeof GeneratedSkillSchema>;
