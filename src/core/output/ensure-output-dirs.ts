import fs from "node:fs/promises";

import { getBridgerDir, getGeneratedDir, getTicketsDir } from "../utils/paths";

export async function ensureOutputDirs(repoRoot: string): Promise<void> {
  await fs.mkdir(getBridgerDir(repoRoot), { recursive: true });
  await fs.mkdir(getGeneratedDir(repoRoot), { recursive: true });
  await fs.mkdir(getTicketsDir(repoRoot), { recursive: true });
}
