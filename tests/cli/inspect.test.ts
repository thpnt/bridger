import { describe, expect, it } from "vitest";

import { formatInspectSummary } from "../../src/cli/commands/inspect";

describe("formatInspectSummary", () => {
  it("renders lists and commands in a stable readable format", () => {
    const summary = formatInspectSummary({
      repoRoot: "/repo",
      stack: {
        framework: "Next.js",
        language: "TypeScript",
        packageManager: "pnpm",
        styling: ["Tailwind", "shadcn/ui"],
        validation: ["Zod"],
        database: ["Supabase"],
        testFramework: ["Vitest", "Playwright"],
      },
      commands: {
        install: "pnpm install",
        dev: "pnpm dev",
        build: "pnpm build",
        lint: "pnpm lint",
        typecheck: "pnpm typecheck",
        test: "pnpm test",
        format: "pnpm format",
      },
      indexedFileCount: 183,
    });

    expect(summary).toContain("bridger Inspect");
    expect(summary).toContain("Repo: /repo");
    expect(summary).toContain("Styling: Tailwind, shadcn/ui");
    expect(summary).toContain("Validation: Zod");
    expect(summary).toContain("Database: Supabase");
    expect(summary).toContain("Testing: Vitest, Playwright");
    expect(summary).toContain("- install: pnpm install");
    expect(summary).toContain("- dev: pnpm dev");
    expect(summary).toContain("- build: pnpm build");
    expect(summary).toContain("- lint: pnpm lint");
    expect(summary).toContain("- typecheck: pnpm typecheck");
    expect(summary).toContain("- test: pnpm test");
    expect(summary).toContain("- format: pnpm format");
    expect(summary).toContain("Indexed files: 183");
  });

  it("renders empty collections and missing commands as none", () => {
    const summary = formatInspectSummary({
      repoRoot: "/repo",
      stack: {
        framework: "unknown",
        language: "unknown",
        packageManager: "unknown",
        styling: [],
        validation: [],
        database: [],
        testFramework: [],
      },
      commands: {},
      indexedFileCount: 0,
    });

    expect(summary).toContain("Framework: unknown");
    expect(summary).toContain("Styling: none");
    expect(summary).toContain("Validation: none");
    expect(summary).toContain("Database: none");
    expect(summary).toContain("Testing: none");
    expect(summary).toContain("Commands:\n- none");
  });
});
