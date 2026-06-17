import { z } from "zod";

export const BridgerProjectModeSchema = z.enum([
  "fresh",
  "existing",
  "unknown",
]);

export type BridgerProjectMode = z.infer<typeof BridgerProjectModeSchema>;

export const BridgerConfigSchema = z.object({
  schemaVersion: z.literal(1),
  project: z.object({
    name: z.string().min(1),
    mode: BridgerProjectModeSchema,
  }),
  detected: z.object({
    packageManager: z.string().optional(),
    stack: z.array(z.string()).default([]),
  }),
  paths: z.object({
    memoryDir: z.literal(".bridger/memory"),
    artifactsDir: z.literal(".bridger/artifacts"),
    skillsDir: z.literal(".bridger/skills"),
    templatesDir: z.literal(".bridger/templates"),
    exportsDir: z.literal(".bridger/exports"),
  }),
  memory: z.object({
    schemaVersion: z.literal(1),
    files: z.array(z.string()).default([
      "repo-analysis.md",
      "architecture.md",
      "business-logic.md",
      "conventions.md",
      "testing.md",
      "agent-rules.md",
    ]),
  }),
  artifacts: z.object({
    schemaVersion: z.literal(1),
  }),
  skills: z.object({
    selected: z.array(z.string()).default([]),
  }),
  exports: z.object({
    agentsMd: z.object({
      enabled: z.boolean().default(true),
      generatedPath: z.literal(".bridger/exports/AGENTS.generated.md"),
      rootPath: z.literal("AGENTS.md"),
      writeRootFile: z.boolean().default(false),
    }),
    claudeMd: z.object({
      enabled: z.boolean().default(false),
      generatedPath: z.literal(".bridger/exports/CLAUDE.generated.md"),
      rootPath: z.literal("CLAUDE.md"),
      writeRootFile: z.boolean().default(false),
    }),
  }),
  llm: z.object({
    provider: z.enum(["none", "openai", "bridger-sponsored"]).default("none"),
    modelProfile: z.enum(["cheap", "balanced", "quality"]).default("balanced"),
  }),
  timestamps: z.object({
    initializedAt: z.string(),
    lastInitAt: z.string().optional(),
    lastUpdateAt: z.string().optional(),
  }),
});

export type BridgerConfig = z.infer<typeof BridgerConfigSchema>;
