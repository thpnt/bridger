import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  getAgentsGeneratedPath,
  getAgentsMdPath,
  getBridgerDir,
  getFileIndexPath,
  getGeneratedKnowledgeDocPath,
  getRepoContextPath,
  resolveRepoRoot,
} from "../../../src/core/utils/paths";

describe("resolveRepoRoot", () => {
  it("resolves the provided path", () => {
    expect(resolveRepoRoot("..")).toBe(path.resolve(".."));
  });

  it("defaults to the current working directory", () => {
    expect(resolveRepoRoot()).toBe(path.resolve(process.cwd()));
  });
});

describe("bridger path helpers", () => {
  it("builds absolute filesystem paths for bridger outputs", () => {
    const repoRoot = path.resolve("/repo");

    expect(getBridgerDir(repoRoot)).toBe(path.join(repoRoot, ".bridger"));
    expect(getRepoContextPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "repo-context.json"),
    );
    expect(getFileIndexPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "file-index.json"),
    );
    expect(getGeneratedKnowledgeDocPath(repoRoot, "architecture")).toBe(
      path.join(repoRoot, ".bridger", "generated", "architecture.md"),
    );
    expect(getAgentsGeneratedPath(repoRoot)).toBe(
      path.join(repoRoot, "AGENTS.generated.md"),
    );
    expect(getAgentsMdPath(repoRoot)).toBe(path.join(repoRoot, "AGENTS.md"));
  });
});
