import { describe, expect, it } from "vitest";

import { toSlug } from "../../../src/core/utils/slug";

describe("toSlug", () => {
  it("creates a filesystem-safe slug", () => {
    expect(toSlug("Improve onboarding error handling")).toBe("improve-onboarding-error-handling");
  });

  it("removes unsafe characters and trims whitespace", () => {
    expect(toSlug(" Fix: Stripe / billing!!! ")).toBe("fix-stripe-billing");
  });

  it("falls back to untitled when empty", () => {
    expect(toSlug("!!!")).toBe("untitled");
  });
});
