import { describe, expect, it } from "vitest";

import { FileIndexSchema } from "../src/core/models/file-index";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
} from "../src/core/project/bridger-paths";
import { RepoContextSchema } from "../src/core/models/repo-context";
import { EnrichedTicketSchema } from "../src/core/models/ticket";

describe("core models", () => {
  it("validates a repo context payload", () => {
    const repoContext = {
      repoRoot: "/repo",
      generatedAt: "2026-05-01T00:00:00.000Z",
      stack: {
        framework: "Next.js",
        language: "TypeScript",
        packageManager: "pnpm",
        styling: ["Tailwind"],
        validation: ["Zod"],
        database: ["Supabase"],
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
    };

    expect(RepoContextSchema.parse(repoContext)).toEqual(repoContext);
  });

  it("validates a file index payload", () => {
    const fileIndex = {
      generatedAt: "2026-05-01T00:00:00.000Z",
      files: [
        {
          path: "README.md",
          extension: ".md",
          sizeBytes: 120,
          tags: ["readme", "documentation", "important"],
          reason: "Project README",
        },
      ],
    };

    expect(FileIndexSchema.parse(fileIndex)).toEqual(fileIndex);
  });

  it("validates an enriched ticket payload", () => {
    const enrichedTicket = {
      title: "Improve onboarding error handling",
      sourceRequest: "Improve onboarding error handling",
      goal: "Make onboarding failures easier to diagnose.",
      desiredBehavior: "Users see actionable failure details during onboarding.",
      repoContext: ["Onboarding starts in src/app/onboarding/page.tsx"],
      acceptanceCriteria: ["Onboarding shows a useful error message when setup fails."],
      constraints: ["Do not change the onboarding happy path."],
      suggestedFiles: [
        {
          path: "src/app/onboarding/page.tsx",
          reason: "Entry point for the onboarding flow.",
        },
      ],
      testExpectations: ["Add a regression test for the failing setup path."],
      missingQuestions: [],
      assumptions: ["The current error state is too generic."],
      riskLevel: "medium",
      agentSuitability: {
        score: 82,
        reason: "The change is local and testable.",
      },
      handoffPrompt: "Update onboarding error handling and add coverage.",
      supportingEvidence: [
        {
          path: "src/app/onboarding/page.tsx",
          claim: "This file renders onboarding errors.",
          confidence: "high",
        },
      ],
      metadata: {
        slug: "improve-onboarding-error-handling",
        createdAt: "2026-05-01T00:00:00.000Z",
        generatedBy: "bridger",
      },
    };

    expect(EnrichedTicketSchema.parse(enrichedTicket)).toEqual(enrichedTicket);
  });
});
