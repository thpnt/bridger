import { ensureBridgerLayout } from "../project/ensure-bridger-layout";

export async function ensureOutputDirs(repoRoot: string): Promise<void> {
  await ensureBridgerLayout(repoRoot);
}
