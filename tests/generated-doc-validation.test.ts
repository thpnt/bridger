import { describe, expect, it } from "vitest";

import {
  validateMarkdownSections,
} from "../src/core/doc-generator/validation/markdown-section-validation";
import { KNOWLEDGE_DOC_SPECS } from "../src/core/doc-generator/doc-specs";

const cases = [
  {
    name: "repo analysis",
    displayName: KNOWLEDGE_DOC_SPECS.repoAnalysis.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.repoAnalysis.requiredSections,
    missingSection: "## Unknowns",
  },
  {
    name: "architecture",
    displayName: KNOWLEDGE_DOC_SPECS.architecture.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.architecture.requiredSections,
    missingSection: "## App structure",
  },
  {
    name: "conventions",
    displayName: KNOWLEDGE_DOC_SPECS.conventions.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.conventions.requiredSections,
    missingSection: "## Things agents should avoid",
  },
  {
    name: "business logic",
    displayName: KNOWLEDGE_DOC_SPECS.businessLogic.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.businessLogic.requiredSections,
    missingSection: "## Evidence map",
  },
  {
    name: "testing",
    displayName: KNOWLEDGE_DOC_SPECS.testing.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.testing.requiredSections,
    missingSection: "## Testing gaps and unknowns",
  },
  {
    name: "agent rules",
    displayName: KNOWLEDGE_DOC_SPECS.agentRules.displayName,
    requiredSections: KNOWLEDGE_DOC_SPECS.agentRules.requiredSections,
    missingSection: "## Unknowns",
  },
] as const;

describe("generated doc validation", () => {
  for (const testCase of cases) {
    it(`accepts ${testCase.name} markdown with all required sections`, () => {
      expect(() =>
        validateMarkdownSections({
          markdown: buildMarkdown(testCase.requiredSections),
          requiredSections: testCase.requiredSections,
          documentName: testCase.displayName,
        }),
      ).not.toThrow();
    });

    it(`rejects ${testCase.name} markdown when ${testCase.missingSection} is missing`, () => {
      expect(() =>
        validateMarkdownSections({
          markdown: buildMarkdown(
            testCase.requiredSections.filter(
              (section) => section !== testCase.missingSection,
            ),
          ),
          requiredSections: testCase.requiredSections,
          documentName: testCase.displayName,
        }),
      ).toThrow(
        `${testCase.displayName} is missing required sections: ${testCase.missingSection}`,
      );
    });
  }
});

function buildMarkdown(sections: readonly string[]): string {
  return ["# Document", "", ...sections].join("\n");
}
