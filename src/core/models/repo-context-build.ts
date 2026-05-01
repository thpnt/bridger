import { z } from "zod";

import { FileIndexSchema } from "./file-index";
import { RepoContextSchema } from "./repo-context";

export const RepoContextBuildArtifactsSchema = z.object({
  repoContext: RepoContextSchema,
  fileIndex: FileIndexSchema,
});

export type RepoContextBuildArtifacts = z.infer<
  typeof RepoContextBuildArtifactsSchema
>;
