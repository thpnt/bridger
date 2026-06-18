import type { RepoGraph, RepoGraphNode } from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";

export function getEntrypoints(graph: RepoGraph): string[] {
  return graph.nodes
    .filter((node) => node.kind === "file")
    .filter(isEntrypointNode)
    .map((node) => normalizeRepoPath(node.path))
    .sort((left, right) => left.localeCompare(right));
}

function isEntrypointNode(node: RepoGraphNode): boolean {
  const path = normalizeRepoPath(node.path).toLowerCase();

  return (
    node.tags.includes("entrypoint-candidate") ||
    isNextEntrypoint(path) ||
    isNodeCliEntrypoint(path) ||
    isPythonEntrypoint(path)
  );
}

function isNextEntrypoint(path: string): boolean {
  return (
    path === "app/page.tsx" ||
    path === "src/app/page.tsx" ||
    /^app\/.+\/page\.tsx$/.test(path) ||
    /^src\/app\/.+\/page\.tsx$/.test(path) ||
    /^app\/.+\/route\.ts$/.test(path) ||
    /^src\/app\/.+\/route\.ts$/.test(path) ||
    /^pages\/.+\.tsx$/.test(path) ||
    /^src\/pages\/.+\.tsx$/.test(path)
  );
}

function isNodeCliEntrypoint(path: string): boolean {
  return (
    path === "index.ts" ||
    path === "index.js" ||
    path === "main.ts" ||
    path === "main.js" ||
    path === "src/index.ts" ||
    path === "src/index.js" ||
    path === "src/main.ts" ||
    path === "src/main.js" ||
    path === "src/cli/index.ts" ||
    path === "src/cli/index.js" ||
    path === "src/cli/cli.ts" ||
    path === "src/cli/cli.js" ||
    path.startsWith("bin/")
  );
}

function isPythonEntrypoint(path: string): boolean {
  return (
    path === "main.py" ||
    path === "app.py" ||
    path === "src/main.py" ||
    path === "src/app.py"
  );
}
