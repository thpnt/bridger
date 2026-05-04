import { describe, expect, it } from "vitest";

import {
  DependencyExtractionInputSchema,
  ExtractedImportSchema,
  type DependencyExtractor,
} from "../src/core/repo-graph/extractors/dependency-extractor";

describe("dependency extractor models", () => {
  it("accepts a valid extracted import", () => {
    const result = ExtractedImportSchema.safeParse({
      specifier: "./app",
      kind: "static",
      source: "typescript-js-imports",
      line: 1,
    });

    expect(result.success).toBe(true);
  });

  it("rejects invalid import kinds", () => {
    const result = ExtractedImportSchema.safeParse({
      specifier: "./app",
      kind: "side-effect",
      source: "typescript-js-imports",
    });

    expect(result.success).toBe(false);
  });

  it("rejects invalid extractor sources", () => {
    const result = ExtractedImportSchema.safeParse({
      specifier: "./app",
      kind: "static",
      source: "filesystem",
    });

    expect(result.success).toBe(false);
  });

  it("accepts empty file content as extraction input", () => {
    const result = DependencyExtractionInputSchema.safeParse({
      filePath: "src/index.ts",
      content: "",
    });

    expect(result.success).toBe(true);
  });

  it("supports extractor implementations without graph construction", () => {
    const extractor: DependencyExtractor = {
      language: "typescript-javascript",
      extensions: [".ts", ".tsx"],
      source: "typescript-js-imports",
      extractImports: () => [
        {
          specifier: "./app",
          kind: "static",
          source: "typescript-js-imports",
          line: 1,
        },
      ],
    };

    expect(
      extractor.extractImports({
        filePath: "src/index.ts",
        content: "",
      }),
    ).toEqual([
      {
        specifier: "./app",
        kind: "static",
        source: "typescript-js-imports",
        line: 1,
      },
    ]);
  });
});
