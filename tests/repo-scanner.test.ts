import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { FileIndexSchema } from "../src/core/models/file-index";
import {
  RepoContextCommandsSchema,
  RepoContextStackSchema,
} from "../src/core/models/repo-context";
import { getGeneratedKnowledgeDocRelativePath } from "../src/core/models/generated-paths";
import { detectCommands } from "../src/core/repo-scanner/detect-commands";
import { buildFileIndex } from "../src/core/repo-scanner/build-file-index";
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
