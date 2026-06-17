import { writeJson } from "../output/write-json";
import { getCodebaseMapPath } from "../project/bridger-paths";
import { CodebaseMapSchema, type CodebaseMap } from "./models/codebase-map";

export async function writeCodebaseMapArtifact(input: {
  repoRoot: string;
  codebaseMap: CodebaseMap;
}): Promise<string> {
  const outputPath = getCodebaseMapPath(input.repoRoot);
  await writeJson(outputPath, CodebaseMapSchema.parse(input.codebaseMap));
  return outputPath;
}
