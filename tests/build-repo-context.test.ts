import path from "node:path";

import { describe, expect, it } from "vitest";

import { RepoContextBuildArtifactsSchema } from "../src/core/models/repo-context-build";
import { RepoContextSchema } from "../src/core/models/repo-context";
import {
  buildRepoContext,
  buildRepoContextArtifacts,
} from "../src/core/context-builder/build-repo-context";

const fixtureRoot = path.resolve("tests/fixtures/repo-context-basic");

describe("buildRepoContext", () => {
  it("builds a validated repo context with stable generated doc paths", async () => {
    const repoContext = await buildRepoContext(fixtureRoot);

    expect(RepoContextSchema.parse(repoContext)).toEqual(repoContext);
    expect(repoContext.repoRoot).toBe(fixtureRoot);
    expect(repoContext.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(new Date(repoContext.generatedAt).toISOString()).toBe(
      repoContext.generatedAt,
    );
    expect(repoContext.stack.framework).toBe("Next.js");
    expect(repoContext.stack.language).toBe("TypeScript");
    expect(repoContext.stack.packageManager).toBe("pnpm");
    expect(repoContext.commands.install).toBe("pnpm install");
    expect(repoContext.commands.dev).toBe("pnpm dev");
    expect(repoContext.generatedDocs).toEqual({
      repoAnalysisPath: ".bridger/generated/repo-analysis.md",
      architecturePath: ".bridger/generated/architecture.md",
      conventionsPath: ".bridger/generated/conventions.md",
      businessLogicPath: ".bridger/generated/business-logic.md",
      testingPath: ".bridger/generated/testing.md",
      agentRulesPath: ".bridger/generated/agent-rules.md",
      ticketTemplatePath: ".bridger/generated/ticket-template.md",
    });

    expect(repoContext.importantFiles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: "README.md", reason: expect.any(String) }),
        expect.objectContaining({
          path: "src/app/page.tsx",
          reason: expect.any(String),
        }),
        expect.objectContaining({
          path: "src/domains/billing/schema.ts",
          reason: expect.any(String),
        }),
        expect.objectContaining({
          path: "src/components/ui/button.tsx",
          reason: expect.any(String),
        }),
      ]),
    );

    expect(repoContext.importantFiles.every((entry) => !("content" in entry))).toBe(
      true,
    );
  });

  it("returns build artifacts with the file index and compact repo context", async () => {
    const artifacts = await buildRepoContextArtifacts(fixtureRoot);

    expect(RepoContextBuildArtifactsSchema.parse(artifacts)).toEqual(artifacts);
    expect(RepoContextSchema.parse(artifacts.repoContext)).toEqual(
      artifacts.repoContext,
    );
    expect(artifacts.fileIndex.files.length).toBeGreaterThan(0);
    expect(artifacts.repoContext.importantFiles.length).toBeGreaterThan(0);
    expect(
      artifacts.fileIndex.files.some((entry) => entry.path === "README.md"),
    ).toBe(true);
    expect(
      artifacts.fileIndex.files.some((entry) => entry.path === "package.json"),
    ).toBe(true);
  });
});
