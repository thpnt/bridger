import { writeJson } from "../output/write-json";
import { getReadingPlansPath } from "../project/bridger-paths";
import {
  ReadingPlansSchema,
  type ReadingPlans,
} from "./models/reading-plans";

export async function writeReadingPlansArtifact(input: {
  repoRoot: string;
  readingPlans: ReadingPlans;
}): Promise<string> {
  const outputPath = getReadingPlansPath(input.repoRoot);
  await writeJson(outputPath, ReadingPlansSchema.parse(input.readingPlans));
  return outputPath;
}
