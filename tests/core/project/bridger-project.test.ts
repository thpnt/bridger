import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { BridgerConfigSchema } from "../../../src/core/project/bridger-config";
import { createBridgerConfig } from "../../../src/core/project/create-bridger-config";
import { ensureBridgerLayout } from "../../../src/core/project/ensure-bridger-layout";
import { loadBridgerProject } from "../../../src/core/project/load-bridger-project";
import {
  getArtifactsDir,
  getBridgerConfigPath,
  getBridgerIndexPath,
  getBridgerLogPath,
  getCodebaseMapPath,
  getMemoryFilePath,
  getReadingPlansPath,
  getSelectedSkillsPath,
  getTicketTemplatePath,
} from "../../../src/core/project/bridger-paths";
import { readBridgerConfig } from "../../../src/core/project/read-bridger-config";
import { writeBridgerConfig } from "../../../src/core/project/write-bridger-config";

let tempDir = "";

afterEach(async () => {
  if (tempDir.length > 0) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("bridger project paths", () => {
  it("builds canonical artifact and memory paths", async () => {
    const repoRoot = path.resolve("/repo");

    expect(getArtifactsDir(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts"),
    );
    expect(getCodebaseMapPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "codebase-map.json"),
    );
    expect(getReadingPlansPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "reading-plans.json"),
    );
    expect(getMemoryFilePath(repoRoot, "agent-rules.md")).toBe(
      path.join(repoRoot, ".bridger", "memory", "agent-rules.md"),
    );
  });
});

describe("bridger config", () => {
  it("creates a validated config with canonical relative path contracts", () => {
    const config = createBridgerConfig({
      repoRoot: "/work/demo",
      mode: "existing",
      detectedStack: ["Next.js", "TypeScript"],
      packageManager: "pnpm",
      now: new Date("2026-05-01T00:00:00.000Z"),
    });

    expect(BridgerConfigSchema.parse(config)).toEqual(config);
    expect(config.project).toEqual({
      name: "demo",
      mode: "existing",
    });
    expect(config.detected).toEqual({
      packageManager: "pnpm",
      stack: ["Next.js", "TypeScript"],
    });
    expect(config.paths).toEqual({
      memoryDir: ".bridger/memory",
      artifactsDir: ".bridger/artifacts",
      skillsDir: ".bridger/skills",
      templatesDir: ".bridger/templates",
      exportsDir: ".bridger/exports",
    });
    expect(config.exports.agentsMd.generatedPath).toBe(
      ".bridger/exports/AGENTS.generated.md",
    );
  });

  it("writes and reads config from the canonical path", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-project-"));
    const config = createBridgerConfig({
      repoRoot: tempDir,
      mode: "unknown",
      projectName: "custom",
      now: new Date("2026-05-01T00:00:00.000Z"),
    });

    await writeBridgerConfig(tempDir, config);

    const rawConfig = await fs.readFile(getBridgerConfigPath(tempDir), "utf8");
    expect(rawConfig).toContain('\n  "schemaVersion": 1');
    await expect(readBridgerConfig(tempDir)).resolves.toEqual(config);
  });
});

describe("loadBridgerProject", () => {
  it("reports missing project state without legacy layout detection", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-project-"));

    await expect(loadBridgerProject(tempDir)).resolves.toEqual({
      status: "uninitialized",
      repoRoot: tempDir,
      reason: "missing-bridger-dir",
    });

    await fs.mkdir(path.join(tempDir, ".bridger"));

    await expect(loadBridgerProject(tempDir)).resolves.toEqual({
      status: "uninitialized",
      repoRoot: tempDir,
      reason: "missing-config",
    });
  });

  it("reports initialized and invalid config states", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-project-"));
    const config = createBridgerConfig({
      repoRoot: tempDir,
      mode: "existing",
    });

    await writeBridgerConfig(tempDir, config);

    await expect(loadBridgerProject(tempDir)).resolves.toEqual({
      status: "initialized",
      repoRoot: tempDir,
      config,
    });

    await fs.writeFile(getBridgerConfigPath(tempDir), "{", "utf8");

    await expect(loadBridgerProject(tempDir)).resolves.toEqual(
      expect.objectContaining({
        status: "invalid",
        repoRoot: tempDir,
        reason: "invalid-config",
      }),
    );
  });
});

describe("ensureBridgerLayout", () => {
  it("creates only the canonical project layout", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-project-"));

    await ensureBridgerLayout(tempDir);

    await expect(fs.stat(getBridgerIndexPath(tempDir))).resolves.toBeDefined();
    await expect(fs.stat(getBridgerLogPath(tempDir))).resolves.toBeDefined();
    await expect(
      fs.readFile(getSelectedSkillsPath(tempDir), "utf8"),
    ).resolves.toBe('{\n  "schemaVersion": 1,\n  "selected": []\n}\n');
    await expect(
      fs.readFile(getTicketTemplatePath(tempDir), "utf8"),
    ).resolves.toBe(
      "# Ticket\n\n## Goal\n\n## Context\n\n## Implementation notes\n\n## Acceptance criteria\n\n## Validation\n",
    );
    await expect(
      fs.stat(path.join(tempDir, ".bridger", "generated")),
    ).rejects.toThrow();
    await expect(
      fs.stat(path.join(tempDir, ".bridger", "tickets")),
    ).rejects.toThrow();
  });

  it("does not overwrite an existing ticket template", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-project-"));
    await fs.mkdir(path.join(tempDir, ".bridger", "templates"), {
      recursive: true,
    });
    await fs.writeFile(
      getTicketTemplatePath(tempDir),
      "# Custom Ticket\n",
      "utf8",
    );

    await ensureBridgerLayout(tempDir);

    await expect(
      fs.readFile(getTicketTemplatePath(tempDir), "utf8"),
    ).resolves.toBe("# Custom Ticket\n");
  });
});
