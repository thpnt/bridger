import { z } from "zod";
import { AbsolutePathSchema, RepoRelativePathSchema } from "./generated-paths";

export const ConfigSchema = z.object({
  repoRoot: AbsolutePathSchema,
  generatedDir: RepoRelativePathSchema,
  ticketsDir: RepoRelativePathSchema,
});

export type Config = z.infer<typeof ConfigSchema>;
