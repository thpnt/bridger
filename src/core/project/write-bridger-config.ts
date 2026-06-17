import fs from "node:fs/promises";
import path from "node:path";

import { BridgerConfigSchema, type BridgerConfig } from "./bridger-config";
import { getBridgerConfigPath } from "./bridger-paths";

export async function writeBridgerConfig(
  repoRoot: string,
  config: BridgerConfig,
): Promise<void> {
  const parsedConfig = BridgerConfigSchema.parse(config);
  const configPath = getBridgerConfigPath(repoRoot);

  await fs.mkdir(path.dirname(configPath), { recursive: true });
  await fs.writeFile(
    configPath,
    `${JSON.stringify(parsedConfig, null, 2)}\n`,
    "utf8",
  );
}
