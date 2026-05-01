import { describe, expect, it } from "vitest";

import {
  formatBulletList,
  formatCommands,
  formatDetectedStack,
  formatFileIndexSummary,
  formatImportantFiles,
  formatKeyValueLines,
  formatMarkdownOutputRules,
  formatRequiredSections,
  formatStringArrayValue,
  formatGroundingRules,
} from "../src/core/llm/prompts/shared/prompt-formatting";

describe("prompt formatting helpers", () => {
  it("formats bullet lists with a stable fallback", () => {
    expect(formatBulletList(["Next.js", "TypeScript"])).toEqual(
      "- Next.js\n- TypeScript",
    );
    expect(formatBulletList([])).toEqual("- Unknown");
  });

  it("formats string arrays and file index summaries", () => {
    expect(formatStringArrayValue(["Tailwind CSS", "shadcn/ui"])).toEqual(
      "Tailwind CSS, shadcn/ui",
    );
    expect(formatStringArrayValue([])).toEqual("unknown");
    expect(formatFileIndexSummary("Total indexed files: 12")).toEqual(
      "Total indexed files: 12",
    );
    expect(formatFileIndexSummary(undefined)).toEqual(
      "No file index summary provided.",
    );
  });

  it("formats key value lines, stack facts, and commands consistently", () => {
    expect(
      formatKeyValueLines({
        framework: "Next.js",
        language: "TypeScript",
        packageManager: "pnpm",
      }),
    ).toEqual("- framework: Next.js\n- language: TypeScript\n- packageManager: pnpm");

    expect(
      formatDetectedStack({
        framework: "Next.js",
        language: "TypeScript",
        packageManager: "pnpm",
        styling: ["Tailwind CSS", "shadcn/ui"],
        validation: ["zod"],
        database: [],
        testFramework: ["vitest"],
      }),
    ).toEqual(
      [
        "- Framework: Next.js",
        "- Language: TypeScript",
        "- Package manager: pnpm",
        "- Styling: Tailwind CSS, shadcn/ui",
        "- Validation: zod",
        "- Database: unknown",
        "- Testing: vitest",
      ].join("\n"),
    );

    expect(
      formatCommands({
        install: "pnpm install",
        dev: "pnpm dev",
        build: "pnpm build",
        lint: "pnpm lint",
        typecheck: "pnpm typecheck",
        test: "pnpm test",
        format: "pnpm format",
      }),
    ).toEqual(
      [
        "- install: pnpm install",
        "- dev: pnpm dev",
        "- build: pnpm build",
        "- lint: pnpm lint",
        "- typecheck: pnpm typecheck",
        "- test: pnpm test",
        "- format: pnpm format",
      ].join("\n"),
    );

    expect(formatCommands({})).toEqual("- Unknown");
  });

  it("formats required sections, grounding rules, and markdown rules", () => {
    expect(
      formatRequiredSections([
        "## Project overview",
        "## Detected stack",
        "## Unknowns",
      ]),
    ).toEqual(
      [
        "- ## Project overview",
        "- ## Detected stack",
        "- ## Unknowns",
      ].join("\n"),
    );

    expect(formatGroundingRules()).toContain(
      "Use only the provided repo context, file index summary, important files, and generated docs included in the prompt.",
    );
    expect(formatGroundingRules()).toContain("Unknowns section");
    expect(formatMarkdownOutputRules()).toContain("Return Markdown only.");
  });

  it("formats important files without truncating content", () => {
    expect(
      formatImportantFiles([
        {
          path: "README.md",
          reason: "Project overview",
          content: "# Bridger",
        },
      ]),
    ).toEqual([
      "--- FILE: README.md",
      "Reason: Project overview",
      "# Bridger",
      "--- END FILE",
    ].join("\n"));

    expect(formatImportantFiles([])).toEqual("none");
  });
});
