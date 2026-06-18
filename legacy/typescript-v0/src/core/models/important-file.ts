import { z } from "zod";

export const ImportantFileSchema = z.object({
  path: z.string(),
  reason: z.string(),
  content: z.string(),
});

export const ImportantFilesSchema = z.array(ImportantFileSchema);

export type ImportantFile = z.infer<typeof ImportantFileSchema>;
