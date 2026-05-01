import { describe, expect, it } from "vitest";

import { buildAgentRulesPrompt } from "../src/core/llm/prompts/docs/agent-rules-prompt";
import { buildArchitecturePrompt } from "../src/core/llm/prompts/docs/architecture-prompt";
import { buildBusinessLogicPrompt } from "../src/core/llm/prompts/docs/business-logic-prompt";
import { buildConventionsPrompt } from "../src/core/llm/prompts/docs/conventions-prompt";
import { buildRepoAnalysisPrompt } from "../src/core/llm/prompts/docs/repo-analysis-prompt";
import { buildTestingPrompt } from "../src/core/llm/prompts/docs/testing-prompt";
import { GENERATED_DOC_FILENAMES } from "../src/core/doc-generator/doc-filenames";
import { buildKnowledgeDocGenerationInput } from "../src/core/doc-generator/knowledge-doc-input";
import {
  GenerateAgentRulesDocInputSchema,
  type GenerateAgentRulesDocInput,
} from "../src/core/models/agent-rules-doc";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
  RepoRelativePathSchema,
} from "../src/core/models/generated-paths";

const input = buildKnowledgeDocGenerationInput({
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
      ...buildGeneratedDocPaths(),
      ticketTemplatePath: RepoRelativePathSchema.parse(
        getTicketTemplateRelativePath(),
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
});

const agentRulesInput: GenerateAgentRulesDocInput = {
  repoContext: input.repoContext,
  generatedDocs: {
    repoAnalysis: "## Project overview\n\nRepo analysis content.",
    architecture: "## Project overview\n\nArchitecture content.",
    conventions: "## TypeScript conventions\n\nConventions content.",
    businessLogic: "## Product/domain overview\n\nBusiness logic content.",
    testing: "## Testing philosophy\n\nTesting content.",
  },
};

describe("prompt builders", () => {
  it("validates the agent rules input schema", () => {
    expect(() => GenerateAgentRulesDocInputSchema.parse(agentRulesInput)).not.toThrow();
    expect(() =>
      GenerateAgentRulesDocInputSchema.parse({
        ...agentRulesInput,
        generatedDocs: {
          ...agentRulesInput.generatedDocs,
          testing: undefined,
        },
      }),
    ).toThrow();
  });

  it("builds the repo analysis prompt scaffold", () => {
    const result = buildRepoAnalysisPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("# Analysis guidance");
    expect(result.prompt).toContain("## File and folder evidence");
    expect(result.prompt).toContain("## Observed structure");
    expect(result.prompt).toContain("## Unknowns");
  });

  it("builds the architecture prompt scaffold", () => {
    const result = buildArchitecturePrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("# Architecture guidance");
    expect(result.prompt).toContain("## App structure");
    expect(result.prompt).toContain("## Data flow assumptions");
    expect(result.prompt).toContain("## Risky areas");
    expect(result.prompt).toContain("## Unknowns");
  });

  it("builds the conventions prompt scaffold", () => {
    const result = buildConventionsPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("# Conventions guidance");
    expect(result.prompt).toContain("## Things agents should avoid");
  });

  it("builds the business logic prompt scaffold", () => {
    const result = buildBusinessLogicPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("# Business logic guidance");
    expect(result.prompt).toContain("## Evidence map");
  });

  it("builds the testing prompt scaffold", () => {
    const result = buildTestingPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("# Testing guidance");
    expect(result.prompt).toContain("## Testing philosophy");
    expect(result.prompt).toContain("## Test types and when to use them");
    expect(result.prompt).toContain("## Unit testing conventions");
    expect(result.prompt).toContain("## Testing gaps and unknowns");
    expect(result.prompt).toContain("## Things agents should avoid");
    expect(result.prompt).toContain("test: pnpm test");
    expect(result.prompt).toContain("Testing: vitest");
  });

  it("builds the testing prompt without inventing test frameworks or commands", () => {
    const result = buildTestingPrompt({
      ...input,
      repoContext: {
        ...input.repoContext,
        commands: {},
        stack: {
          ...input.repoContext.stack,
          testFramework: [],
        },
      },
    });

    expect(result.prompt).toContain("## Testing philosophy");
    expect(result.prompt).toContain("- Unknown");
    expect(result.prompt).toContain("Testing: unknown");
    expect(result.prompt).not.toContain("pnpm test");
  });

  it("builds the agent rules prompt scaffold", () => {
    const result = buildAgentRulesPrompt(agentRulesInput);

    expect(result.system).toEqual(expect.any(String));
    expect(result.prompt).toEqual(expect.any(String));
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).not.toContain("TODO");
    expect(result.prompt).toContain("# Agent guidance");
    expect(result.prompt).toContain("# Repo context");
    expect(result.prompt).toContain("# Generated docs");
    expect(result.prompt).toContain(
      GENERATED_DOC_FILENAMES.repoAnalysis,
    );
    expect(result.prompt).toContain(
      GENERATED_DOC_FILENAMES.architecture,
    );
    expect(result.prompt).toContain(
      GENERATED_DOC_FILENAMES.conventions,
    );
    expect(result.prompt).toContain(
      GENERATED_DOC_FILENAMES.businessLogic,
    );
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.testing);
    expect(result.prompt).toContain("## Project overview");
    expect(result.prompt).toContain("## Rules for agents");
    expect(result.prompt).toContain("## Business logic boundaries");
    expect(result.prompt).toContain(
      "## Files/folders to avoid unless explicitly requested",
    );
    expect(result.prompt).toContain("## Unknowns");
  });
});

function assertPromptScaffold(result: { system: string; prompt: string }): void {
  expect(result.system).toEqual(expect.any(String));
  expect(result.prompt).toEqual(expect.any(String));
  expect(result.prompt).toContain("# Required sections");
  expect(result.prompt).toContain("# Grounding rules");
  expect(result.prompt).toContain("# Output rules");
  expect(result.prompt).toContain("# Repo context");
  expect(result.prompt).toContain("## Detected stack");
  expect(result.prompt).toContain("## Commands");
  expect(result.prompt).toContain("## File index summary");
  expect(result.prompt).toContain("## Important files");
}
