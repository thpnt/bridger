import { describe, expect, it } from "vitest";

import { detectLanguageFromExtension } from "../src/core/repo-graph/utils/detect-language";
import { getPathTags } from "../src/core/repo-graph/utils/path-tags";
import { normalizeRepoPath } from "../src/core/repo-graph/utils/normalize-path";

describe("repo graph utilities", () => {
  describe("normalizeRepoPath", () => {
    it("normalizes separators and repo-relative prefixes", () => {
      expect(normalizeRepoPath("src\\app\\page.tsx")).toBe(
        "src/app/page.tsx",
      );
      expect(normalizeRepoPath("./src/app/page.tsx")).toBe("src/app/page.tsx");
      expect(normalizeRepoPath("src//app///page.tsx")).toBe("src/app/page.tsx");
    });

    it("keeps root-like values stable", () => {
      expect(normalizeRepoPath("")).toBe(".");
      expect(normalizeRepoPath(".")).toBe(".");
    });

    it("does not strip leading slashes", () => {
      expect(normalizeRepoPath("/tmp/repo")).toBe("/tmp/repo");
    });
  });

  describe("detectLanguageFromExtension", () => {
    it("detects supported languages from extensions", () => {
      expect(detectLanguageFromExtension(".ts")).toBe("typescript");
      expect(detectLanguageFromExtension("tsx")).toBe("typescript");
      expect(detectLanguageFromExtension(".js")).toBe("javascript");
      expect(detectLanguageFromExtension(".jsx")).toBe("javascript");
      expect(detectLanguageFromExtension(".mjs")).toBe("javascript");
      expect(detectLanguageFromExtension(".cjs")).toBe("javascript");
      expect(detectLanguageFromExtension(".py")).toBe("python");
      expect(detectLanguageFromExtension(".md")).toBe("markdown");
      expect(detectLanguageFromExtension(".json")).toBe("json");
    });

    it("returns unknown for missing or unsupported extensions", () => {
      expect(detectLanguageFromExtension(".toml")).toBe("unknown");
      expect(detectLanguageFromExtension(null)).toBe("unknown");
      expect(detectLanguageFromExtension(undefined)).toBe("unknown");
    });
  });

  describe("getPathTags", () => {
    it("tags root documentation and config files", () => {
      expect(getPathTags("README.md")).toEqual(["root", "docs"]);
      expect(getPathTags("package.json")).toEqual(["root", "config"]);
    });

    it("tags Next.js app paths", () => {
      const tags = getPathTags("src/app/page.tsx");

      expect(tags).toContain("source");
      expect(tags).toContain("entrypoint-candidate");
      expect(tags).toContain("component");
      expect(tags).toContain("route");
    });

    it("tags API routes", () => {
      const tags = getPathTags("src/app/api/users/route.ts");

      expect(tags).toContain("source");
      expect(tags).toContain("entrypoint-candidate");
      expect(tags).toContain("route");
      expect(tags).toContain("api-route");
    });

    it("tags common source categories", () => {
      expect(getPathTags("src/components/Button.tsx")).toContain("component");
      expect(getPathTags("src/services/user-service.ts")).toContain("service");
      expect(getPathTags("src/lib/format.ts")).toContain("utility");
      expect(getPathTags("tests/repo-graph.test.ts")).toContain("test");
    });
  });
});
