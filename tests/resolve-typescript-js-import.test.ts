import { describe, expect, it } from "vitest";

import { resolveTypeScriptJsImport } from "../src/core/repo-graph/resolution/resolve-typescript-js-import";

describe("resolveTypeScriptJsImport", () => {
  it("resolves relative imports to existing files", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/index.ts",
        specifier: "./app",
        repoFiles: ["src/index.ts", "src/app.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app.ts",
      confidence: "high",
    });
  });

  it("resolves parent relative imports", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/app/page.tsx",
        specifier: "../lib/format",
        repoFiles: ["src/app/page.tsx", "src/lib/format.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/lib/format.ts",
      confidence: "high",
    });
  });

  it("resolves directory index imports", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/app.ts",
        specifier: "./features/users",
        repoFiles: ["src/app.ts", "src/features/users/index.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/features/users/index.ts",
      confidence: "high",
    });
  });

  it("ignores external package imports", () => {
    for (const specifier of [
      "react",
      "next",
      "zod",
      "@supabase/supabase-js",
      "node:fs",
      "fs",
      "@/components/Button",
    ]) {
      expect(
        resolveTypeScriptJsImport({
          importerPath: "src/index.ts",
          specifier,
          repoFiles: ["src/index.ts"],
        }),
      ).toEqual({
        status: "ignored",
        reason: "external-package",
      });
    }
  });

  it("returns unresolved for missing local imports", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/index.ts",
        specifier: "./missing",
        repoFiles: ["src/index.ts"],
      }),
    ).toEqual({
      status: "unresolved",
      reason: "local-import-not-found",
    });
  });

  it("resolves imports with explicit supported extensions", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/index.ts",
        specifier: "./app.ts",
        repoFiles: ["src/index.ts", "src/app.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app.ts",
      confidence: "high",
    });
  });

  it("uses deterministic candidate priority", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/index.ts",
        specifier: "./app",
        repoFiles: ["src/index.ts", "src/app.tsx", "src/app.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app.ts",
      confidence: "high",
    });
  });

  it("normalizes Windows-style importer and repo file paths", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src\\index.ts",
        specifier: "./app",
        repoFiles: ["src\\index.ts", "src\\app.ts"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app.ts",
      confidence: "high",
    });
  });

  it("accepts a readonly set of repo files", () => {
    expect(
      resolveTypeScriptJsImport({
        importerPath: "src/index.ts",
        specifier: "./app",
        repoFiles: new Set(["src/index.ts", "src/app.ts"]),
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app.ts",
      confidence: "high",
    });
  });
});
