import { describe, expect, it } from "vitest";

import { buildArchitecturePrompt } from "../src/core/llm/prompts/architecture-prompt";
import { buildBusinessLogicPrompt } from "../src/core/llm/prompts/business-logic-prompt";
import { buildConventionsPrompt } from "../src/core/llm/prompts/conventions-prompt";
import { buildRepoAnalysisPrompt } from "../src/core/llm/prompts/repo-analysis-prompt";
import { buildTestingPrompt } from "../src/core/llm/prompts/testing-prompt";
import type { GenerateRepoKnowledgeDocInput } from "../src/core/models/repo-knowledge-doc";
import { RepoRelativePathSchema } from "../src/core/models/paths";

const input: GenerateRepoKnowledgeDocInput = {
  repoContext: {
    repoRoot: "/repo",
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: ["Tailwind CSS"],
      validation: ["zod"],
      database: [],
      testFramework: ["vitest"],
    },
    commands: {
      dev: "pnpm dev",
      test: "pnpm test",
    },
    importantFiles: [
      {
        path: "README.md",
        reason: "Project overview",
      },
    ],
    generatedDocs: {
      repoAnalysisPath: RepoRelativePathSchema.parse(
        ".bridger/generated/repo-analysis.md",
      ),
      architecturePath: RepoRelativePathSchema.parse(
        ".bridger/generated/architecture.md",
      ),
      conventionsPath: RepoRelativePathSchema.parse(
        ".bridger/generated/conventions.md",
      ),
      businessLogicPath: RepoRelativePathSchema.parse(
        ".bridger/generated/business-logic.md",
      ),
      testingPath: RepoRelativePathSchema.parse(".bridger/generated/testing.md"),
      agentRulesPath: RepoRelativePathSchema.parse(
        ".bridger/generated/agent-rules.md",
      ),
      ticketTemplatePath: RepoRelativePathSchema.parse(
        ".bridger/generated/ticket-template.md",
      ),
    },
  },
  fileIndex: {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      {
        path: RepoRelativePathSchema.parse("README.md"),
        extension: ".md",
        sizeBytes: 100,
        tags: ["documentation", "readme"],
        reason: "Project README",
      },
      {
        path: RepoRelativePathSchema.parse("src/app/page.tsx"),
        extension: ".tsx",
        sizeBytes: 200,
        tags: ["app", "route"],
        reason: "Route entry",
      },
    ],
  },
  importantFiles: [
    {
      path: "README.md",
      reason: "Project overview",
      content: "# Bridger",
    },
  ],
};

describe("prompt builders", () => {
  it("builds the repo analysis prompt scaffold", () => {
    const result = buildRepoAnalysisPrompt(input);

    assertPromptScaffold(result);
    expect(result.prompt).toContain("## File and folder evidence");
    expect(result.prompt).toContain("## Observed structure");
    expect(result.prompt).toContain("## Unknowns");
  });

  it("builds the architecture prompt scaffold", () => {
    const result = buildArchitecturePrompt(input);

    assertPromptScaffold(result);
    expect(result.prompt).toContain("## App structure");
    expect(result.prompt).toContain("## Data flow assumptions");
    expect(result.prompt).toContain("## Risky areas");
    expect(result.prompt).toContain("## Unknowns");
  });

  it("builds the conventions prompt scaffold", () => {
    const result = buildConventionsPrompt(input);

    assertPromptScaffold(result);
    expect(result.prompt).toContain("## Things agents should avoid");
  });

  it("builds the business logic prompt scaffold", () => {
    const result = buildBusinessLogicPrompt(input);

    assertPromptScaffold(result);
    expect(result.prompt).toContain("## Evidence map");
  });

  it("builds the testing prompt scaffold", () => {
    const result = buildTestingPrompt(input);

    assertPromptScaffold(result);
    expect(result.prompt).toContain("## Testing philosophy");
    expect(result.prompt).toContain("## Test types and when to use them");
    expect(result.prompt).toContain("## Unit testing conventions");
    expect(result.prompt).toContain("## Testing gaps and unknowns");
    expect(result.prompt).toContain("## Things agents should avoid");
  });
});

function assertPromptScaffold(result: { system: string; prompt: string }): void {
  expect(result.system).toEqual(expect.any(String));
  expect(result.prompt).toEqual(expect.any(String));
  expect(result.system).toContain("TODO");
  expect(result.prompt).toContain("TODO");
  expect(result.prompt).toContain("Repo context:");
  expect(result.prompt).toContain("File index summary:");
  expect(result.prompt).toContain("Important files:");
}
