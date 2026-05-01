import { describe, expect, it } from "vitest";

import {
  assertArchitectureDoc,
  REQUIRED_ARCHITECTURE_SECTIONS,
} from "../src/core/context-builder/generate-architecture-doc";
import {
  assertBusinessLogicDoc,
  REQUIRED_BUSINESS_LOGIC_SECTIONS,
} from "../src/core/context-builder/generate-business-logic-doc";
import {
  assertConventionsDoc,
  REQUIRED_CONVENTIONS_SECTIONS,
} from "../src/core/context-builder/generate-conventions-doc";
import {
  assertRepoAnalysisDoc,
  REQUIRED_REPO_ANALYSIS_SECTIONS,
} from "../src/core/context-builder/generate-repo-analysis-doc";
import {
  assertTestingDoc,
  REQUIRED_TESTING_SECTIONS,
} from "../src/core/context-builder/generate-testing-doc";

describe("generated doc validation", () => {
  it("accepts repo analysis markdown with all required sections", () => {
    expect(() =>
      assertRepoAnalysisDoc(buildMarkdown(REQUIRED_REPO_ANALYSIS_SECTIONS)),
    ).not.toThrow();
  });

  it("rejects repo analysis markdown when Unknowns is missing", () => {
    expect(() =>
      assertRepoAnalysisDoc(
        buildMarkdown(
          REQUIRED_REPO_ANALYSIS_SECTIONS.filter(
            (section) => section !== "## Unknowns",
          ),
        ),
      ),
    ).toThrow("Repo analysis doc is missing required sections: ## Unknowns");
  });

  it("accepts architecture markdown with all required sections", () => {
    expect(() =>
      assertArchitectureDoc(buildMarkdown(REQUIRED_ARCHITECTURE_SECTIONS)),
    ).not.toThrow();
  });

  it("rejects architecture markdown when App structure is missing", () => {
    expect(() =>
      assertArchitectureDoc(
        buildMarkdown(
          REQUIRED_ARCHITECTURE_SECTIONS.filter(
            (section) => section !== "## App structure",
          ),
        ),
      ),
    ).toThrow("Architecture doc is missing required sections: ## App structure");
  });

  it("accepts conventions markdown with all required sections", () => {
    expect(() =>
      assertConventionsDoc(buildMarkdown(REQUIRED_CONVENTIONS_SECTIONS)),
    ).not.toThrow();
  });

  it("rejects conventions markdown when Things agents should avoid is missing", () => {
    expect(() =>
      assertConventionsDoc(
        buildMarkdown(
          REQUIRED_CONVENTIONS_SECTIONS.filter(
            (section) => section !== "## Things agents should avoid",
          ),
        ),
      ),
    ).toThrow(
      "Conventions doc is missing required sections: ## Things agents should avoid",
    );
  });

  it("accepts business logic markdown with all required sections", () => {
    expect(() =>
      assertBusinessLogicDoc(buildMarkdown(REQUIRED_BUSINESS_LOGIC_SECTIONS)),
    ).not.toThrow();
  });

  it("rejects business logic markdown when Evidence map is missing", () => {
    expect(() =>
      assertBusinessLogicDoc(
        buildMarkdown(
          REQUIRED_BUSINESS_LOGIC_SECTIONS.filter(
            (section) => section !== "## Evidence map",
          ),
        ),
      ),
    ).toThrow(
      "Business logic doc is missing required sections: ## Evidence map",
    );
  });

  it("accepts testing markdown with all required sections", () => {
    expect(() =>
      assertTestingDoc(buildMarkdown(REQUIRED_TESTING_SECTIONS)),
    ).not.toThrow();
  });

  it("rejects testing markdown when Testing gaps and unknowns is missing", () => {
    expect(() =>
      assertTestingDoc(
        buildMarkdown(
          REQUIRED_TESTING_SECTIONS.filter(
            (section) => section !== "## Testing gaps and unknowns",
          ),
        ),
      ),
    ).toThrow(
      "Testing doc is missing required sections: ## Testing gaps and unknowns",
    );
  });
});

function buildMarkdown(sections: readonly string[]): string {
  return ["# Document", "", ...sections].join("\n");
}
