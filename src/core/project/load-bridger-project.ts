import fs from "node:fs/promises";

import type { BridgerConfig } from "./bridger-config";
import { getBridgerConfigPath, getBridgerDir } from "./bridger-paths";
import { readBridgerConfig } from "./read-bridger-config";

export type LoadBridgerProjectResult =
  | {
      status: "initialized";
      repoRoot: string;
      config: BridgerConfig;
    }
  | {
      status: "uninitialized";
      repoRoot: string;
      reason: "missing-bridger-dir" | "missing-config";
    }
  | {
      status: "invalid";
      repoRoot: string;
      reason: "invalid-config" | "unreadable-config";
      message: string;
    };

export async function loadBridgerProject(
  repoRoot: string,
): Promise<LoadBridgerProjectResult> {
  const bridgerDir = getBridgerDir(repoRoot);
  const configPath = getBridgerConfigPath(repoRoot);

  if (!(await pathExists(bridgerDir))) {
    return {
      status: "uninitialized",
      repoRoot,
      reason: "missing-bridger-dir",
    };
  }

  if (!(await pathExists(configPath))) {
    return {
      status: "uninitialized",
      repoRoot,
      reason: "missing-config",
    };
  }

  try {
    return {
      status: "initialized",
      repoRoot,
      config: await readBridgerConfig(repoRoot),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);

    return {
      status: "invalid",
      repoRoot,
      reason: error instanceof SyntaxError ? "invalid-config" : "unreadable-config",
      message,
    };
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}
