import fs from "node:fs/promises";

import { BridgerConfigSchema, type BridgerConfig } from "./bridger-config";
import { getBridgerConfigPath } from "./bridger-paths";

export async function readBridgerConfig(
  repoRoot: string,
): Promise<BridgerConfig> {
  const configPath = getBridgerConfigPath(repoRoot);
  const rawConfig = await fs.readFile(configPath, "utf8");

  return BridgerConfigSchema.parse(JSON.parse(rawConfig));
}
