import { describe, expect, it } from "vitest";

import type { ExtractedImport } from "../src/core/repo-graph/extractors/dependency-extractor";
import {
  extractTypeScriptJsImports,
  typescriptJsImportExtractor,
} from "../src/core/repo-graph/extractors/typescript-js-import-extractor";

function simplify(imports: ExtractedImport[]) {
  return imports.map((item) => ({
    specifier: item.specifier,
    kind: item.kind,
  }));
}

describe("typescriptJsImportExtractor", () => {
  it("extracts static imports and type imports", () => {
    const imports = extractTypeScriptJsImports(`
import React from "react";
import { helper } from "./helper";
import type { Config } from "../config";
import "./globals.css";
`);

    expect(simplify(imports)).toEqual([
      { specifier: "react", kind: "static" },
      { specifier: "./helper", kind: "static" },
      { specifier: "../config", kind: "static" },
      { specifier: "./globals.css", kind: "static" },
    ]);
  });

  it("extracts reexports", () => {
    const imports = extractTypeScriptJsImports(`
export * from "./public-api";
export { Button } from "../components/button";
export type { Config } from "./types";
`);

    expect(simplify(imports)).toEqual([
      { specifier: "./public-api", kind: "reexport" },
      { specifier: "../components/button", kind: "reexport" },
      { specifier: "./types", kind: "reexport" },
    ]);
  });

  it("extracts require calls", () => {
    const imports = extractTypeScriptJsImports(`
const fs = require("fs");
const local = require("./local");
require("../setup");
`);

    expect(simplify(imports)).toEqual([
      { specifier: "fs", kind: "require" },
      { specifier: "./local", kind: "require" },
      { specifier: "../setup", kind: "require" },
    ]);
  });

  it("extracts dynamic imports", () => {
    const imports = extractTypeScriptJsImports(`
const mod = await import("./dynamic");
const pkg = import("next/dynamic");
`);

    expect(simplify(imports)).toEqual([
      { specifier: "./dynamic", kind: "dynamic" },
      { specifier: "next/dynamic", kind: "dynamic" },
    ]);
  });

  it("extracts package imports without resolving them", () => {
    const imports = extractTypeScriptJsImports(`
import z from "zod";
`);

    expect(simplify(imports)).toEqual([
      { specifier: "zod", kind: "static" },
    ]);
  });

  it("skips imports commented out with line comments", () => {
    const imports = extractTypeScriptJsImports(`
// import old from "./old";
import current from "./current";
`);

    expect(simplify(imports)).toEqual([
      { specifier: "./current", kind: "static" },
    ]);
  });

  it("declares all supported TS/JS extensions", () => {
    expect(typescriptJsImportExtractor.extensions).toEqual([
      ".ts",
      ".tsx",
      ".js",
      ".jsx",
      ".mjs",
      ".cjs",
    ]);
  });

  it("can be used through the dependency extractor interface", () => {
    const imports = typescriptJsImportExtractor.extractImports({
      filePath: "src/index.ts",
      content: `import app from "./app";`,
    });

    expect(simplify(imports)).toEqual([
      { specifier: "./app", kind: "static" },
    ]);
  });

  it("includes positive line numbers", () => {
    const imports = extractTypeScriptJsImports(`

import app from "./app";
`);

    expect(imports[0]?.line).toBe(3);
    expect(
      imports.every((item) => typeof item.line === "number" && item.line > 0),
    ).toBe(true);
  });
});
