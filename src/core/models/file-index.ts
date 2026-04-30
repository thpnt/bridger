import { z } from "zod";
import { AbsolutePathSchema, RepoRelativePathSchema } from "./paths";

export const FileIndexEntrySchema = z.object({
  path: RepoRelativePathSchema,
  extension: z.string().optional(),
  sizeBytes: z.number(),
  reason: z.string().optional(),
  tags: z.array(z.string()),
});

export const FileIndexSchema = z.object({
  generatedAt: z.iso.datetime(),
  files: z.array(FileIndexEntrySchema),
});

export type FileIndexEntry = z.infer<typeof FileIndexEntrySchema>;
export type FileIndex = z.infer<typeof FileIndexSchema>;
