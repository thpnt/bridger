import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/core/doc-generator/generators/generate-knowledge-doc", () => ({
  generateKnowledgeDoc: vi.fn(),
}));

import { KNOWLEDGE_DOC_SPECS } from "../src/core/doc-generator/doc-specs";
import { generateAgentRulesDoc } from "../src/core/doc-generator/generators/generate-agent-rules-doc";
import { generateArchitectureDoc } from "../src/core/doc-generator/generators/generate-architecture-doc";
import { generateBusinessLogicDoc } from "../src/core/doc-generator/generators/generate-business-logic-doc";
import { generateConventionsDoc } from "../src/core/doc-generator/generators/generate-conventions-doc";
import { generateRepoAnalysisDoc } from "../src/core/doc-generator/generators/generate-repo-analysis-doc";
import { generateTestingDoc } from "../src/core/doc-generator/generators/generate-testing-doc";
import { generateKnowledgeDoc } from "../src/core/doc-generator/generators/generate-knowledge-doc";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
} from "../src/core/project/bridger-paths";
import {
  RepoRelativePathSchema,
} from "../src/core/models/path";

const mockedGenerateKnowledgeDoc = vi.mocked(generateKnowledgeDoc);

const repoKnowledgeInput = {
  repoContext: {
    repoRoot: "/repo",
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: ["Tailwind"],
      validation: ["Zod"],
      database: [],
      testFramework: ["Vitest"],
    },
    commands: {
      install: "pnpm install",
      dev: "pnpm dev",
      test: "pnpm test",
    },
    importantFiles: [
      {
        path: "README.md",
        reason: "Project README",
      },
    ],
    generatedDocs: {
      ...buildGeneratedDocPaths(),
      ticketTemplatePath: getTicketTemplateRelativePath(),
    },
  },
  fileIndex: {
    schemaVersion: 2 as const,
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      {
        path: RepoRelativePathSchema.parse("README.md"),
        extension: ".md",
        sizeBytes: 100,
        language: "markdown" as const,
        roles: ["docs" as const],
        confidence: "inferred" as const,
        includeReason: "documentation" as const,
        signals: [],
        tags: ["readme", "documentation"],
        reason: "Project README",
      },
    ],
    skippedFiles: [],
    warnings: [],
    stats: {
      totalFilesDiscovered: 1,
      includedFileCount: 1,
      skippedFileCount: 0,
      totalIncludedBytes: 100,
      byLanguage: {
        markdown: 1,
      },
      byRole: {
        docs: 1,
      },
      bySkipReason: {},
    },
  },
  importantFiles: [
    {
      path: "README.md",
      reason: "Project README",
      content: "# Bridger",
    },
  ],
};

const agentRulesInput = {
  repoContext: repoKnowledgeInput.repoContext,
  generatedDocs: {
    repoAnalysis: "## Project overview\n\nRepo analysis",
    architecture: "## Project overview\n\nArchitecture",
    conventions: "## TypeScript conventions\n\nConventions",
    businessLogic: "## Product/domain overview\n\nBusiness logic",
    testing: "## Testing philosophy\n\nTesting",
  },
};

describe("doc generators", () => {
  beforeEach(() => {
    mockedGenerateKnowledgeDoc.mockReset();
    mockedGenerateKnowledgeDoc.mockResolvedValue("## Generated\n");
  });

  it.each([
    ["repo analysis", generateRepoAnalysisDoc, KNOWLEDGE_DOC_SPECS.repoAnalysis],
    ["architecture", generateArchitectureDoc, KNOWLEDGE_DOC_SPECS.architecture],
    ["conventions", generateConventionsDoc, KNOWLEDGE_DOC_SPECS.conventions],
    ["business logic", generateBusinessLogicDoc, KNOWLEDGE_DOC_SPECS.businessLogic],
    ["testing", generateTestingDoc, KNOWLEDGE_DOC_SPECS.testing],
  ])(
    "delegates %s generation to the shared knowledge doc pipeline",
    async (_name, generateDoc, spec) => {
      await expect(generateDoc(repoKnowledgeInput)).resolves.toBe("## Generated\n");

      expect(mockedGenerateKnowledgeDoc).toHaveBeenCalledTimes(1);
      expect(mockedGenerateKnowledgeDoc.mock.calls[0]?.[0].spec).toEqual(spec);
      expect(mockedGenerateKnowledgeDoc.mock.calls[0]?.[0].buildPrompt).toEqual(
        expect.any(Function),
      );
    },
  );

  it("delegates agent rules generation to the shared knowledge doc pipeline", async () => {
    await expect(generateAgentRulesDoc(agentRulesInput)).resolves.toBe(
      "## Generated\n",
    );

    expect(mockedGenerateKnowledgeDoc).toHaveBeenCalledTimes(1);
    expect(mockedGenerateKnowledgeDoc.mock.calls[0]?.[0].spec).toEqual(
      KNOWLEDGE_DOC_SPECS.agentRules,
    );
    expect(mockedGenerateKnowledgeDoc.mock.calls[0]?.[0].generationInput).toEqual(
      agentRulesInput,
    );
  });
});
