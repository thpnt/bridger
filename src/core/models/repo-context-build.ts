import { z } from "zod";

import { FileIndexSchema } from "./file-index";
import { ImportantFilesSchema } from "./important-file";
import { RepoContextSchema } from "./repo-context";

export const RepoContextBuildArtifactsSchema = z.object({
  repoContext: RepoContextSchema,
  fileIndex: FileIndexSchema,
  importantFiles: ImportantFilesSchema,
});

export type RepoContextBuildArtifacts = z.infer<
  typeof RepoContextBuildArtifactsSchema
>;
