import path from "node:path";

import {
  BridgerConfigSchema,
  type BridgerConfig,
  type BridgerProjectMode,
} from "./bridger-config";

export interface CreateBridgerConfigInput {
  repoRoot: string;
  mode: BridgerProjectMode;
  projectName?: string;
  detectedStack?: string[];
  packageManager?: string;
  now?: Date;
  writeRootAgentsFile?: boolean;
}

export function createBridgerConfig(
  input: CreateBridgerConfigInput,
): BridgerConfig {
  const now = input.now ?? new Date();
  const timestamp = now.toISOString();
  const projectName = input.projectName ?? path.basename(input.repoRoot);

  return BridgerConfigSchema.parse({
    schemaVersion: 1,
    project: {
      name: projectName,
      mode: input.mode,
    },
    detected: {
      packageManager: input.packageManager,
      stack: input.detectedStack ?? [],
    },
    paths: {
      memoryDir: ".bridger/memory",
      artifactsDir: ".bridger/artifacts",
      skillsDir: ".bridger/skills",
      templatesDir: ".bridger/templates",
      exportsDir: ".bridger/exports",
    },
    memory: {
      schemaVersion: 1,
    },
    artifacts: {
      schemaVersion: 1,
    },
    skills: {
      selected: [],
    },
    exports: {
      agentsMd: {
        enabled: true,
        generatedPath: ".bridger/exports/AGENTS.generated.md",
        rootPath: "AGENTS.md",
        writeRootFile: input.writeRootAgentsFile ?? false,
      },
      claudeMd: {
        enabled: false,
        generatedPath: ".bridger/exports/CLAUDE.generated.md",
        rootPath: "CLAUDE.md",
        writeRootFile: false,
      },
    },
    llm: {
      provider: "none",
      modelProfile: "balanced",
    },
    timestamps: {
      initializedAt: timestamp,
      lastInitAt: timestamp,
    },
  });
}
