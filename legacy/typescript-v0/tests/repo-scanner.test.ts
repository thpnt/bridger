import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { FileIndexSchema } from "../src/core/models/file-index";
import {
  RepoContextCommandsSchema,
  RepoContextStackSchema,
} from "../src/core/models/repo-context";
import { getGeneratedKnowledgeDocRelativePath } from "../src/core/project/bridger-paths";
import { detectCommands } from "../src/core/repo-scanner/detect-commands";
import { buildFileIndex } from "../src/core/repo-scanner/build-file-index";
import { buildRepoGraph } from "../src/core/repo-graph/build-repo-graph";
import { buildGraphSummary } from "../src/core/repo-graph/build-graph-summary";
import { detectStack } from "../src/core/repo-scanner/detect-stack";

const fixtureRoot = path.resolve("tests/fixtures/file-index-basic");
const nextFixtureRoot = path.resolve("tests/fixtures/nextjs-basic");
const noPackageJsonFixtureRoot = path.resolve("tests/fixtures/no-package-json");
const commandsPnpmFixtureRoot = path.resolve("tests/fixtures/commands-pnpm");
const commandsAlternateScriptsFixtureRoot = path.resolve(
  "tests/fixtures/commands-alternate-scripts",
);
const commandsNpmFixtureRoot = path.resolve("tests/fixtures/commands-npm");
const commandsBunFixtureRoot = path.resolve("tests/fixtures/commands-bun");
const commandsPackageManagerFixtureRoot = path.resolve(
  "tests/fixtures/commands-package-manager",
);
let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("repo scanner", () => {
  it("builds a deterministic, gitignore-aware file index", async () => {
    const index = await buildFileIndex(fixtureRoot);

    expect(FileIndexSchema.parse(index)).toEqual(index);
    expect(index.files.map((entry) => entry.path)).toEqual([
      ".gitignore",
      "components/Button.tsx",
      "package.json",
      "README.md",
      "src/app/page.tsx",
      "src/lib/auth.ts",
    ]);

    expect(index.files.some((entry) => entry.path === ".env")).toBe(false);
    expect(index.files.some((entry) => entry.path === "node_modules/ignored.js")).toBe(false);
    expect(index.files.some((entry) => entry.path === ".next/ignored.js")).toBe(false);
    expect(index.files.some((entry) => entry.path === "ignored/generated.ts")).toBe(false);
    expect(index.files.some((entry) => entry.path === "public/logo.png")).toBe(false);
    expect(
      index.files.some(
        (entry) => entry.path === getGeneratedKnowledgeDocRelativePath("architecture"),
      ),
    ).toBe(false);
    expect(index.files.some((entry) => entry.path === ".agents/skills/generated-skill/SKILL.md")).toBe(false);

    const readme = index.files.find((entry) => entry.path === "README.md");
    const packageJson = index.files.find((entry) => entry.path === "package.json");
    const page = index.files.find((entry) => entry.path === "src/app/page.tsx");
    const auth = index.files.find((entry) => entry.path === "src/lib/auth.ts");

    expect(readme?.tags).toEqual(["readme", "documentation", "important", "markdown"]);
    expect(packageJson?.tags).toEqual(["package", "config", "important", "json"]);
    expect(page?.tags).toEqual(["src", "app", "route", "typescript", "react"]);
    expect(auth?.tags).toEqual(["src", "lib", "typescript"]);

    expect(readme?.reason).toBe("Project README");
    expect(packageJson?.reason).toBe("Package manifest and scripts/dependencies source");
    expect(page?.reason).toBe("Application route file");
    expect(auth?.reason).toBe("Library/helper file");

    expect(index.files.every((entry) => entry.path === entry.path.replaceAll("\\", "/"))).toBe(true);
    expect(index.files.map((entry) => entry.path)).toEqual(
      [...index.files.map((entry) => entry.path)].sort((left, right) => left.localeCompare(right)),
    );
  });

  it("builds a v2 repository inventory with skip diagnostics, roles, stats, signals, and entrypoints", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-inventory-"));
    await fs.outputJson(
      path.join(tempDir, "package.json"),
      {
        name: "inventory-fixture",
        bin: {
          inventory: "./src/cli/cli.ts",
        },
      },
      { spaces: 2 },
    );
    await fs.outputFile(path.join(tempDir, "pnpm-lock.yaml"), "lockfileVersion: 9\n");
    await fs.outputFile(path.join(tempDir, ".gitignore"), "ignored/\n");
    await fs.outputFile(path.join(tempDir, ".env"), "TOKEN=secret\n");
    await fs.outputFile(path.join(tempDir, ".env.local"), "TOKEN=secret\n");
    await fs.outputFile(path.join(tempDir, "public/logo.png"), "not really png\n");
    await fs.outputFile(path.join(tempDir, "large.txt"), "x".repeat(1_000_001));
    await fs.outputFile(path.join(tempDir, "ignored/generated.ts"), "export {};\n");
    await fs.outputFile(path.join(tempDir, "node_modules/pkg/index.js"), "module.exports = {};\n");
    await fs.outputFile(path.join(tempDir, ".git/HEAD"), "ref: main\n");
    await fs.outputFile(path.join(tempDir, ".bridger/artifacts/file-index.json"), "{}\n");
    await fs.outputFile(path.join(tempDir, "dist/generated.js"), "export {};\n");
    await fs.outputFile(path.join(tempDir, "build/generated.js"), "export {};\n");
    await fs.outputFile(path.join(tempDir, "coverage/coverage.json"), "{}\n");
    await fs.outputFile(path.join(tempDir, ".next/server.js"), "export {};\n");
    await fs.outputFile(path.join(tempDir, "README.md"), "# Fixture\n");
    await fs.outputFile(
      path.join(tempDir, "src/cli/cli.ts"),
      [
        'import { Command } from "commander";',
        'import { z } from "zod";',
        'import { helper } from "../lib/helper";',
        "export const cli = new Command();",
        "export const schema = z.object({ name: z.string() });",
        "helper();",
        "",
      ].join("\n"),
    );
    await fs.outputFile(
      path.join(tempDir, "src/app/page.tsx"),
      [
        'import React from "react";',
        "export default function Page() { return null; }",
        "",
      ].join("\n"),
    );
    await fs.outputFile(
      path.join(tempDir, "src/app/api/route.ts"),
      [
        'import type { NextRequest } from "next/server";',
        "export function GET(_request: NextRequest) { return Response.json({ ok: true }); }",
        "",
      ].join("\n"),
    );
    await fs.outputFile(
      path.join(tempDir, "src/lib/helper.ts"),
      "export function helper() { return true; }\n",
    );
    await fs.outputFile(
      path.join(tempDir, "tests/fixtures/user.fixture.ts"),
      "export const user = { id: 1 };\n",
    );
    await fs.outputFile(
      path.join(tempDir, "tests/sample.test.ts"),
      [
        'import { describe, it } from "vitest";',
        "describe('sample', () => { it('works', () => undefined); });",
        "",
      ].join("\n"),
    );
    await fs.outputFile(
      path.join(tempDir, "api/main.py"),
      [
        "from fastapi import FastAPI",
        "from pydantic import BaseModel",
        "app = FastAPI()",
        "class User(BaseModel):",
        "    name: str",
        "",
      ].join("\n"),
    );

    const index = await buildFileIndex(tempDir);
    const graph = await buildRepoGraph({
      repoRoot: tempDir,
      fileIndex: index,
    });
    const summary = buildGraphSummary(graph);

    expect(FileIndexSchema.parse(index)).toEqual(index);
    expect(index.schemaVersion).toBe(2);
    expect(index.skippedFiles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: ".env", reason: "sensitive" }),
        expect.objectContaining({ path: ".env.local", reason: "sensitive" }),
        expect.objectContaining({ path: "node_modules", reason: "noise-directory" }),
        expect.objectContaining({ path: ".git", reason: "noise-directory" }),
        expect.objectContaining({ path: ".bridger", reason: "noise-directory" }),
        expect.objectContaining({ path: "dist", reason: "generated" }),
        expect.objectContaining({ path: "build", reason: "generated" }),
        expect.objectContaining({ path: "coverage", reason: "generated" }),
        expect.objectContaining({ path: ".next", reason: "generated" }),
        expect.objectContaining({ path: "public/logo.png", reason: "binary" }),
        expect.objectContaining({ path: "large.txt", reason: "too-large" }),
        expect.objectContaining({ path: "ignored/generated.ts", reason: "ignored" }),
      ]),
    );
    expect(index.warnings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "sensitive-file-skipped",
          filePath: ".env",
        }),
        expect.objectContaining({
          code: "large-file-skipped",
          filePath: "large.txt",
        }),
      ]),
    );
    expect(index.stats).toEqual(
      expect.objectContaining({
        totalFilesDiscovered:
          index.files.length + (index.skippedFiles?.length ?? 0),
        includedFileCount: index.files.length,
        skippedFileCount: index.skippedFiles?.length,
      }),
    );
    expect(index.stats?.bySkipReason.sensitive).toBe(2);
    expect(index.stats?.bySkipReason.binary).toBe(1);
    expect(index.stats?.bySkipReason["too-large"]).toBe(1);
    expect(index.stats?.byLanguage.typescript).toBeGreaterThan(0);
    expect(index.stats?.byLanguage.python).toBe(1);

    const cli = getIndexedFile(index, "src/cli/cli.ts");
    const page = getIndexedFile(index, "src/app/page.tsx");
    const route = getIndexedFile(index, "src/app/api/route.ts");
    const lockfile = getIndexedFile(index, "pnpm-lock.yaml");
    const fixture = getIndexedFile(index, "tests/fixtures/user.fixture.ts");
    const test = getIndexedFile(index, "tests/sample.test.ts");
    const python = getIndexedFile(index, "api/main.py");

    expect(cli.language).toBe("typescript");
    expect(page.language).toBe("typescript");
    expect(python.language).toBe("python");
    expect(lockfile.language).toBe("yaml");

    expect(cli.roles).toEqual([...cli.roles ?? []].sort());
    expect(cli.roles).toEqual(
      expect.arrayContaining(["command", "entrypoint-candidate", "source"]),
    );
    expect(route.roles).toEqual(expect.arrayContaining(["api-route", "route"]));
    expect(lockfile.roles).toEqual(expect.arrayContaining(["lockfile"]));
    expect(lockfile.includeReason).toBe("project-metadata");
    expect(fixture.roles).toEqual(expect.arrayContaining(["fixture"]));
    expect(test.roles).toEqual(expect.arrayContaining(["test"]));

    expect(cli.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "cli", source: "import", value: "commander" }),
        expect.objectContaining({ kind: "schema", source: "import", value: "zod" }),
        expect.objectContaining({ kind: "validation", source: "import", value: "zod" }),
        expect.objectContaining({
          kind: "entrypoint",
          source: "package-json",
          value: "package-bin",
        }),
      ]),
    );
    expect(page.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "frontend", source: "import", value: "react" }),
        expect.objectContaining({ kind: "framework", source: "import", value: "react" }),
      ]),
    );
    expect(route.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "framework", source: "import", value: "next" }),
      ]),
    );
    expect(test.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "testing", source: "import", value: "vitest" }),
      ]),
    );
    expect(python.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "framework", source: "import", value: "fastapi" }),
        expect.objectContaining({ kind: "schema", source: "import", value: "pydantic" }),
        expect.objectContaining({ kind: "validation", source: "import", value: "pydantic" }),
      ]),
    );

    expect(
      graph.edges
        .filter((edge) => edge.type === "imports")
        .map((edge) => `${edge.from} -> ${edge.to}`),
    ).toEqual(["src/cli/cli.ts -> src/lib/helper.ts"]);
    expect(
      graph.edges.some((edge) => edge.to === "react" || edge.to === "commander"),
    ).toBe(false);
    expect(graph.diagnostics).toEqual([]);
    expect(summary.entrypoints).toContain("src/cli/cli.ts");
    expect(summary.entrypoints.every((entrypoint) => typeof entrypoint === "string")).toBe(true);
  });

  it("detects a Next.js stack from package and file heuristics", async () => {
    const stack = await detectStack(nextFixtureRoot);

    expect(RepoContextStackSchema.parse(stack)).toEqual(stack);
    expect(stack.framework).toBe("Next.js");
    expect(stack.language).toBe("TypeScript");
    expect(stack.packageManager).toBe("pnpm");
    expect(stack.styling).toContain("Tailwind");
    expect(stack.styling).toContain("shadcn/ui");
    expect(stack.validation).toContain("Zod");
    expect(stack.database).toContain("Supabase");
    expect(stack.database).toContain("Drizzle");
    expect(stack.testFramework).toContain("Vitest");
    expect(stack.testFramework).toContain("Playwright");
  });

  it("handles a repository without package.json gracefully", async () => {
    const stack = await detectStack(noPackageJsonFixtureRoot);

    expect(RepoContextStackSchema.parse(stack)).toEqual(stack);
    expect(stack.framework).toBe("unknown");
    expect(stack.language).toBe("unknown");
    expect(stack.packageManager).toBe("unknown");
    expect(stack.styling).toEqual([]);
    expect(stack.validation).toEqual([]);
    expect(stack.database).toEqual([]);
    expect(stack.testFramework).toEqual([]);
  });

  it("detects the package manager from common lockfiles", async () => {
    const cases = [
      ["pnpm-lock.yaml", "pnpm"],
      ["package-lock.json", "npm"],
      ["yarn.lock", "yarn"],
      ["bun.lock", "bun"],
      ["bun.lockb", "bun"],
    ] as const;

    for (const [lockfileName, expectedPackageManager] of cases) {
      tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-stack-"));
      await fs.outputFile(
        path.join(tempDir, "package.json"),
        '{\n  "name": "fixture"\n}\n',
      );
      await fs.outputFile(path.join(tempDir, lockfileName), "");

      const stack = await detectStack(tempDir);

      expect(stack.packageManager).toBe(expectedPackageManager);

      await fs.rm(tempDir, { recursive: true, force: true });
      tempDir = "";
    }
  });

  it("detects Next.js from config and app structure even without a next dependency", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-stack-"));
    await fs.outputFile(
      path.join(tempDir, "package.json"),
      '{\n  "name": "fixture"\n}\n',
    );
    await fs.outputFile(path.join(tempDir, "next.config.ts"), "export default {};\n");
    await fs.outputFile(
      path.join(tempDir, "src/app/page.tsx"),
      "export default function Page() { return null; }\n",
    );

    const stack = await detectStack(tempDir);

    expect(stack.framework).toBe("Next.js");
  });

  it("detects commands from package scripts using the provided package manager", async () => {
    const commands = await detectCommands(commandsPnpmFixtureRoot, "pnpm");

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(() => RepoContextCommandsSchema.parse(commands)).not.toThrow();
    expect(commands.install).toBe("pnpm install");
    expect(commands.dev).toBe("pnpm dev");
    expect(commands.build).toBe("pnpm build");
    expect(commands.lint).toBe("pnpm lint");
    expect(commands.typecheck).toBe("pnpm typecheck");
    expect(commands.test).toBe("pnpm test");
    expect(commands.format).toBe("pnpm format");
  });

  it("falls back to alternate script names when the preferred ones are missing", async () => {
    const commands = await detectCommands(commandsAlternateScriptsFixtureRoot, "pnpm");

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(commands.install).toBe("pnpm install");
    expect(commands.dev).toBe("pnpm start");
    expect(commands.typecheck).toBe("pnpm check-types");
    expect(commands.test).toBe("pnpm test:unit");
    expect(commands.format).toBe("pnpm prettier");
    expect(commands.build).toBeUndefined();
    expect(commands.lint).toBeUndefined();
  });

  it("formats commands for npm", async () => {
    const commands = await detectCommands(commandsNpmFixtureRoot, "npm");

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(commands.install).toBe("npm install");
    expect(commands.dev).toBe("npm run dev");
    expect(commands.build).toBe("npm run build");
  });

  it("formats commands for bun", async () => {
    const commands = await detectCommands(commandsBunFixtureRoot, "bun");

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(commands.install).toBe("bun install");
    expect(commands.dev).toBe("bun run dev");
  });

  it("formats commands for yarn and falls back to install when scripts are missing", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-commands-"));
    await fs.outputFile(
      path.join(tempDir, "package.json"),
      JSON.stringify(
        {
          name: "fixture",
          packageManager: "yarn@4.0.0",
        },
        null,
        2,
      ),
    );

    const commands = await detectCommands(tempDir, "yarn");

    expect(commands).toEqual({
      install: "yarn install",
    });
  });

  it("returns an empty command object when package.json is missing", async () => {
    const commands = await detectCommands(noPackageJsonFixtureRoot, "pnpm");

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(commands).toEqual({});
  });

  it("uses package.json packageManager when no package manager is provided", async () => {
    const commands = await detectCommands(commandsPackageManagerFixtureRoot);

    expect(RepoContextCommandsSchema.parse(commands)).toEqual(commands);
    expect(commands.install).toBe("pnpm install");
    expect(commands.dev).toBe("pnpm dev");
  });
});

function getIndexedFile(
  index: Awaited<ReturnType<typeof buildFileIndex>>,
  filePath: string,
) {
  const file = index.files.find((entry) => entry.path === filePath);

  expect(file).toBeDefined();

  return file!;
}
