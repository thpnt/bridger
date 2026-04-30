import path from "node:path";

import { describe, expect, it } from "vitest";

import { resolveRepoRoot } from "../../../src/core/utils/paths";

describe("resolveRepoRoot", () => {
  it("resolves the provided path", () => {
    expect(resolveRepoRoot("..")).toBe(path.resolve(".."));
  });

  it("defaults to the current working directory", () => {
    expect(resolveRepoRoot()).toBe(path.resolve(process.cwd()));
  });
});
