import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  getAgentsGeneratedPath,
  getAgentsMdPath,
  getArtifactsDir,
  getBridgerDir,
  getExportsDir,
  getGraphSummaryPath,
  getFileIndexPath,
  getGeneratedKnowledgeDocPath,
  getMemoryDir,
  getRepoContextPath,
  getRepoGraphPath,
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
      path.join(repoRoot, ".bridger", "artifacts", "repo-context.json"),
    );
    expect(getFileIndexPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "file-index.json"),
    );
    expect(getRepoGraphPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "repo-graph.json"),
    );
    expect(getGraphSummaryPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "graph-summary.json"),
    );
    expect(getArtifactsDir(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts"),
    );
    expect(getMemoryDir(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "memory"),
    );
    expect(getExportsDir(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "exports"),
    );
    expect(getGeneratedKnowledgeDocPath(repoRoot, "architecture")).toBe(
      path.join(repoRoot, ".bridger", "memory", "architecture.md"),
    );
    expect(getAgentsGeneratedPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "exports", "AGENTS.generated.md"),
    );
    expect(getAgentsMdPath(repoRoot)).toBe(path.join(repoRoot, "AGENTS.md"));
  });
});
