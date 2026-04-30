import path from "node:path";

import { describe, expect, it } from "vitest";

import { FileIndexSchema } from "../src/core/models/file-index";
import { buildFileIndex } from "../src/core/repo-scanner/build-file-index";

const fixtureRoot = path.resolve("tests/fixtures/file-index-basic");

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
    expect(index.files.some((entry) => entry.path === ".bridger/generated/architecture.md")).toBe(false);
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
});
