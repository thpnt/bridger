import { describe, expect, it } from "vitest";

import { assertMarkdownSections } from "../src/core/context-builder/markdown-section-validation";

describe("assertMarkdownSections", () => {
  it("does not throw when all required sections are present", () => {
    expect(() =>
      assertMarkdownSections({
        markdown: "# Doc\n\n## Overview\n\n## Unknowns\n",
        requiredSections: ["## Overview", "## Unknowns"],
        documentName: "Example doc",
      }),
    ).not.toThrow();
  });

  it("throws with the missing section names", () => {
    expect(() =>
      assertMarkdownSections({
        markdown: "# Doc\n\n## Overview\n",
        requiredSections: ["## Overview", "## Unknowns", "## Risks"],
        documentName: "Example doc",
      }),
    ).toThrow(
      "Example doc is missing required sections: ## Unknowns, ## Risks",
    );
  });
});
