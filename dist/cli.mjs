#!/usr/bin/env node

// src/cli/cli.ts
import { Command as Command3 } from "commander";
import { pathToFileURL } from "url";

// src/cli/commands/inspect.ts
import fs9 from "fs/promises";
import { Command } from "commander";

// src/core/codebase-map/build-codebase-map.ts
import path2 from "path";

// src/core/repo-graph/utils/normalize-path.ts
function normalizeRepoPath(input) {
  if (input === "") {
    return ".";
  }
  const normalized = input.replace(/\\/g, "/").replace(/\/+/g, "/").replace(/^\.\//, "");
  if (normalized === "/") {
    return "/";
  }
  const withoutTrailingSlash = normalized.replace(/\/$/, "");
  return withoutTrailingSlash === "" ? "." : withoutTrailingSlash;
}

// src/core/repo-graph/traversal/build-adjacency-map.ts
function buildAdjacencyMap(graph) {
  const dependenciesByFile = /* @__PURE__ */ new Map();
  const consumersByFile = /* @__PURE__ */ new Map();
  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }
    const path20 = normalizeRepoPath(node.path);
    dependenciesByFile.set(path20, /* @__PURE__ */ new Set());
    consumersByFile.set(path20, /* @__PURE__ */ new Set());
  }
  for (const edge of graph.edges) {
    if (edge.type !== "imports") {
      continue;
    }
    const fromPath = normalizeRepoPath(edge.from);
    const toPath = normalizeRepoPath(edge.to);
    if (!dependenciesByFile.has(fromPath)) {
      dependenciesByFile.set(fromPath, /* @__PURE__ */ new Set());
    }
    if (!consumersByFile.has(toPath)) {
      consumersByFile.set(toPath, /* @__PURE__ */ new Set());
    }
    dependenciesByFile.get(fromPath)?.add(toPath);
    consumersByFile.get(toPath)?.add(fromPath);
  }
  return {
    dependenciesByFile: sortMapValues(dependenciesByFile),
    consumersByFile: sortMapValues(consumersByFile)
  };
}
function traverseAdjacency(input) {
  const startPath = normalizeRepoPath(input.startPath);
  const maxDepth = Math.max(0, Math.floor(input.depth ?? 1));
  if (maxDepth === 0) {
    return [];
  }
  const visited = /* @__PURE__ */ new Set([startPath]);
  const results = /* @__PURE__ */ new Set();
  const queue = [
    { path: startPath, depth: 0 }
  ];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || current.depth >= maxDepth) {
      continue;
    }
    const nextPaths = input.nextPathsByFile.get(current.path) ?? [];
    for (const nextPath of nextPaths) {
      if (visited.has(nextPath)) {
        continue;
      }
      visited.add(nextPath);
      results.add(nextPath);
      queue.push({
        path: nextPath,
        depth: current.depth + 1
      });
    }
  }
  return [...results].sort((a, b) => a.localeCompare(b));
}
function sortMapValues(input) {
  const output = /* @__PURE__ */ new Map();
  for (const [path20, values] of [...input.entries()].sort(
    ([left], [right]) => left.localeCompare(right)
  )) {
    output.set(path20, [...values].sort(
      (left, right) => left.localeCompare(right)
    ));
  }
  return output;
}

// src/core/repo-graph/traversal/get-entrypoints.ts
function getEntrypoints(graph) {
  return graph.nodes.filter((node) => node.kind === "file").filter(isEntrypointNode).map((node) => normalizeRepoPath(node.path)).sort((left, right) => left.localeCompare(right));
}
function isEntrypointNode(node) {
  const path20 = normalizeRepoPath(node.path).toLowerCase();
  return node.tags.includes("entrypoint-candidate") || isNextEntrypoint(path20) || isNodeCliEntrypoint(path20) || isPythonEntrypoint(path20);
}
function isNextEntrypoint(path20) {
  return path20 === "app/page.tsx" || path20 === "src/app/page.tsx" || /^app\/.+\/page\.tsx$/.test(path20) || /^src\/app\/.+\/page\.tsx$/.test(path20) || /^app\/.+\/route\.ts$/.test(path20) || /^src\/app\/.+\/route\.ts$/.test(path20) || /^pages\/.+\.tsx$/.test(path20) || /^src\/pages\/.+\.tsx$/.test(path20);
}
function isNodeCliEntrypoint(path20) {
  return path20 === "index.ts" || path20 === "index.js" || path20 === "main.ts" || path20 === "main.js" || path20 === "src/index.ts" || path20 === "src/index.js" || path20 === "src/main.ts" || path20 === "src/main.js" || path20 === "src/cli/index.ts" || path20 === "src/cli/index.js" || path20 === "src/cli/cli.ts" || path20 === "src/cli/cli.js" || path20.startsWith("bin/");
}
function isPythonEntrypoint(path20) {
  return path20 === "main.py" || path20 === "app.py" || path20 === "src/main.py" || path20 === "src/app.py";
}

// src/core/repo-graph/traversal/get-root-files.ts
function getRootFiles(graph) {
  const rootFiles = /* @__PURE__ */ new Set();
  const configFiles = /* @__PURE__ */ new Set();
  const docsFiles = /* @__PURE__ */ new Set();
  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }
    const path20 = normalizeRepoPath(node.path);
    const lowerPath = path20.toLowerCase();
    if (isRootFile(path20)) {
      rootFiles.add(path20);
    }
    if (isConfigFileNode(node, lowerPath)) {
      configFiles.add(path20);
    }
    if (isDocsFileNode(node, lowerPath)) {
      docsFiles.add(path20);
    }
  }
  return {
    rootFiles: sortPaths(rootFiles),
    configFiles: sortPaths(configFiles),
    docsFiles: sortPaths(docsFiles)
  };
}
function isRootFile(path20) {
  return !path20.includes("/");
}
function isConfigFileNode(node, lowerPath) {
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;
  return node.tags.includes("config") || lowerPath.startsWith(".github/") || fileName === "package.json" || fileName === "tsconfig.json" || fileName === "jsconfig.json" || fileName === "components.json" || fileName === "pyproject.toml" || fileName === "ruff.toml" || fileName === "mypy.ini" || fileName === "pytest.ini" || fileName === "dockerfile" || fileName === "docker-compose.yml" || fileName === ".env.example" || fileName.startsWith("next.config.") || fileName.startsWith("vite.config.") || fileName.startsWith("vitest.config.") || fileName.startsWith("jest.config.") || fileName.startsWith("playwright.config.") || fileName.startsWith("tailwind.config.") || fileName.startsWith("postcss.config.") || fileName.startsWith("eslint.config.") || fileName.startsWith("prettier.config.");
}
function isDocsFileNode(node, lowerPath) {
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;
  return node.tags.includes("docs") || lowerPath.startsWith("docs/") || fileName === "readme.md" || fileName === "agents.md" || fileName === "claude.md" || fileName.endsWith(".md");
}
function sortPaths(paths) {
  return [...paths].sort((left, right) => left.localeCompare(right));
}

// src/core/repo-graph/traversal/get-graph-file-ranks.ts
function getGraphFileRanks(graph) {
  const adjacencyMap = buildAdjacencyMap(graph);
  const entrypoints = new Set(getEntrypoints(graph));
  const rootFiles = getRootFiles(graph);
  const configFiles = new Set(rootFiles.configFiles);
  const docsFiles = new Set(rootFiles.docsFiles);
  return graph.nodes.filter((node) => node.kind === "file").map((node) => {
    const path20 = normalizeRepoPath(node.path);
    const fanOut = adjacencyMap.dependenciesByFile.get(path20)?.length ?? 0;
    const fanIn = adjacencyMap.consumersByFile.get(path20)?.length ?? 0;
    return {
      path: path20,
      fanIn,
      fanOut,
      isLeaf: fanOut === 0,
      isIsolated: fanIn === 0 && fanOut === 0,
      isEntrypoint: entrypoints.has(path20),
      isConfig: configFiles.has(path20),
      isDocs: docsFiles.has(path20)
    };
  }).sort((left, right) => left.path.localeCompare(right.path));
}

// src/core/codebase-map/build-clusters.ts
var MAX_CENTRAL_FILES = 5;
var AREA_DIRECTORIES = /* @__PURE__ */ new Set([
  "core",
  "domains",
  "features",
  "modules",
  "packages"
]);
var SOURCE_DIRECTORIES = /* @__PURE__ */ new Set([
  "api",
  "app",
  "cli",
  "components",
  "db",
  "lib",
  "pages",
  "routes",
  "server",
  "shared"
]);
function getPathClusterIdentity(file) {
  const segments = file.path.split("/");
  const roles = new Set(file.roles);
  if (roles.has("test")) {
    return identityForSpecialPath(file.path, "tests", "test");
  }
  if (roles.has("fixture")) {
    return identityForSpecialPath(file.path, "fixtures", "test");
  }
  if (roles.has("docs")) {
    return { id: "docs", rootPath: "docs", kind: "docs" };
  }
  if (roles.has("script") || segments[0] === "scripts" || segments[0] === "jobs") {
    const rootPath = segments[0] === "jobs" ? "jobs" : "scripts";
    return { id: slugPath(rootPath), rootPath, kind: "scripts" };
  }
  if (roles.has("config") || roles.has("project-config") || roles.has("lockfile")) {
    return { id: "config", rootPath: "config/root", kind: "config" };
  }
  if (segments[0] === "src") {
    const second = segments[1];
    let depth = 2;
    if (second && AREA_DIRECTORIES.has(second) && segments[2]) {
      depth = 3;
    } else if (!second || !SOURCE_DIRECTORIES.has(second) && segments.length < 3) {
      depth = 1;
    }
    const rootPath = segments.slice(0, depth).join("/");
    return { id: slugPath(rootPath), rootPath, kind: "source" };
  }
  if (segments[0] && SOURCE_DIRECTORIES.has(segments[0])) {
    const rootPath = segments[0];
    return { id: slugPath(rootPath), rootPath, kind: "source" };
  }
  if (roles.has("source")) {
    return { id: "root", rootPath: "root", kind: "source" };
  }
  return { id: "unassigned", rootPath: "unassigned", kind: "unknown" };
}
function buildClusters(input) {
  const identityByFile = /* @__PURE__ */ new Map();
  const filesByCluster = /* @__PURE__ */ new Map();
  for (const file of input.files) {
    const identity = getPathClusterIdentity(file);
    identityByFile.set(file.path, identity);
    const clusterFiles = filesByCluster.get(identity.id) ?? [];
    clusterFiles.push(file);
    filesByCluster.set(identity.id, clusterFiles);
  }
  const dependencyCounts = buildRelationCounts(input.repoGraph, identityByFile);
  const consumerCounts = reverseRelationCounts(dependencyCounts);
  const entrypointPaths = new Set(
    input.entrypoints.map((entrypoint) => entrypoint.path)
  );
  const highFanInPaths = new Set(
    input.graphSummary.highFanInFiles.map((file) => file.path)
  );
  const highFanOutPaths = new Set(
    input.graphSummary.highFanOutFiles.map((file) => file.path)
  );
  const unresolvedByCluster = getUnresolvedCounts(
    input.repoGraph,
    identityByFile
  );
  return [...filesByCluster.entries()].map(([clusterId, files]) => {
    const sortedFiles = files.sort(
      (left, right) => left.path.localeCompare(right.path)
    );
    const identity = identityByFile.get(sortedFiles[0].path);
    const centralFiles = getCentralFiles({
      files: sortedFiles,
      entrypointPaths,
      highFanInPaths,
      highFanOutPaths
    });
    const roles = countRoles(sortedFiles);
    const warnings = [];
    if (identity.kind === "source" && !sortedFiles.some((file) => file.roles.includes("source"))) {
      warnings.push("Source cluster contains no source-role files.");
    }
    const unresolvedCount = unresolvedByCluster.get(clusterId) ?? 0;
    if (unresolvedCount > 0) {
      warnings.push(
        `Cluster has ${unresolvedCount} unresolved import${unresolvedCount === 1 ? "" : "s"}.`
      );
    }
    return {
      id: clusterId,
      title: titleForPath(identity.rootPath),
      rootPath: identity.rootPath,
      kind: identity.kind,
      files: sortedFiles.map((file) => file.path),
      roles,
      entrypoints: sortedFiles.filter((file) => entrypointPaths.has(file.path)).map((file) => file.path),
      centralFiles,
      tests: sortedFiles.filter((file) => file.isTest).map((file) => file.path),
      fixtures: sortedFiles.filter((file) => file.isFixture).map((file) => file.path),
      dependencies: formatRelations(dependencyCounts.get(clusterId)),
      consumers: formatRelations(consumerCounts.get(clusterId)),
      confidence: "inferred",
      reasons: [`Grouped by path prefix ${identity.rootPath}.`],
      warnings
    };
  }).sort((left, right) => left.id.localeCompare(right.id));
}
function identityForSpecialPath(filePath, fallbackRoot, kind) {
  const segments = filePath.split("/");
  const markerIndex = segments.findIndex(
    (segment) => ["test", "tests", "__tests__", "fixture", "fixtures"].includes(
      segment.toLowerCase()
    )
  );
  const rootPath = markerIndex >= 0 ? segments.slice(0, markerIndex + 1).join("/") : fallbackRoot;
  return { id: slugPath(rootPath), rootPath, kind };
}
function buildRelationCounts(graph, identityByFile) {
  const result = /* @__PURE__ */ new Map();
  for (const edge of graph.edges) {
    if (edge.type !== "imports") {
      continue;
    }
    const from = identityByFile.get(edge.from);
    const to = identityByFile.get(edge.to);
    if (!from || !to || from.id === to.id) {
      continue;
    }
    const byTarget = result.get(from.id) ?? /* @__PURE__ */ new Map();
    const counts = byTarget.get(to.id) ?? {
      edges: /* @__PURE__ */ new Set(),
      sourceFiles: /* @__PURE__ */ new Set()
    };
    counts.edges.add(`${edge.from}\0${edge.to}`);
    counts.sourceFiles.add(edge.from);
    byTarget.set(to.id, counts);
    result.set(from.id, byTarget);
  }
  return result;
}
function reverseRelationCounts(relations) {
  const reversed = /* @__PURE__ */ new Map();
  for (const [fromCluster, targets] of relations) {
    for (const [toCluster, counts] of targets) {
      const consumers = reversed.get(toCluster) ?? /* @__PURE__ */ new Map();
      consumers.set(fromCluster, counts);
      reversed.set(toCluster, consumers);
    }
  }
  return reversed;
}
function formatRelations(relations) {
  if (!relations) {
    return [];
  }
  return [...relations.entries()].map(([clusterId, counts]) => ({
    clusterId,
    fileCount: counts.edges.size,
    reasons: [
      formatRelationReason(counts)
    ]
  })).sort((left, right) => left.clusterId.localeCompare(right.clusterId));
}
function formatRelationReason(counts) {
  const fileLabel = counts.sourceFiles.size === 1 ? "file creates" : "files create";
  const importLabel = counts.edges.size === 1 ? "import" : "imports";
  return `${counts.sourceFiles.size} ${fileLabel} ${counts.edges.size} cross-cluster ${importLabel}.`;
}
function getCentralFiles(input) {
  return input.files.filter((file) => file.isCentral || input.entrypointPaths.has(file.path)).sort(
    (left, right) => right.fanIn - left.fanIn || right.fanOut - left.fanOut || left.path.localeCompare(right.path)
  ).slice(0, MAX_CENTRAL_FILES).map((file) => {
    const reasons = [];
    if (file.fanIn > 0) reasons.push("High fan-in within repo.");
    if (file.fanOut > 0) reasons.push("High fan-out within repo.");
    if (input.highFanInPaths.has(file.path)) {
      reasons.push("Listed in graph summary high fan-in files.");
    }
    if (input.highFanOutPaths.has(file.path)) {
      reasons.push("Listed in graph summary high fan-out files.");
    }
    if (input.entrypointPaths.has(file.path)) {
      reasons.push("Entrypoint candidate.");
    }
    return { path: file.path, fanIn: file.fanIn, fanOut: file.fanOut, reasons };
  });
}
function countRoles(files) {
  const counts = /* @__PURE__ */ new Map();
  for (const role of files.flatMap((file) => file.roles)) {
    counts.set(role, (counts.get(role) ?? 0) + 1);
  }
  return Object.fromEntries(
    [...counts.entries()].sort(
      ([left], [right]) => left.localeCompare(right)
    )
  );
}
function getUnresolvedCounts(graph, identityByFile) {
  const counts = /* @__PURE__ */ new Map();
  for (const diagnostic of graph.diagnostics) {
    if (diagnostic.code !== "unresolved-import" || !diagnostic.file) {
      continue;
    }
    const identity = identityByFile.get(diagnostic.file);
    if (identity) {
      counts.set(identity.id, (counts.get(identity.id) ?? 0) + 1);
    }
  }
  return counts;
}
function slugPath(value) {
  return value.toLowerCase().replaceAll("/", "-").replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "") || "unassigned";
}
function titleForPath(value) {
  return value === "root" ? "Root" : value.split("/").map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1)).join(" / ");
}

// src/core/codebase-map/models/codebase-map.ts
import { z as z3 } from "zod";

// src/core/models/file-index.ts
import { z as z2 } from "zod";

// src/core/models/path.ts
import path from "path";
import { z } from "zod";
var AbsolutePathSchema = z.string().min(1).refine((value) => path.isAbsolute(value), {
  message: "Expected an absolute path"
}).transform((value) => path.normalize(value));
var RepoRelativePathSchema = z.string().min(1).refine((value) => !path.isAbsolute(value), {
  message: "Expected a repo-relative path, not an absolute path"
}).refine((value) => !value.startsWith(".."), {
  message: "Repo-relative path must not escape the repo root"
}).refine((value) => !value.includes(`..${path.sep}`), {
  message: "Repo-relative path must not contain parent traversal"
}).transform((value) => value.replaceAll("\\", "/"));

// src/core/models/file-index.ts
var FileIndexLanguageSchema = z2.enum([
  "typescript",
  "javascript",
  "python",
  "markdown",
  "json",
  "yaml",
  "css",
  "html",
  "shell",
  "unknown"
]);
var FileRoleSchema = z2.enum([
  "source",
  "test",
  "fixture",
  "docs",
  "config",
  "project-config",
  "fixture-config",
  "lockfile",
  "planning-doc",
  "generated",
  "entrypoint-candidate",
  "command",
  "route",
  "api-route",
  "script",
  "model",
  "schema",
  "type",
  "service",
  "utility",
  "component",
  "builder",
  "generator",
  "resolver",
  "extractor",
  "reader",
  "writer",
  "migration"
]);
var ConfidenceSchema = z2.enum(["observed", "inferred", "ambiguous"]);
var IncludeReasonSchema = z2.enum([
  "source",
  "project-metadata",
  "documentation",
  "test",
  "fixture",
  "config",
  "script",
  "unknown"
]);
var SkipReasonSchema = z2.enum([
  "ignored",
  "sensitive",
  "binary",
  "too-large",
  "generated",
  "lockfile",
  "unsupported",
  "noise-directory"
]);
var FileSignalSchema = z2.object({
  kind: z2.enum([
    "framework",
    "schema",
    "model",
    "validation",
    "cli",
    "testing",
    "database",
    "frontend",
    "entrypoint",
    "unknown"
  ]),
  source: z2.enum(["import", "path", "package-json", "extension"]),
  value: z2.string().min(1),
  confidence: ConfidenceSchema,
  reason: z2.string().min(1)
});
var FileIndexEntrySchema = z2.object({
  path: RepoRelativePathSchema,
  extension: z2.string().optional(),
  sizeBytes: z2.number(),
  language: FileIndexLanguageSchema,
  roles: z2.array(FileRoleSchema),
  confidence: ConfidenceSchema,
  includeReason: IncludeReasonSchema,
  signals: z2.array(FileSignalSchema),
  reason: z2.string().optional(),
  tags: z2.array(z2.string())
});
var SkippedFileSchema = z2.object({
  path: RepoRelativePathSchema,
  reason: SkipReasonSchema,
  detail: z2.string().optional()
});
var ScanWarningSchema = z2.object({
  code: z2.string().min(1),
  message: z2.string().min(1),
  filePath: RepoRelativePathSchema.optional(),
  severity: z2.enum(["info", "warning"])
});
var FileIndexStatsSchema = z2.object({
  totalFilesDiscovered: z2.number().int().nonnegative(),
  includedFileCount: z2.number().int().nonnegative(),
  skippedFileCount: z2.number().int().nonnegative(),
  totalIncludedBytes: z2.number().int().nonnegative(),
  byLanguage: z2.partialRecord(
    FileIndexLanguageSchema,
    z2.number().int().nonnegative()
  ),
  byRole: z2.partialRecord(FileRoleSchema, z2.number().int().nonnegative()),
  bySkipReason: z2.partialRecord(
    SkipReasonSchema,
    z2.number().int().nonnegative()
  )
});
var FileIndexSchema = z2.object({
  schemaVersion: z2.literal(2),
  generatedAt: z2.iso.datetime(),
  files: z2.array(FileIndexEntrySchema),
  skippedFiles: z2.array(SkippedFileSchema),
  warnings: z2.array(ScanWarningSchema),
  stats: FileIndexStatsSchema
});

// src/core/codebase-map/models/codebase-map.ts
var CountRecordSchema = z3.record(z3.string(), z3.number().int().nonnegative());
var EntrypointKindSchema = z3.enum([
  "node-cli",
  "cli-command",
  "package-bin",
  "next-page",
  "next-route",
  "vite-react",
  "python-script",
  "fastapi-app",
  "django-app",
  "script",
  "job",
  "unknown"
]);
var EntrypointCandidateSchema = z3.object({
  path: z3.string().min(1),
  kind: EntrypointKindSchema,
  framework: z3.string().min(1).optional(),
  confidence: ConfidenceSchema,
  reasons: z3.array(z3.string().min(1))
});
var ClusterCentralFileSchema = z3.object({
  path: z3.string().min(1),
  fanIn: z3.number().int().nonnegative(),
  fanOut: z3.number().int().nonnegative(),
  reasons: z3.array(z3.string().min(1))
});
var ClusterRelationSchema = z3.object({
  clusterId: z3.string().min(1),
  fileCount: z3.number().int().positive(),
  reasons: z3.array(z3.string().min(1))
});
var CodebaseClusterSchema = z3.object({
  id: z3.string().min(1),
  title: z3.string().min(1),
  rootPath: z3.string().min(1),
  kind: z3.enum([
    "source",
    "test",
    "docs",
    "config",
    "scripts",
    "mixed",
    "unknown"
  ]),
  files: z3.array(z3.string().min(1)),
  roles: CountRecordSchema,
  entrypoints: z3.array(z3.string().min(1)),
  centralFiles: z3.array(ClusterCentralFileSchema),
  tests: z3.array(z3.string().min(1)),
  fixtures: z3.array(z3.string().min(1)),
  dependencies: z3.array(ClusterRelationSchema),
  consumers: z3.array(ClusterRelationSchema),
  confidence: ConfidenceSchema,
  reasons: z3.array(z3.string().min(1)),
  warnings: z3.array(z3.string().min(1))
});
var CodebaseMapFileSchema = z3.object({
  path: z3.string().min(1),
  language: FileIndexLanguageSchema,
  roles: z3.array(FileRoleSchema),
  signals: z3.array(FileSignalSchema),
  clusterId: z3.string().min(1).optional(),
  fanIn: z3.number().int().nonnegative(),
  fanOut: z3.number().int().nonnegative(),
  isCentral: z3.boolean(),
  isEntrypoint: z3.boolean(),
  isTest: z3.boolean(),
  isFixture: z3.boolean()
});
var CodebaseMapStatsSchema = z3.object({
  fileCount: z3.number().int().nonnegative(),
  sourceFileCount: z3.number().int().nonnegative(),
  testFileCount: z3.number().int().nonnegative(),
  fixtureFileCount: z3.number().int().nonnegative(),
  docsFileCount: z3.number().int().nonnegative(),
  configFileCount: z3.number().int().nonnegative(),
  clusterCount: z3.number().int().nonnegative(),
  entrypointCount: z3.number().int().nonnegative(),
  centralFileCount: z3.number().int().nonnegative(),
  unresolvedImportCount: z3.number().int().nonnegative()
});
var CodebaseSignalSummarySchema = z3.object({
  frameworks: CountRecordSchema,
  schemas: CountRecordSchema,
  validation: CountRecordSchema,
  cli: CountRecordSchema,
  testing: CountRecordSchema,
  database: CountRecordSchema
});
var UnresolvedImportSummarySchema = z3.object({
  count: z3.number().int().nonnegative(),
  byFile: z3.array(
    z3.object({
      path: z3.string().min(1),
      count: z3.number().int().positive()
    })
  )
});
var CodebaseMapSchema = z3.object({
  schemaVersion: z3.literal(1),
  generatedAt: z3.iso.datetime(),
  repo: z3.object({
    name: z3.string().min(1),
    packageManager: z3.string().min(1).optional(),
    detectedStack: z3.array(z3.string().min(1))
  }),
  stats: CodebaseMapStatsSchema,
  entrypoints: z3.array(EntrypointCandidateSchema),
  clusters: z3.array(CodebaseClusterSchema),
  files: z3.array(CodebaseMapFileSchema),
  signals: CodebaseSignalSummarySchema,
  unresolvedImports: UnresolvedImportSummarySchema,
  warnings: z3.array(z3.string().min(1))
});

// src/core/codebase-map/build-codebase-map.ts
function buildCodebaseMap(input) {
  const entrypoints = buildEntrypoints(input.fileIndex, input.graphSummary);
  const entrypointPaths = new Set(
    entrypoints.map((entrypoint) => entrypoint.path)
  );
  const ranks = new Map(
    getGraphFileRanks(input.repoGraph).map((rank) => [rank.path, rank])
  );
  const summaryCentralPaths = /* @__PURE__ */ new Set([
    ...input.graphSummary.highFanInFiles.map((file) => file.path),
    ...input.graphSummary.highFanOutFiles.map((file) => file.path)
  ]);
  const files = input.fileIndex.files.map((file) => {
    const roles = [...file.roles ?? []].sort(
      (left, right) => left.localeCompare(right)
    );
    const rank = ranks.get(file.path);
    const record = {
      path: file.path,
      language: file.language ?? "unknown",
      roles,
      signals: sortSignals(file.signals ?? []),
      fanIn: rank?.fanIn ?? 0,
      fanOut: rank?.fanOut ?? 0,
      isCentral: summaryCentralPaths.has(file.path),
      isEntrypoint: entrypointPaths.has(file.path),
      isTest: roles.includes("test"),
      isFixture: roles.includes("fixture")
    };
    return { ...record, clusterId: getPathClusterIdentity(record).id };
  }).sort((left, right) => left.path.localeCompare(right.path));
  const clusters = buildClusters({
    files,
    entrypoints,
    repoGraph: input.repoGraph,
    graphSummary: input.graphSummary
  });
  const unresolvedImports = summarizeUnresolvedImports(input.repoGraph);
  const warnings = buildWarnings({
    files,
    entrypoints,
    unresolvedImportCount: unresolvedImports.count
  });
  const detectedStack = getDetectedStack(input.repoContext);
  return CodebaseMapSchema.parse({
    schemaVersion: 1,
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    repo: {
      name: path2.basename(input.repoRoot),
      packageManager: valueOrUndefined(input.repoContext.stack.packageManager),
      detectedStack
    },
    stats: {
      fileCount: files.length,
      sourceFileCount: files.filter(
        (file) => file.roles.includes("source") && !file.isTest && !file.isFixture
      ).length,
      testFileCount: countFilesWithRole(files, "test"),
      fixtureFileCount: countFilesWithRole(files, "fixture"),
      docsFileCount: countFilesWithRole(files, "docs"),
      configFileCount: files.filter(
        (file) => file.roles.includes("config") || file.roles.includes("project-config")
      ).length,
      clusterCount: clusters.length,
      entrypointCount: entrypoints.length,
      centralFileCount: files.filter((file) => file.isCentral).length,
      unresolvedImportCount: unresolvedImports.count
    },
    entrypoints,
    clusters,
    files,
    signals: summarizeSignals(files),
    unresolvedImports,
    warnings
  });
}
function buildEntrypoints(fileIndex, graphSummary) {
  const fileByPath = new Map(
    fileIndex.files.map((file) => [file.path, file])
  );
  const candidatePaths = new Set(graphSummary.entrypoints);
  for (const file of fileIndex.files) {
    if (file.roles?.includes("entrypoint-candidate") || file.signals?.some((signal) => signal.kind === "entrypoint")) {
      candidatePaths.add(file.path);
    }
  }
  return [...candidatePaths].sort((left, right) => left.localeCompare(right)).map(
    (candidatePath) => toEntrypointCandidate(candidatePath, fileByPath.get(candidatePath))
  );
}
function toEntrypointCandidate(candidatePath, file) {
  const lowerPath = candidatePath.toLowerCase();
  const signals = file?.signals ?? [];
  const packageBin = signals.find(
    (signal) => signal.kind === "entrypoint" && signal.value === "package-bin"
  );
  const frameworkSignals = new Set(
    signals.filter((signal) => signal.kind === "framework").map((signal) => signal.value)
  );
  const hasCliSignal = signals.some((signal) => signal.kind === "cli");
  let kind = "unknown";
  let framework;
  if (packageBin) {
    kind = "package-bin";
  } else if (/\/page\.[jt]sx?$/.test(lowerPath)) {
    kind = "next-page";
    framework = "next";
  } else if (/\/route\.[jt]s$/.test(lowerPath)) {
    kind = "next-route";
    framework = "next";
  } else if (frameworkSignals.has("fastapi")) {
    kind = "fastapi-app";
    framework = "fastapi";
  } else if (frameworkSignals.has("django")) {
    kind = "django-app";
    framework = "django";
  } else if (lowerPath.includes("/cli/") || lowerPath.startsWith("cli/")) {
    kind = "cli-command";
  } else if (hasCliSignal) {
    kind = "node-cli";
  } else if (lowerPath.includes("/jobs/") || lowerPath.startsWith("jobs/")) {
    kind = "job";
  } else if (lowerPath.startsWith("scripts/")) {
    kind = "script";
  } else if (lowerPath.endsWith("manage.py") || lowerPath.endsWith("asgi.py") || lowerPath.endsWith("wsgi.py")) {
    kind = "django-app";
    framework = "django";
  } else if (lowerPath.endsWith(".py")) {
    kind = "python-script";
  } else if (frameworkSignals.has("react") && /\/(main|index)\.[jt]sx?$/.test(`/${lowerPath}`)) {
    kind = "vite-react";
    framework = "react";
  }
  const entrypointSignals = signals.filter(
    (signal) => signal.kind === "entrypoint"
  );
  const reasons = entrypointSignals.length > 0 ? [...new Set(entrypointSignals.map((signal) => signal.reason))].sort() : ["Listed in graph summary entrypoint candidates."];
  return {
    path: candidatePath,
    kind,
    ...framework ? { framework } : {},
    confidence: packageBin ? "observed" : entrypointSignals[0]?.confidence ?? "inferred",
    reasons
  };
}
function summarizeSignals(files) {
  const categories = {
    framework: /* @__PURE__ */ new Map(),
    schema: /* @__PURE__ */ new Map(),
    validation: /* @__PURE__ */ new Map(),
    cli: /* @__PURE__ */ new Map(),
    testing: /* @__PURE__ */ new Map(),
    database: /* @__PURE__ */ new Map()
  };
  for (const signal of files.flatMap((file) => file.signals)) {
    if (!(signal.kind in categories)) continue;
    const counts = categories[signal.kind];
    counts.set(signal.value, (counts.get(signal.value) ?? 0) + 1);
  }
  return {
    frameworks: sortedRecord(categories.framework),
    schemas: sortedRecord(categories.schema),
    validation: sortedRecord(categories.validation),
    cli: sortedRecord(categories.cli),
    testing: sortedRecord(categories.testing),
    database: sortedRecord(categories.database)
  };
}
function summarizeUnresolvedImports(graph) {
  const counts = /* @__PURE__ */ new Map();
  for (const diagnostic of graph.diagnostics) {
    if (diagnostic.code === "unresolved-import" && diagnostic.file) {
      counts.set(diagnostic.file, (counts.get(diagnostic.file) ?? 0) + 1);
    }
  }
  return {
    count: [...counts.values()].reduce((total, count) => total + count, 0),
    byFile: [...counts.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([filePath, count]) => ({ path: filePath, count }))
  };
}
function buildWarnings(input) {
  const warnings = [];
  if (input.entrypoints.length === 0) warnings.push("No entrypoints detected.");
  if (!input.files.some((file) => file.roles.includes("source"))) {
    warnings.push("No source files detected.");
  }
  if (!input.files.some((file) => file.isTest)) {
    warnings.push("No tests detected.");
  }
  if (input.unresolvedImportCount > 0) {
    const importLabel = input.unresolvedImportCount === 1 ? "import" : "imports";
    warnings.push(
      `${input.unresolvedImportCount} unresolved ${importLabel} detected.`
    );
  }
  const unassignedCount = input.files.filter(
    (file) => file.clusterId === "unassigned"
  ).length;
  if (input.files.length > 0 && unassignedCount / input.files.length > 0.25) {
    warnings.push(
      `${unassignedCount} files could not be assigned to a specific cluster.`
    );
  }
  return warnings;
}
function getDetectedStack(repoContext) {
  const stack = repoContext.stack;
  return [
    ...new Set(
      [
        stack.framework,
        stack.language,
        ...stack.styling,
        ...stack.validation,
        ...stack.database,
        ...stack.testFramework
      ].filter((value) => value.length > 0 && value !== "unknown")
    )
  ].sort();
}
function countFilesWithRole(files, role) {
  return files.filter((file) => file.roles.includes(role)).length;
}
function sortedRecord(counts) {
  return Object.fromEntries(
    [...counts.entries()].sort(
      ([left], [right]) => left.localeCompare(right)
    )
  );
}
function sortSignals(signals) {
  return [...signals].sort(
    (left, right) => left.kind.localeCompare(right.kind) || left.value.localeCompare(right.value) || left.source.localeCompare(right.source)
  );
}
function valueOrUndefined(value) {
  return value && value !== "unknown" ? value : void 0;
}

// src/core/repo-scanner/build-file-index.ts
import fg from "fast-glob";
import fs3 from "fs-extra";
import path6 from "path";

// src/core/repo-scanner/file-classification.ts
import path4 from "path";

// src/core/repo-scanner/file-signals.ts
import fs from "fs-extra";
import path3 from "path";

// src/core/repo-graph/extractors/dependency-extractor.ts
import { z as z4 } from "zod";
var DependencyExtractorLanguageSchema = z4.enum([
  "typescript-javascript",
  "python"
]);
var DependencyExtractorSourceSchema = z4.enum([
  "typescript-js-imports",
  "python-imports"
]);
var ExtractedImportKindSchema = z4.enum([
  "static",
  "dynamic",
  "require",
  "reexport"
]);
var DependencyExtractionInputSchema = z4.object({
  filePath: z4.string().min(1),
  content: z4.string()
});
var ExtractedImportSchema = z4.object({
  specifier: z4.string().min(1),
  kind: ExtractedImportKindSchema,
  source: DependencyExtractorSourceSchema,
  line: z4.number().int().positive().optional()
});

// src/core/repo-graph/extractors/python-import-extractor.ts
var PYTHON_EXTENSIONS = [".py"];
var IMPORT_REGEX = /^import\s+(.+)$/;
var FROM_IMPORT_REGEX = /^from\s+([.\w]+)\s+import\s+(.+)$/;
var pythonImportExtractor = {
  language: "python",
  extensions: PYTHON_EXTENSIONS,
  source: "python-imports",
  extractImports(input) {
    return extractPythonImports(input.content);
  }
};
function extractPythonImports(content) {
  const imports = [];
  const seen = /* @__PURE__ */ new Set();
  const lines = content.split(/\r?\n/);
  lines.forEach((rawLine, index) => {
    const lineNumber = index + 1;
    const line = stripInlineComment(rawLine).trim();
    if (!line) {
      return;
    }
    collectImportLine({
      line,
      lineNumber,
      imports,
      seen
    });
    collectFromImportLine({
      line,
      lineNumber,
      imports,
      seen
    });
  });
  return imports;
}
function collectImportLine(input) {
  const match = input.line.match(IMPORT_REGEX);
  if (!match?.[1]) {
    return;
  }
  for (const rawModuleName of match[1].split(",")) {
    const moduleName = stripAlias(rawModuleName.trim());
    if (!isValidPythonModuleSpecifier(moduleName)) {
      continue;
    }
    addImport({
      specifier: moduleName,
      lineNumber: input.lineNumber,
      imports: input.imports,
      seen: input.seen
    });
  }
}
function collectFromImportLine(input) {
  const match = input.line.match(FROM_IMPORT_REGEX);
  if (!match?.[1] || !match[2]) {
    return;
  }
  const moduleName = match[1].trim();
  const importedNames = match[2].split(",");
  if (!isValidPythonModuleSpecifier(moduleName)) {
    return;
  }
  for (const rawImportedName of importedNames) {
    const importedName = stripAlias(rawImportedName.trim());
    if (!isValidPythonImportedName(importedName)) {
      continue;
    }
    addImport({
      specifier: buildFromImportSpecifier(moduleName, importedName),
      lineNumber: input.lineNumber,
      imports: input.imports,
      seen: input.seen
    });
  }
}
function addImport(input) {
  const key = `${input.specifier}\0${input.lineNumber}`;
  if (input.seen.has(key)) {
    return;
  }
  input.seen.add(key);
  input.imports.push(
    ExtractedImportSchema.parse({
      specifier: input.specifier,
      kind: "static",
      source: "python-imports",
      line: input.lineNumber
    })
  );
}
function stripAlias(value) {
  return value.split(/\s+as\s+/i)[0]?.trim() ?? "";
}
function stripInlineComment(line) {
  const trimmed = line.trimStart();
  if (trimmed.startsWith("#")) {
    return "";
  }
  const commentIndex = line.indexOf("#");
  if (commentIndex === -1) {
    return line;
  }
  return line.slice(0, commentIndex);
}
function buildFromImportSpecifier(moduleName, importedName) {
  if (importedName === "*") {
    return moduleName;
  }
  if (moduleName === ".") {
    return `.${importedName}`;
  }
  if (moduleName === "..") {
    return `..${importedName}`;
  }
  return `${moduleName}.${importedName}`;
}
function isValidPythonModuleSpecifier(value) {
  return /^\.+$/.test(value) || /^\.*[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$/.test(value);
}
function isValidPythonImportedName(value) {
  return value === "*" || /^[A-Za-z_][\w]*$/.test(value);
}

// src/core/repo-graph/extractors/typescript-js-import-extractor.ts
var TYPESCRIPT_JS_EXTENSIONS = [
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs"
];
var STATIC_IMPORT_REGEX = /\bimport\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']/g;
var REEXPORT_REGEX = /\bexport\s+(?:type\s+)?(?:\*|\{[\s\S]*?\})\s+from\s+["']([^"']+)["']/g;
var REQUIRE_REGEX = /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g;
var DYNAMIC_IMPORT_REGEX = /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g;
var typescriptJsImportExtractor = {
  language: "typescript-javascript",
  extensions: TYPESCRIPT_JS_EXTENSIONS,
  source: "typescript-js-imports",
  extractImports(input) {
    return extractTypeScriptJsImports(input.content);
  }
};
function extractTypeScriptJsImports(content) {
  const imports = [];
  const seen = /* @__PURE__ */ new Set();
  collectMatches({
    content,
    regex: STATIC_IMPORT_REGEX,
    kind: "static",
    imports,
    seen
  });
  collectMatches({
    content,
    regex: REEXPORT_REGEX,
    kind: "reexport",
    imports,
    seen
  });
  collectMatches({
    content,
    regex: REQUIRE_REGEX,
    kind: "require",
    imports,
    seen
  });
  collectMatches({
    content,
    regex: DYNAMIC_IMPORT_REGEX,
    kind: "dynamic",
    imports,
    seen
  });
  return imports;
}
function collectMatches(input) {
  input.regex.lastIndex = 0;
  for (const match of input.content.matchAll(input.regex)) {
    const specifier = match[1];
    if (!specifier || isCommentedOutLine(input.content, match.index ?? 0)) {
      continue;
    }
    const line = getLineNumber(input.content, match.index ?? 0);
    const key = `${input.kind}\0${specifier}\0${line}`;
    if (input.seen.has(key)) {
      continue;
    }
    input.seen.add(key);
    input.imports.push(
      ExtractedImportSchema.parse({
        specifier,
        kind: input.kind,
        source: "typescript-js-imports",
        line
      })
    );
  }
}
function getLineNumber(content, index) {
  return content.slice(0, index).split("\n").length;
}
function isCommentedOutLine(content, index) {
  const lineStart = content.lastIndexOf("\n", index) + 1;
  const lineEnd = content.indexOf("\n", index);
  const line = lineEnd === -1 ? content.slice(lineStart) : content.slice(lineStart, lineEnd);
  return line.trimStart().startsWith("//");
}

// src/core/repo-scanner/file-signals.ts
var MAX_SIGNAL_SCAN_FILE_BYTES = 25e4;
var SIGNALS_BY_PACKAGE = {
  zod: [
    { kind: "schema", value: "zod", reason: "Imports zod schema tooling." },
    {
      kind: "validation",
      value: "zod",
      reason: "Imports zod validation tooling."
    }
  ],
  pydantic: [
    {
      kind: "schema",
      value: "pydantic",
      reason: "Imports Pydantic schema tooling."
    },
    {
      kind: "model",
      value: "pydantic",
      reason: "Imports Pydantic model tooling."
    },
    {
      kind: "validation",
      value: "pydantic",
      reason: "Imports Pydantic validation tooling."
    }
  ],
  fastapi: [
    {
      kind: "framework",
      value: "fastapi",
      reason: "Imports FastAPI framework APIs."
    }
  ],
  django: [
    {
      kind: "framework",
      value: "django",
      reason: "Imports Django framework APIs."
    }
  ],
  react: [
    {
      kind: "frontend",
      value: "react",
      reason: "Imports React frontend APIs."
    },
    {
      kind: "framework",
      value: "react",
      reason: "Imports React framework APIs."
    }
  ],
  next: [
    {
      kind: "framework",
      value: "next",
      reason: "Imports Next.js framework APIs."
    }
  ],
  commander: [
    {
      kind: "cli",
      value: "commander",
      reason: "Imports Commander CLI APIs."
    }
  ],
  cac: [{ kind: "cli", value: "cac", reason: "Imports CAC CLI APIs." }],
  click: [{ kind: "cli", value: "click", reason: "Imports Click CLI APIs." }],
  typer: [{ kind: "cli", value: "typer", reason: "Imports Typer CLI APIs." }],
  prisma: [
    {
      kind: "database",
      value: "prisma",
      reason: "Imports Prisma database APIs."
    },
    {
      kind: "schema",
      value: "prisma",
      reason: "Imports Prisma schema APIs."
    }
  ],
  drizzle: [
    {
      kind: "database",
      value: "drizzle",
      reason: "Imports Drizzle database APIs."
    },
    {
      kind: "schema",
      value: "drizzle",
      reason: "Imports Drizzle schema APIs."
    }
  ],
  vitest: [
    {
      kind: "testing",
      value: "vitest",
      reason: "Imports Vitest testing APIs."
    }
  ],
  jest: [{ kind: "testing", value: "jest", reason: "Imports Jest testing APIs." }],
  playwright: [
    {
      kind: "testing",
      value: "playwright",
      reason: "Imports Playwright testing APIs."
    }
  ],
  cypress: [
    {
      kind: "testing",
      value: "cypress",
      reason: "Imports Cypress testing APIs."
    }
  ]
};
async function getFileSignals(input) {
  const signals = [];
  addPathSignals({
    relativePath: input.relativePath,
    packageBinPaths: input.packageBinPaths,
    signals
  });
  if (input.sizeBytes > MAX_SIGNAL_SCAN_FILE_BYTES) {
    return sortSignals2(signals);
  }
  const extractor = getImportExtractor(input.relativePath);
  if (!extractor) {
    return sortSignals2(signals);
  }
  let content;
  try {
    content = await fs.readFile(
      path3.join(input.repoRoot, input.relativePath),
      "utf8"
    );
  } catch {
    return sortSignals2(signals);
  }
  for (const extractedImport of extractor.extractImports({
    filePath: input.relativePath,
    content
  })) {
    if (isLocalImport(extractedImport.specifier)) {
      continue;
    }
    addPackageSignals({
      packageName: getPackageName(extractedImport.specifier),
      signals
    });
  }
  return sortSignals2(signals);
}
async function readPackageBinPaths(repoRoot) {
  const packageJsonPath = path3.join(repoRoot, "package.json");
  const result = /* @__PURE__ */ new Set();
  if (!await fs.pathExists(packageJsonPath)) {
    return result;
  }
  try {
    const packageJson = await fs.readJson(packageJsonPath);
    if (typeof packageJson.bin === "string") {
      result.add(normalizeBinPath(packageJson.bin));
    }
    if (packageJson.bin && typeof packageJson.bin === "object") {
      for (const binPath of Object.values(packageJson.bin)) {
        result.add(normalizeBinPath(binPath));
      }
    }
  } catch {
    return result;
  }
  return result;
}
function isEntrypointCandidatePath(relativePath) {
  const lowerPath = relativePath.toLowerCase();
  return lowerPath === "index.ts" || lowerPath === "index.js" || lowerPath === "main.ts" || lowerPath === "main.tsx" || lowerPath === "main.js" || lowerPath === "main.jsx" || lowerPath === "src/index.ts" || lowerPath === "src/index.js" || lowerPath === "src/main.ts" || lowerPath === "src/main.tsx" || lowerPath === "src/main.js" || lowerPath === "src/main.jsx" || lowerPath === "src/cli/index.ts" || lowerPath === "src/cli/index.js" || lowerPath === "src/cli/cli.ts" || lowerPath === "src/cli/cli.js" || lowerPath === "main.py" || lowerPath === "app.py" || lowerPath === "manage.py" || lowerPath === "asgi.py" || lowerPath === "wsgi.py" || lowerPath === "src/main.py" || lowerPath === "src/app.py" || lowerPath.endsWith("/main.py") || lowerPath.endsWith("/app.py") || lowerPath.endsWith("/manage.py") || lowerPath.endsWith("/urls.py") || lowerPath.endsWith("/asgi.py") || lowerPath.endsWith("/wsgi.py") || lowerPath.endsWith("/page.tsx") || lowerPath.endsWith("/page.jsx") || lowerPath.endsWith("/route.ts") || lowerPath.endsWith("/route.js") || lowerPath.startsWith("bin/") || lowerPath.startsWith("scripts/") || lowerPath.includes("/jobs/");
}
function getImportExtractor(relativePath) {
  const extension = path3.posix.extname(relativePath).toLowerCase();
  if (typescriptJsImportExtractor.extensions.includes(extension)) {
    return typescriptJsImportExtractor;
  }
  if (pythonImportExtractor.extensions.includes(extension)) {
    return pythonImportExtractor;
  }
  return null;
}
function addPathSignals(input) {
  const lowerPath = input.relativePath.toLowerCase();
  if (input.packageBinPaths.has(input.relativePath)) {
    input.signals.push({
      kind: "entrypoint",
      source: "package-json",
      value: "package-bin",
      confidence: "observed",
      reason: "Referenced by package.json bin."
    });
  }
  if (isEntrypointCandidatePath(input.relativePath)) {
    input.signals.push({
      kind: "entrypoint",
      source: "path",
      value: lowerPath,
      confidence: "inferred",
      reason: "Path matches a common entrypoint convention."
    });
  }
  if (lowerPath.endsWith("route.ts") || lowerPath.endsWith("route.js")) {
    input.signals.push({
      kind: "framework",
      source: "path",
      value: "next-route",
      confidence: "inferred",
      reason: "Path matches a Next.js route convention."
    });
  }
}
function addPackageSignals(input) {
  const packageSignals = SIGNALS_BY_PACKAGE[input.packageName];
  if (!packageSignals) {
    return;
  }
  for (const signal of packageSignals) {
    input.signals.push({
      ...signal,
      source: "import",
      confidence: "observed"
    });
  }
}
function sortSignals2(signals) {
  const byKey = /* @__PURE__ */ new Map();
  for (const signal of signals) {
    byKey.set(
      `${signal.kind}\0${signal.source}\0${signal.value}\0${signal.reason}`,
      signal
    );
  }
  return [...byKey.values()].sort(
    (left, right) => left.kind.localeCompare(right.kind) || left.source.localeCompare(right.source) || left.value.localeCompare(right.value) || left.reason.localeCompare(right.reason)
  );
}
function normalizeBinPath(value) {
  return value.replace(/^\.\//, "").replaceAll("\\", "/");
}
function isLocalImport(specifier) {
  return specifier.startsWith(".") || specifier.startsWith("/");
}
function getPackageName(specifier) {
  if (specifier.startsWith("@")) {
    return specifier.split("/").slice(0, 2).join("/");
  }
  const rootSpecifier = specifier.split("/")[0] ?? specifier;
  return rootSpecifier.split(".")[0] ?? rootSpecifier;
}

// src/core/repo-scanner/file-classification.ts
var LOCKFILE_NAMES = /* @__PURE__ */ new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb"
]);
var CONFIG_FILE_NAMES = /* @__PURE__ */ new Set([
  "package.json",
  "tsconfig.json",
  "jsconfig.json",
  "components.json",
  "pyproject.toml",
  "requirements.txt"
]);
var GENERATED_DIRECTORIES = /* @__PURE__ */ new Set(["dist", "build", "coverage", ".next"]);
function detectFileLanguage(relativePath, extension) {
  const fileName = path4.posix.basename(relativePath);
  if (fileName === ".gitignore" || fileName === ".env") {
    return "unknown";
  }
  switch (extension) {
    case ".ts":
    case ".tsx":
    case ".mts":
    case ".cts":
      return "typescript";
    case ".js":
    case ".jsx":
    case ".mjs":
    case ".cjs":
      return "javascript";
    case ".py":
      return "python";
    case ".md":
    case ".mdx":
      return "markdown";
    case ".json":
      return "json";
    case ".yaml":
    case ".yml":
      return "yaml";
    case ".css":
    case ".scss":
      return "css";
    case ".html":
      return "html";
    case ".sh":
    case ".bash":
    case ".zsh":
      return "shell";
    default:
      return "unknown";
  }
}
function getFileRoles(relativePath, tags) {
  const roles = [];
  const lowerPath = relativePath.toLowerCase();
  const fileName = path4.posix.basename(lowerPath);
  const extension = path4.posix.extname(lowerPath);
  if (isSourceExtension(extension)) {
    roles.push("source");
  }
  if (lowerPath.includes("/__tests__/") || lowerPath.includes("/tests/") || lowerPath.startsWith("tests/") || /\.(test|spec)\.[cm]?[jt]sx?$/.test(lowerPath) || lowerPath.endsWith("_test.py")) {
    roles.push("test");
  }
  if (lowerPath.includes("/fixtures/") || lowerPath.startsWith("fixtures/") || lowerPath.includes("/fixture/")) {
    roles.push("fixture");
  }
  if (extension === ".md" || extension === ".mdx" || hasPathPrefix(lowerPath, "docs") || ["readme.md", "agents.md", "claude.md"].includes(fileName)) {
    roles.push("docs");
  }
  if (isConfigPath(lowerPath)) {
    roles.push("config");
  }
  if (CONFIG_FILE_NAMES.has(fileName) || lowerPath.endsWith(".config.ts") || lowerPath.endsWith(".config.js")) {
    roles.push("project-config");
  }
  if (roles.includes("fixture") && roles.includes("config")) {
    roles.push("fixture-config");
  }
  if (LOCKFILE_NAMES.has(fileName)) {
    roles.push("lockfile");
  }
  if (lowerPath.includes("planning") || lowerPath.includes("ticket") || lowerPath.includes("roadmap")) {
    roles.push("planning-doc");
  }
  if (hasGeneratedPathSegment(lowerPath)) {
    roles.push("generated");
  }
  if (isEntrypointCandidatePath(relativePath)) {
    roles.push("entrypoint-candidate");
  }
  if (hasPathPrefix(lowerPath, "src/cli") || hasPathPrefix(lowerPath, "cli")) {
    roles.push("command");
  }
  if (tags.includes("route")) {
    roles.push("route");
  }
  if (fileName === "route.ts" || fileName === "route.js" || lowerPath.includes("/api/")) {
    roles.push("api-route");
  }
  if (hasPathPrefix(lowerPath, "scripts") || lowerPath.includes("/scripts/")) {
    roles.push("script");
  }
  addMatchingRole(roles, lowerPath, ["/models/", "model"], "model");
  addMatchingRole(roles, lowerPath, ["/schemas/", "schema"], "schema");
  addMatchingRole(roles, lowerPath, ["/types/", ".d.ts"], "type");
  addMatchingRole(roles, lowerPath, ["/services/", "/service"], "service");
  addMatchingRole(
    roles,
    lowerPath,
    ["/utils/", "/utility", "/lib/"],
    "utility"
  );
  addMatchingRole(
    roles,
    lowerPath,
    ["/components/", "components/"],
    "component"
  );
  addMatchingRole(roles, lowerPath, ["build", "builder"], "builder");
  addMatchingRole(roles, lowerPath, ["generator"], "generator");
  addMatchingRole(roles, lowerPath, ["resolver"], "resolver");
  addMatchingRole(roles, lowerPath, ["extractor"], "extractor");
  addMatchingRole(roles, lowerPath, ["reader"], "reader");
  addMatchingRole(roles, lowerPath, ["writer"], "writer");
  if (extension === ".sql") {
    roles.push("schema");
  }
  if (hasPathPrefix(lowerPath, "migrations") || lowerPath.includes("/migrations/")) {
    roles.push("migration");
  }
  return uniqueSortedRoles(roles);
}
function getIncludeReason(input) {
  if (input.roles.includes("test")) {
    return "test";
  }
  if (input.roles.includes("fixture")) {
    return "fixture";
  }
  if (input.roles.includes("lockfile") || input.roles.includes("project-config")) {
    return "project-metadata";
  }
  if (input.roles.includes("docs")) {
    return "documentation";
  }
  if (input.roles.includes("config")) {
    return "config";
  }
  if (input.roles.includes("script")) {
    return "script";
  }
  if (input.roles.includes("source")) {
    return "source";
  }
  return input.language === "unknown" ? "unknown" : "source";
}
function getFileConfidence(roles) {
  if (roles.includes("lockfile") || roles.includes("project-config")) {
    return "observed";
  }
  return roles.length === 0 ? "ambiguous" : "inferred";
}
function uniqueSortedRoles(roles) {
  return [...new Set(roles)].sort((left, right) => left.localeCompare(right));
}
function isSourceExtension(extension) {
  return [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"].includes(
    extension
  );
}
function isConfigPath(lowerPath) {
  const fileName = path4.posix.basename(lowerPath);
  return CONFIG_FILE_NAMES.has(fileName) || LOCKFILE_NAMES.has(fileName) || lowerPath.endsWith(".config.ts") || lowerPath.endsWith(".config.js") || lowerPath.endsWith(".config.mjs") || lowerPath.endsWith(".config.cjs") || lowerPath.endsWith(".config.json") || fileName.startsWith(".");
}
function hasGeneratedPathSegment(lowerPath) {
  return lowerPath.split("/").some((segment) => GENERATED_DIRECTORIES.has(segment));
}
function hasPathPrefix(relativePath, prefix) {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}
function addMatchingRole(roles, lowerPath, matches, role) {
  if (matches.some((match) => lowerPath.includes(match))) {
    roles.push(role);
  }
}

// src/core/repo-scanner/gitignore.ts
import fs2 from "fs-extra";
import ignore from "ignore";
import path5 from "path";
function toPosixPath(value) {
  return value.replaceAll(path5.sep, "/");
}
async function createGitignoreFilter(repoRoot) {
  const gitignorePath = path5.join(repoRoot, ".gitignore");
  const ignoreRules = ignore();
  if (await fs2.pathExists(gitignorePath)) {
    const content = await fs2.readFile(gitignorePath, "utf8");
    ignoreRules.add(content);
  }
  return (relativePath) => {
    const normalizedPath = toPosixPath(relativePath);
    return !ignoreRules.ignores(normalizedPath);
  };
}

// src/core/repo-scanner/build-file-index.ts
var NOISE_DIRECTORY_PATTERNS = [
  "**/node_modules/**",
  "**/.next/**",
  "**/dist/**",
  "**/build/**",
  "**/coverage/**",
  "**/.git/**",
  "**/.bridger/**",
  "**/.agents/**"
];
var NOISE_DIRECTORIES = /* @__PURE__ */ new Set([
  "node_modules",
  ".git",
  ".bridger",
  ".agents",
  "dist",
  "build",
  "coverage",
  ".next"
]);
var GENERATED_DIRECTORIES2 = /* @__PURE__ */ new Set(["dist", "build", "coverage", ".next"]);
var BINARY_EXTENSIONS = /* @__PURE__ */ new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".ico",
  ".mp4",
  ".mov",
  ".woff",
  ".woff2",
  ".ttf",
  ".pdf",
  ".zip",
  ".tar",
  ".gz",
  ".sqlite",
  ".db"
]);
var LOCKFILE_NAMES2 = /* @__PURE__ */ new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb"
]);
var MAX_INDEXED_FILE_BYTES = 1e6;
function toPosixPath2(value) {
  return value.replaceAll(path6.sep, "/");
}
function uniqueTags(tags) {
  const seen = /* @__PURE__ */ new Set();
  const result = [];
  for (const tag of tags) {
    if (seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    result.push(tag);
  }
  return result;
}
function hasPathPrefix2(relativePath, prefix) {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}
function hasFileName(relativePath, fileName) {
  return path6.posix.basename(relativePath) === fileName;
}
function getFileTags(relativePath) {
  const tags = [];
  if (hasFileName(relativePath, "README.md")) {
    tags.push("readme", "documentation", "important");
  }
  if (hasFileName(relativePath, "AGENTS.md") || hasFileName(relativePath, "CLAUDE.md")) {
    tags.push("agent-rules", "important");
  }
  if (hasFileName(relativePath, "package.json")) {
    tags.push("package", "config", "important");
  }
  if (hasFileName(relativePath, "tsconfig.json")) {
    tags.push("typescript", "config");
  }
  if (hasFileName(relativePath, "components.json")) {
    tags.push("shadcn", "config");
  }
  if (relativePath.startsWith("next.config.")) {
    tags.push("nextjs", "config");
  }
  if (relativePath.startsWith("tailwind.config.")) {
    tags.push("tailwind", "config");
  }
  if (relativePath.startsWith("drizzle.config.")) {
    tags.push("drizzle", "database", "config");
  }
  if (hasPathPrefix2(relativePath, "docs")) {
    tags.push("documentation");
  }
  if (hasPathPrefix2(relativePath, "app")) {
    tags.push("app", "route");
  }
  if (hasPathPrefix2(relativePath, "pages")) {
    tags.push("pages", "route");
  }
  if (hasPathPrefix2(relativePath, "src")) {
    tags.push("src");
  }
  if (hasPathPrefix2(relativePath, "src/app")) {
    tags.push("src", "app", "route");
  }
  if (hasPathPrefix2(relativePath, "components")) {
    tags.push("components", "ui");
  }
  if (hasPathPrefix2(relativePath, "src/components")) {
    tags.push("src", "components", "ui");
  }
  if (hasPathPrefix2(relativePath, "lib")) {
    tags.push("lib");
  }
  if (hasPathPrefix2(relativePath, "src/lib")) {
    tags.push("src", "lib");
  }
  if (hasPathPrefix2(relativePath, "server")) {
    tags.push("server");
  }
  if (hasPathPrefix2(relativePath, "src/server")) {
    tags.push("src", "server");
  }
  if (hasPathPrefix2(relativePath, "db")) {
    tags.push("database");
  }
  if (hasPathPrefix2(relativePath, "src/db")) {
    tags.push("src", "database");
  }
  if (hasPathPrefix2(relativePath, "supabase")) {
    tags.push("supabase", "database");
  }
  if (hasPathPrefix2(relativePath, "prisma")) {
    tags.push("prisma", "database");
  }
  if (hasPathPrefix2(relativePath, "drizzle")) {
    tags.push("drizzle", "database");
  }
  const extension = path6.posix.extname(relativePath);
  if (extension === ".ts") {
    tags.push("typescript");
  }
  if (extension === ".tsx") {
    tags.push("typescript", "react");
  }
  if (extension === ".js") {
    tags.push("javascript");
  }
  if (extension === ".jsx") {
    tags.push("javascript", "react");
  }
  if (extension === ".md") {
    tags.push("markdown");
  }
  if (extension === ".mdx") {
    tags.push("markdown", "react");
  }
  if (extension === ".json") {
    tags.push("json");
  }
  if (extension === ".css" || extension === ".scss") {
    tags.push("style");
  }
  if (extension === ".sql") {
    tags.push("database", "sql");
  }
  return uniqueTags(tags);
}
function getFileReason(relativePath) {
  if (hasFileName(relativePath, "README.md")) {
    return "Project README";
  }
  if (hasFileName(relativePath, "AGENTS.md")) {
    return "Agent instruction file";
  }
  if (hasFileName(relativePath, "CLAUDE.md")) {
    return "Claude agent instruction file";
  }
  if (hasFileName(relativePath, "package.json")) {
    return "Package manifest and scripts/dependencies source";
  }
  if (hasFileName(relativePath, "tsconfig.json")) {
    return "TypeScript configuration";
  }
  if (hasFileName(relativePath, "components.json")) {
    return "shadcn/ui component configuration";
  }
  if (relativePath.startsWith("next.config.")) {
    return "Next.js configuration";
  }
  if (relativePath.startsWith("tailwind.config.")) {
    return "Tailwind CSS configuration";
  }
  if (relativePath.startsWith("drizzle.config.")) {
    return "Drizzle configuration";
  }
  if (hasPathPrefix2(relativePath, "docs")) {
    return "Project documentation";
  }
  if (hasPathPrefix2(relativePath, "app") || hasPathPrefix2(relativePath, "src/app")) {
    return "Application route file";
  }
  if (hasPathPrefix2(relativePath, "pages")) {
    return "Pages router file";
  }
  if (hasPathPrefix2(relativePath, "components") || hasPathPrefix2(relativePath, "src/components")) {
    return "UI component file";
  }
  if (hasPathPrefix2(relativePath, "lib") || hasPathPrefix2(relativePath, "src/lib")) {
    return "Library/helper file";
  }
  if (hasPathPrefix2(relativePath, "server") || hasPathPrefix2(relativePath, "src/server")) {
    return "Server-side code file";
  }
  if (hasPathPrefix2(relativePath, "db") || hasPathPrefix2(relativePath, "src/db")) {
    return "Database-related file";
  }
  if (hasPathPrefix2(relativePath, "supabase")) {
    return "Supabase-related file";
  }
  if (hasPathPrefix2(relativePath, "prisma")) {
    return "Prisma-related file";
  }
  if (hasPathPrefix2(relativePath, "drizzle")) {
    return "Drizzle-related file";
  }
  return void 0;
}
async function buildFileIndex(repoRoot) {
  const gitignoreFilter = await createGitignoreFilter(repoRoot);
  const packageBinPaths = await readPackageBinPaths(repoRoot);
  const discoveredPaths = await fg("**/*", {
    cwd: repoRoot,
    onlyFiles: true,
    dot: true,
    ignore: NOISE_DIRECTORY_PATTERNS,
    followSymbolicLinks: false
  });
  const skippedFiles = await getSkippedNoiseDirectories(repoRoot);
  const files = [];
  for (const relativePath of discoveredPaths.map(toPosixPath2).sort((left, right) => left.localeCompare(right))) {
    const absolutePath = path6.join(repoRoot, relativePath);
    const stats = await fs3.stat(absolutePath);
    const extension = path6.posix.extname(relativePath);
    const skipReason = getSkipReason({
      relativePath,
      sizeBytes: stats.size,
      gitignoreFilter
    });
    if (skipReason) {
      skippedFiles.push({
        path: RepoRelativePathSchema.parse(relativePath),
        reason: skipReason.reason,
        detail: skipReason.detail
      });
      continue;
    }
    const tags = getFileTags(relativePath);
    const language = detectFileLanguage(relativePath, extension || void 0);
    const roles = getFileRoles(relativePath, tags);
    const rolesWithEntrypoint = packageBinPaths.has(relativePath) ? uniqueSortedRoles([...roles, "entrypoint-candidate"]) : roles;
    const signals = await getFileSignals({
      repoRoot,
      relativePath,
      sizeBytes: stats.size,
      packageBinPaths
    });
    files.push({
      path: RepoRelativePathSchema.parse(relativePath),
      extension: extension || void 0,
      sizeBytes: stats.size,
      language,
      roles: rolesWithEntrypoint,
      confidence: getFileConfidence(rolesWithEntrypoint),
      includeReason: getIncludeReason({
        language,
        roles: rolesWithEntrypoint
      }),
      signals,
      tags,
      reason: getFileReason(relativePath)
    });
  }
  skippedFiles.sort(compareSkippedFiles);
  const warnings = getWarnings(files, skippedFiles);
  return FileIndexSchema.parse({
    schemaVersion: 2,
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    files,
    skippedFiles,
    warnings,
    stats: buildStats({
      totalFilesDiscovered: files.length + skippedFiles.length,
      files,
      skippedFiles
    })
  });
}
function getSkipReason(input) {
  const lowerPath = input.relativePath.toLowerCase();
  const extension = path6.posix.extname(lowerPath);
  if (isSensitivePath(lowerPath)) {
    return {
      reason: "sensitive",
      detail: "Sensitive environment or secrets-like file."
    };
  }
  if (BINARY_EXTENSIONS.has(extension)) {
    return {
      reason: "binary",
      detail: `Binary or media extension ${extension}.`
    };
  }
  if (!input.gitignoreFilter(input.relativePath)) {
    return {
      reason: "ignored",
      detail: "Ignored by repository gitignore rules."
    };
  }
  if (!LOCKFILE_NAMES2.has(path6.posix.basename(lowerPath)) && input.sizeBytes > MAX_INDEXED_FILE_BYTES) {
    return {
      reason: "too-large",
      detail: `File exceeds ${MAX_INDEXED_FILE_BYTES} bytes.`
    };
  }
  return null;
}
async function getSkippedNoiseDirectories(repoRoot) {
  const skippedFiles = [];
  for (const directory of [...NOISE_DIRECTORIES].sort((left, right) => left.localeCompare(right))) {
    if (!await fs3.pathExists(path6.join(repoRoot, directory))) {
      continue;
    }
    skippedFiles.push({
      path: RepoRelativePathSchema.parse(directory),
      reason: GENERATED_DIRECTORIES2.has(directory) ? "generated" : "noise-directory",
      detail: "Directory excluded from repository inventory traversal."
    });
  }
  return skippedFiles;
}
function isSensitivePath(lowerPath) {
  const fileName = path6.posix.basename(lowerPath);
  return fileName === ".env" || fileName.startsWith(".env.") || fileName === "secrets.json" || fileName === "secrets.yaml" || fileName === "secrets.yml" || fileName === "credentials.json" || fileName.endsWith(".pem") || fileName.endsWith(".key");
}
function buildStats(input) {
  const byLanguage = {
    typescript: 0,
    javascript: 0,
    python: 0,
    markdown: 0,
    json: 0,
    yaml: 0,
    css: 0,
    html: 0,
    shell: 0,
    unknown: 0
  };
  const byRole = {};
  const bySkipReason = {};
  let totalIncludedBytes = 0;
  for (const file of input.files) {
    totalIncludedBytes += file.sizeBytes;
    byLanguage[file.language ?? "unknown"] += 1;
    for (const role of file.roles ?? []) {
      byRole[role] = (byRole[role] ?? 0) + 1;
    }
  }
  for (const skippedFile of input.skippedFiles) {
    bySkipReason[skippedFile.reason] = (bySkipReason[skippedFile.reason] ?? 0) + 1;
  }
  return {
    totalFilesDiscovered: input.totalFilesDiscovered,
    includedFileCount: input.files.length,
    skippedFileCount: input.skippedFiles.length,
    totalIncludedBytes,
    byLanguage,
    byRole,
    bySkipReason
  };
}
function getWarnings(files, skippedFiles) {
  const warnings = [];
  if (!files.some((file) => file.roles?.includes("source"))) {
    warnings.push({
      code: "no-source-files",
      message: "No source files were detected in the repository inventory.",
      severity: "warning"
    });
  }
  for (const skippedFile of skippedFiles) {
    if (skippedFile.reason === "sensitive") {
      warnings.push({
        code: "sensitive-file-skipped",
        message: `Skipped sensitive file ${skippedFile.path}.`,
        filePath: skippedFile.path,
        severity: "warning"
      });
    }
    if (skippedFile.reason === "too-large") {
      warnings.push({
        code: "large-file-skipped",
        message: `Skipped large file ${skippedFile.path}.`,
        filePath: skippedFile.path,
        severity: "info"
      });
    }
  }
  if (skippedFiles.length > files.length * 2 && skippedFiles.length > 20) {
    warnings.push({
      code: "many-skipped-files",
      message: "Skipped file count is much larger than included file count.",
      severity: "info"
    });
  }
  return warnings.sort(compareWarnings);
}
function compareSkippedFiles(left, right) {
  return left.path.localeCompare(right.path) || left.reason.localeCompare(right.reason);
}
function compareWarnings(left, right) {
  return left.code.localeCompare(right.code) || (left.filePath ?? "").localeCompare(right.filePath ?? "") || left.message.localeCompare(right.message);
}

// src/core/repo-scanner/detect-commands.ts
import fs4 from "fs-extra";
import path7 from "path";

// src/core/models/repo-context.ts
import { z as z5 } from "zod";
var RepoContextStackSchema = z5.object({
  framework: z5.string(),
  language: z5.string(),
  packageManager: z5.string(),
  styling: z5.array(z5.string()),
  validation: z5.array(z5.string()),
  database: z5.array(z5.string()),
  testFramework: z5.array(z5.string())
});
var RepoContextCommandsSchema = z5.object({
  install: z5.string().optional(),
  dev: z5.string().optional(),
  build: z5.string().optional(),
  lint: z5.string().optional(),
  typecheck: z5.string().optional(),
  test: z5.string().optional(),
  format: z5.string().optional()
});
var RepoContextImportantFileSchema = z5.object({
  path: z5.string(),
  reason: z5.string()
});
var RepoContextGeneratedDocsSchema = z5.object({
  repoAnalysisPath: RepoRelativePathSchema,
  architecturePath: RepoRelativePathSchema,
  conventionsPath: RepoRelativePathSchema,
  businessLogicPath: RepoRelativePathSchema,
  testingPath: RepoRelativePathSchema,
  ticketTemplatePath: RepoRelativePathSchema
});
var RepoContextSchema = z5.object({
  repoRoot: z5.string(),
  generatedAt: z5.iso.datetime(),
  stack: RepoContextStackSchema,
  commands: RepoContextCommandsSchema,
  importantFiles: z5.array(RepoContextImportantFileSchema),
  generatedDocs: RepoContextGeneratedDocsSchema
});

// src/core/repo-scanner/detect-commands.ts
async function readPackageJson(repoRoot) {
  const packageJsonPath = path7.join(repoRoot, "package.json");
  if (!await fs4.pathExists(packageJsonPath)) {
    return null;
  }
  try {
    const raw = await fs4.readFile(packageJsonPath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
function normalizePackageManager(packageManager) {
  if (packageManager === "pnpm" || packageManager?.startsWith("pnpm")) {
    return "pnpm";
  }
  if (packageManager === "npm" || packageManager?.startsWith("npm")) {
    return "npm";
  }
  if (packageManager === "yarn" || packageManager?.startsWith("yarn")) {
    return "yarn";
  }
  if (packageManager === "bun" || packageManager?.startsWith("bun")) {
    return "bun";
  }
  return void 0;
}
function formatInstallCommand(packageManager) {
  if (packageManager === "pnpm") {
    return "pnpm install";
  }
  if (packageManager === "yarn") {
    return "yarn install";
  }
  if (packageManager === "bun") {
    return "bun install";
  }
  return "npm install";
}
function formatScriptCommand(packageManager, scriptName) {
  if (packageManager === "pnpm") {
    return `pnpm ${scriptName}`;
  }
  if (packageManager === "yarn") {
    return `yarn ${scriptName}`;
  }
  if (packageManager === "bun") {
    return `bun run ${scriptName}`;
  }
  return `npm run ${scriptName}`;
}
function findScript(scripts, candidates) {
  for (const candidate of candidates) {
    if (Object.prototype.hasOwnProperty.call(scripts, candidate)) {
      return candidate;
    }
  }
  return void 0;
}
async function detectCommands(repoRoot, packageManager) {
  const packageJson = await readPackageJson(repoRoot);
  if (packageJson === null) {
    return RepoContextCommandsSchema.parse({});
  }
  const resolvedPackageManager = normalizePackageManager(packageManager) ?? normalizePackageManager(packageJson.packageManager) ?? "npm";
  const scripts = packageJson.scripts ?? {};
  const commands = {
    install: formatInstallCommand(resolvedPackageManager)
  };
  const devScript = findScript(scripts, ["dev", "start"]);
  if (devScript !== void 0) {
    commands.dev = formatScriptCommand(resolvedPackageManager, devScript);
  }
  const buildScript = findScript(scripts, ["build"]);
  if (buildScript !== void 0) {
    commands.build = formatScriptCommand(resolvedPackageManager, buildScript);
  }
  const lintScript = findScript(scripts, ["lint"]);
  if (lintScript !== void 0) {
    commands.lint = formatScriptCommand(resolvedPackageManager, lintScript);
  }
  const typecheckScript = findScript(scripts, [
    "typecheck",
    "check-types",
    "check:types",
    "tsc"
  ]);
  if (typecheckScript !== void 0) {
    commands.typecheck = formatScriptCommand(resolvedPackageManager, typecheckScript);
  }
  const testScript = findScript(scripts, ["test", "test:unit"]);
  if (testScript !== void 0) {
    commands.test = formatScriptCommand(resolvedPackageManager, testScript);
  }
  const formatScript = findScript(scripts, ["format", "prettier"]);
  if (formatScript !== void 0) {
    commands.format = formatScriptCommand(resolvedPackageManager, formatScript);
  }
  return RepoContextCommandsSchema.parse(commands);
}

// src/core/repo-scanner/detect-stack.ts
import fs5 from "fs-extra";
import path8 from "path";
var CONFIG_EXTENSIONS = [".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"];
function pushUnique(target, value) {
  if (!target.includes(value)) {
    target.push(value);
  }
}
async function pathExists(repoRoot, relativePath) {
  return fs5.pathExists(path8.join(repoRoot, relativePath));
}
async function hasAnyPath(repoRoot, relativePaths) {
  for (const relativePath of relativePaths) {
    if (await pathExists(repoRoot, relativePath)) {
      return true;
    }
  }
  return false;
}
async function hasAnyConfigFile(repoRoot, baseName) {
  for (const extension of CONFIG_EXTENSIONS) {
    if (await pathExists(repoRoot, `${baseName}${extension}`)) {
      return true;
    }
  }
  return false;
}
async function readPackageJson2(repoRoot) {
  const packageJsonPath = path8.join(repoRoot, "package.json");
  if (!await fs5.pathExists(packageJsonPath)) {
    return null;
  }
  try {
    const raw = await fs5.readFile(packageJsonPath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
function getAllDependencyNames(packageJson) {
  const names = /* @__PURE__ */ new Set();
  if (packageJson === null) {
    return names;
  }
  const sections = [
    packageJson.dependencies,
    packageJson.devDependencies,
    packageJson.peerDependencies,
    packageJson.optionalDependencies
  ];
  for (const section of sections) {
    if (section === void 0) {
      continue;
    }
    for (const name of Object.keys(section)) {
      names.add(name);
    }
  }
  return names;
}
async function detectPackageManager(repoRoot, packageJson) {
  if (await pathExists(repoRoot, "pnpm-lock.yaml")) {
    return "pnpm";
  }
  if (await pathExists(repoRoot, "yarn.lock")) {
    return "yarn";
  }
  if (await pathExists(repoRoot, "package-lock.json")) {
    return "npm";
  }
  if (await pathExists(repoRoot, "bun.lockb") || await pathExists(repoRoot, "bun.lock")) {
    return "bun";
  }
  const packageManager = packageJson?.packageManager;
  if (typeof packageManager !== "string") {
    return "unknown";
  }
  if (packageManager.startsWith("pnpm")) {
    return "pnpm";
  }
  if (packageManager.startsWith("yarn")) {
    return "yarn";
  }
  if (packageManager.startsWith("npm")) {
    return "npm";
  }
  if (packageManager.startsWith("bun")) {
    return "bun";
  }
  return "unknown";
}
async function detectFramework(repoRoot, dependencies) {
  if (dependencies.has("next")) {
    return "Next.js";
  }
  const hasNextConfig = await hasAnyConfigFile(repoRoot, "next.config");
  const hasAppOrPagesDir = await hasAnyPath(repoRoot, [
    "app",
    "pages",
    "src/app",
    "src/pages"
  ]);
  if (hasNextConfig && hasAppOrPagesDir) {
    return "Next.js";
  }
  return "unknown";
}
async function detectLanguage(repoRoot, dependencies, packageJson) {
  if (await pathExists(repoRoot, "tsconfig.json")) {
    return "TypeScript";
  }
  if (dependencies.has("typescript")) {
    return "TypeScript";
  }
  if (packageJson !== null) {
    return "JavaScript";
  }
  return "unknown";
}
async function detectStyling(repoRoot, dependencies) {
  const styling = [];
  if (dependencies.has("tailwindcss") || await hasAnyConfigFile(repoRoot, "tailwind.config")) {
    pushUnique(styling, "Tailwind");
  }
  if (await pathExists(repoRoot, "components.json")) {
    pushUnique(styling, "shadcn/ui");
  }
  return styling;
}
function detectValidation(dependencies) {
  const validation = [];
  if (dependencies.has("zod")) {
    pushUnique(validation, "Zod");
  }
  return validation;
}
async function detectDatabase(repoRoot, dependencies) {
  const database = [];
  if (dependencies.has("@supabase/supabase-js") || await pathExists(repoRoot, "supabase")) {
    pushUnique(database, "Supabase");
  }
  if (dependencies.has("prisma") || dependencies.has("@prisma/client") || await pathExists(repoRoot, "prisma/schema.prisma")) {
    pushUnique(database, "Prisma");
  }
  if (dependencies.has("drizzle-orm") || await hasAnyConfigFile(repoRoot, "drizzle.config")) {
    pushUnique(database, "Drizzle");
  }
  return database;
}
async function detectTestFramework(repoRoot, dependencies) {
  const testFramework = [];
  if (dependencies.has("vitest") || await hasAnyConfigFile(repoRoot, "vitest.config")) {
    pushUnique(testFramework, "Vitest");
  }
  if (dependencies.has("jest") || await hasAnyConfigFile(repoRoot, "jest.config")) {
    pushUnique(testFramework, "Jest");
  }
  if (dependencies.has("@playwright/test") || dependencies.has("playwright") || await hasAnyConfigFile(repoRoot, "playwright.config")) {
    pushUnique(testFramework, "Playwright");
  }
  if (dependencies.has("cypress") || await pathExists(repoRoot, "cypress") || await hasAnyConfigFile(repoRoot, "cypress.config")) {
    pushUnique(testFramework, "Cypress");
  }
  return testFramework;
}
async function detectStack(repoRoot) {
  const packageJson = await readPackageJson2(repoRoot);
  const dependencies = getAllDependencyNames(packageJson);
  const framework = await detectFramework(repoRoot, dependencies);
  const language = await detectLanguage(repoRoot, dependencies, packageJson);
  const packageManager = await detectPackageManager(repoRoot, packageJson);
  const styling = await detectStyling(repoRoot, dependencies);
  const validation = detectValidation(dependencies);
  const database = await detectDatabase(repoRoot, dependencies);
  const testFramework = await detectTestFramework(repoRoot, dependencies);
  const stack = {
    framework,
    language,
    packageManager,
    styling,
    validation,
    database,
    testFramework
  };
  return RepoContextStackSchema.parse(stack);
}

// src/core/repo-scanner/read-important-files.ts
import fs6 from "fs-extra";
import path10 from "path";

// src/core/models/important-file.ts
import { z as z6 } from "zod";
var ImportantFileSchema = z6.object({
  path: z6.string(),
  reason: z6.string(),
  content: z6.string()
});
var ImportantFilesSchema = z6.array(ImportantFileSchema);

// src/core/repo-scanner/important-file-rules.ts
import path9 from "path";
var IMPORTANT_FILE_BUDGETS = {
  maxSingleFileBytes: 20 * 1024,
  maxTotalContentBytes: 120 * 1024,
  maxConfigTotalBytes: 20 * 1024
};
var IMPORTANT_FILE_CATEGORY_LIMITS = {
  agent: 3,
  docs: 6,
  entrypoint: 12,
  domain: 20,
  component: 10,
  test: 6,
  config: 5
};
var ALLOWED_TEXT_EXTENSIONS = /* @__PURE__ */ new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".json",
  ".md",
  ".mdx",
  ".css",
  ".scss",
  ".sql",
  ".prisma",
  ".yaml",
  ".yml",
  ".toml"
]);
var LOCKFILE_NAMES3 = /* @__PURE__ */ new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb"
]);
function normalizeRelativePath(relativePath) {
  return relativePath.replaceAll("\\", "/");
}
function hasPathPrefix3(relativePath, prefix) {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}
function hasFileName2(relativePath, fileName) {
  return path9.posix.basename(relativePath) === fileName;
}
function hasSuffixMatch(relativePath, suffix) {
  return relativePath.includes(`/${suffix}`) || path9.posix.basename(relativePath).includes(suffix);
}
function isAllowedImportantFileExtension(relativePath) {
  const normalizedPath = normalizeRelativePath(relativePath);
  const fileName = path9.posix.basename(normalizedPath);
  if (LOCKFILE_NAMES3.has(fileName)) {
    return false;
  }
  const extension = path9.extname(normalizedPath);
  return ALLOWED_TEXT_EXTENSIONS.has(extension);
}
function classifyImportantFile(relativePath) {
  const normalizedPath = normalizeRelativePath(relativePath);
  if (LOCKFILE_NAMES3.has(path9.posix.basename(normalizedPath))) {
    return null;
  }
  if (hasFileName2(normalizedPath, "AGENTS.md")) {
    return {
      path: normalizedPath,
      reason: "Existing agent instruction file",
      priority: 10,
      category: "agent"
    };
  }
  if (hasFileName2(normalizedPath, "CLAUDE.md")) {
    return {
      path: normalizedPath,
      reason: "Existing Claude instruction file",
      priority: 10,
      category: "agent"
    };
  }
  if (hasFileName2(normalizedPath, "components.json")) {
    return {
      path: normalizedPath,
      reason: "Design system or component alias configuration",
      priority: 70,
      category: "config"
    };
  }
  if (hasFileName2(normalizedPath, "tsconfig.json")) {
    return {
      path: normalizedPath,
      reason: "TypeScript path alias configuration",
      priority: 70,
      category: "config"
    };
  }
  if (normalizedPath.startsWith("next.config.")) {
    return {
      path: normalizedPath,
      reason: "Framework configuration with possible repo-specific behavior",
      priority: 70,
      category: "config"
    };
  }
  if (normalizedPath.startsWith("tailwind.config.")) {
    return {
      path: normalizedPath,
      reason: "Tailwind theme/configuration",
      priority: 70,
      category: "config"
    };
  }
  if (hasFileName2(normalizedPath, "package.json")) {
    return {
      path: normalizedPath,
      reason: "Package scripts and dependency manifest",
      priority: 70,
      category: "config"
    };
  }
  if (hasFileName2(normalizedPath, "README.md")) {
    return {
      path: normalizedPath,
      reason: "Project README",
      priority: 60,
      category: "docs"
    };
  }
  if (hasPathPrefix3(normalizedPath, "docs") && path9.extname(normalizedPath) === ".md") {
    return {
      path: normalizedPath,
      reason: "Project documentation",
      priority: 60,
      category: "docs"
    };
  }
  if (hasPathPrefix3(normalizedPath, "app") || hasPathPrefix3(normalizedPath, "src/app")) {
    const fileName = path9.posix.basename(normalizedPath);
    if (fileName.startsWith("layout.")) {
      return {
        path: normalizedPath,
        reason: "Application layout entry point",
        priority: 20,
        category: "entrypoint"
      };
    }
    if (fileName.startsWith("page.")) {
      return {
        path: normalizedPath,
        reason: "Application page/route entry point",
        priority: 20,
        category: "entrypoint"
      };
    }
    if (fileName.startsWith("route.")) {
      return {
        path: normalizedPath,
        reason: "API route entry point",
        priority: 20,
        category: "entrypoint"
      };
    }
  }
  if (hasPathPrefix3(normalizedPath, "pages") || hasPathPrefix3(normalizedPath, "src/pages")) {
    const fileName = path9.posix.basename(normalizedPath);
    if (normalizedPath.startsWith("pages/api/") || normalizedPath.startsWith("src/pages/api/") || normalizedPath.startsWith("src/pages/") || fileName.startsWith("_app.") || fileName.startsWith("index.")) {
      return {
        path: normalizedPath,
        reason: "Pages router entry point",
        priority: 20,
        category: "entrypoint"
      };
    }
  }
  if (hasPathPrefix3(normalizedPath, "src/core") || hasPathPrefix3(normalizedPath, "src/domain") || hasPathPrefix3(normalizedPath, "src/domains")) {
    if (hasPathPrefix3(normalizedPath, "src/models") || hasPathPrefix3(normalizedPath, "src/entities") || hasPathPrefix3(normalizedPath, "src/schemas") || hasPathPrefix3(normalizedPath, "src/types") || hasSuffixMatch(normalizedPath, "schema.") || hasSuffixMatch(normalizedPath, "types.")) {
      return {
        path: normalizedPath,
        reason: "Model/schema/type definition file",
        priority: 30,
        category: "domain"
      };
    }
    return {
      path: normalizedPath,
      reason: hasPathPrefix3(normalizedPath, "src/domain") || hasPathPrefix3(normalizedPath, "src/domains") ? "Domain/business logic file" : hasPathPrefix3(normalizedPath, "src/core") ? "Core application logic file" : "Infrastructure/helper file",
      priority: 30,
      category: "domain"
    };
  }
  if (hasPathPrefix3(normalizedPath, "src/models") || hasPathPrefix3(normalizedPath, "src/entities") || hasPathPrefix3(normalizedPath, "src/schemas") || hasPathPrefix3(normalizedPath, "src/types") || hasSuffixMatch(normalizedPath, "schema.") || hasSuffixMatch(normalizedPath, "types.")) {
    return {
      path: normalizedPath,
      reason: "Model/schema/type definition file",
      priority: 30,
      category: "domain"
    };
  }
  if (hasPathPrefix3(normalizedPath, "db") || hasPathPrefix3(normalizedPath, "src/db") || hasPathPrefix3(normalizedPath, "prisma") || hasPathPrefix3(normalizedPath, "drizzle") || hasPathPrefix3(normalizedPath, "supabase")) {
    return {
      path: normalizedPath,
      reason: "Data access or persistence file",
      priority: 30,
      category: "domain"
    };
  }
  if (hasPathPrefix3(normalizedPath, "src/lib") || hasPathPrefix3(normalizedPath, "lib")) {
    return {
      path: normalizedPath,
      reason: "Infrastructure/helper file",
      priority: 30,
      category: "domain"
    };
  }
  if (hasPathPrefix3(normalizedPath, "components/ui") || hasPathPrefix3(normalizedPath, "src/components/ui")) {
    return {
      path: normalizedPath,
      reason: "Representative UI component file",
      priority: 40,
      category: "component"
    };
  }
  if (hasPathPrefix3(normalizedPath, "components/layout") || hasPathPrefix3(normalizedPath, "src/components/layout") || hasPathPrefix3(normalizedPath, "components/navigation") || hasPathPrefix3(normalizedPath, "src/components/navigation")) {
    return {
      path: normalizedPath,
      reason: "Representative layout/navigation component file",
      priority: 40,
      category: "component"
    };
  }
  if (hasPathPrefix3(normalizedPath, "components") || hasPathPrefix3(normalizedPath, "src/components")) {
    return {
      path: normalizedPath,
      reason: "Representative component file",
      priority: 40,
      category: "component"
    };
  }
  if (hasPathPrefix3(normalizedPath, "tests") || hasPathPrefix3(normalizedPath, "__tests__") || hasPathPrefix3(normalizedPath, "src/__tests__") || normalizedPath.includes(".test.") || normalizedPath.includes(".spec.")) {
    return {
      path: normalizedPath,
      reason: "Representative test file",
      priority: 50,
      category: "test"
    };
  }
  return null;
}

// src/core/repo-scanner/read-important-files.ts
function dedupeCandidates(candidates) {
  const byPath = /* @__PURE__ */ new Map();
  for (const candidate of candidates) {
    const existing = byPath.get(candidate.path);
    if (existing === void 0) {
      byPath.set(candidate.path, candidate);
      continue;
    }
    if (candidate.priority < existing.priority) {
      byPath.set(candidate.path, candidate);
    }
  }
  return [...byPath.values()];
}
function createCategoryCounts() {
  return {
    agent: 0,
    docs: 0,
    entrypoint: 0,
    domain: 0,
    component: 0,
    test: 0,
    config: 0
  };
}
async function readImportantFiles(input) {
  const normalizedRepoRoot = path10.resolve(input.repoRoot);
  const candidates = [];
  for (const entry of input.fileIndex.files) {
    if (!isAllowedImportantFileExtension(entry.path)) {
      continue;
    }
    const candidate = classifyImportantFile(entry.path);
    if (candidate === null) {
      continue;
    }
    candidates.push(candidate);
  }
  const selectedCandidates = dedupeCandidates(candidates).sort((left, right) => {
    if (left.priority !== right.priority) {
      return left.priority - right.priority;
    }
    return left.path.localeCompare(right.path);
  });
  const selectedFiles = [];
  const categoryCounts = createCategoryCounts();
  let totalBytes = 0;
  let configBytes = 0;
  for (const candidate of selectedCandidates) {
    const entry = input.fileIndex.files.find((file) => file.path === candidate.path);
    if (entry === void 0) {
      continue;
    }
    if (entry.sizeBytes > IMPORTANT_FILE_BUDGETS.maxSingleFileBytes) {
      continue;
    }
    if (categoryCounts[candidate.category] >= IMPORTANT_FILE_CATEGORY_LIMITS[candidate.category]) {
      continue;
    }
    if (totalBytes + entry.sizeBytes > IMPORTANT_FILE_BUDGETS.maxTotalContentBytes) {
      continue;
    }
    if (candidate.category === "config" && configBytes + entry.sizeBytes > IMPORTANT_FILE_BUDGETS.maxConfigTotalBytes) {
      continue;
    }
    const absolutePath = path10.resolve(normalizedRepoRoot, candidate.path);
    if (!absolutePath.startsWith(`${normalizedRepoRoot}${path10.sep}`) && absolutePath !== normalizedRepoRoot) {
      continue;
    }
    let content;
    try {
      content = await fs6.readFile(absolutePath, "utf8");
    } catch {
      continue;
    }
    const contentBytes = Buffer.byteLength(content, "utf8");
    if (contentBytes > IMPORTANT_FILE_BUDGETS.maxSingleFileBytes) {
      continue;
    }
    if (totalBytes + contentBytes > IMPORTANT_FILE_BUDGETS.maxTotalContentBytes) {
      continue;
    }
    if (candidate.category === "config" && configBytes + contentBytes > IMPORTANT_FILE_BUDGETS.maxConfigTotalBytes) {
      continue;
    }
    selectedFiles.push({
      path: candidate.path,
      reason: candidate.reason,
      content
    });
    totalBytes += contentBytes;
    categoryCounts[candidate.category] += 1;
    if (candidate.category === "config") {
      configBytes += contentBytes;
    }
  }
  return ImportantFilesSchema.parse(selectedFiles);
}

// src/core/project/bridger-paths.ts
import path11 from "path";
var MEMORY_FILENAMES = {
  repoAnalysis: "repo-analysis.md",
  architecture: "architecture.md",
  businessLogic: "business-logic.md",
  conventions: "conventions.md",
  testing: "testing.md"
};
function getBridgerDir(repoRoot) {
  return path11.join(repoRoot, ".bridger");
}
function getBridgerConfigPath(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "config.json");
}
function getBridgerIndexPath(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "index.md");
}
function getBridgerLogPath(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "log.md");
}
function getArtifactsDir(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "artifacts");
}
function getFileIndexPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "file-index.json");
}
function getRepoContextPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "repo-context.json");
}
function getRepoGraphPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "repo-graph.json");
}
function getGraphSummaryPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "graph-summary.json");
}
function getCodebaseMapPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "codebase-map.json");
}
function getReadingPlansPath(repoRoot) {
  return path11.join(getArtifactsDir(repoRoot), "reading-plans.json");
}
function getMemoryDir(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "memory");
}
function getMemoryFilePath(repoRoot, file) {
  return path11.join(getMemoryDir(repoRoot), file);
}
function getGeneratedKnowledgeDocPath(repoRoot, key) {
  return getMemoryFilePath(repoRoot, MEMORY_FILENAMES[key]);
}
function getGeneratedKnowledgeDocRelativePath(key) {
  return RepoRelativePathSchema.parse(
    [".bridger", "memory", MEMORY_FILENAMES[key]].join("/")
  );
}
function getSkillsDir(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "skills");
}
function getSelectedSkillsPath(repoRoot) {
  return path11.join(getSkillsDir(repoRoot), "selected-skills.json");
}
function getTemplatesDir(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "templates");
}
function getTicketTemplatePath(repoRoot) {
  return path11.join(getTemplatesDir(repoRoot), "ticket-template.md");
}
function getTicketTemplateRelativePath() {
  return RepoRelativePathSchema.parse(
    [".bridger", "templates", "ticket-template.md"].join("/")
  );
}
function getExportsDir(repoRoot) {
  return path11.join(getBridgerDir(repoRoot), "exports");
}
function getAgentsGeneratedExportPath(repoRoot) {
  return path11.join(getExportsDir(repoRoot), "AGENTS.generated.md");
}
function getClaudeGeneratedExportPath(repoRoot) {
  return path11.join(getExportsDir(repoRoot), "CLAUDE.generated.md");
}
function getRootAgentsPath(repoRoot) {
  return path11.join(repoRoot, "AGENTS.md");
}
function buildGeneratedDocPaths() {
  return {
    repoAnalysisPath: getGeneratedKnowledgeDocRelativePath("repoAnalysis"),
    architecturePath: getGeneratedKnowledgeDocRelativePath("architecture"),
    businessLogicPath: getGeneratedKnowledgeDocRelativePath("businessLogic"),
    conventionsPath: getGeneratedKnowledgeDocRelativePath("conventions"),
    testingPath: getGeneratedKnowledgeDocRelativePath("testing")
  };
}

// src/core/models/repo-context-build.ts
import { z as z7 } from "zod";
var RepoContextBuildArtifactsSchema = z7.object({
  repoContext: RepoContextSchema,
  fileIndex: FileIndexSchema,
  importantFiles: ImportantFilesSchema
});

// src/core/context-builder/build-repo-context.ts
async function buildRepoContextArtifacts(repoRoot) {
  const stack = await detectStack(repoRoot);
  const commands = await detectCommands(repoRoot, stack.packageManager);
  const fileIndex = await buildFileIndex(repoRoot);
  const importantFiles = await readImportantFiles({
    repoRoot,
    fileIndex
  });
  const repoContext = RepoContextSchema.parse({
    repoRoot,
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    stack,
    commands,
    importantFiles: importantFiles.map((file) => ({
      path: file.path,
      reason: file.reason
    })),
    generatedDocs: {
      ...buildGeneratedDocPaths(),
      ticketTemplatePath: getTicketTemplateRelativePath()
    }
  });
  return RepoContextBuildArtifactsSchema.parse({
    repoContext,
    fileIndex,
    importantFiles
  });
}

// src/core/project/load-bridger-project.ts
import fs8 from "fs/promises";

// src/core/project/read-bridger-config.ts
import fs7 from "fs/promises";

// src/core/project/bridger-config.ts
import { z as z8 } from "zod";
var BridgerProjectModeSchema = z8.enum([
  "fresh",
  "existing",
  "unknown"
]);
var BridgerConfigSchema = z8.object({
  schemaVersion: z8.literal(1),
  project: z8.object({
    name: z8.string().min(1),
    mode: BridgerProjectModeSchema
  }),
  detected: z8.object({
    packageManager: z8.string().optional(),
    stack: z8.array(z8.string()).default([])
  }),
  paths: z8.object({
    memoryDir: z8.literal(".bridger/memory"),
    artifactsDir: z8.literal(".bridger/artifacts"),
    skillsDir: z8.literal(".bridger/skills"),
    templatesDir: z8.literal(".bridger/templates"),
    exportsDir: z8.literal(".bridger/exports")
  }),
  memory: z8.object({
    schemaVersion: z8.literal(1),
    files: z8.array(z8.string()).default([
      "repo-analysis.md",
      "architecture.md",
      "business-logic.md",
      "conventions.md",
      "testing.md"
    ])
  }),
  artifacts: z8.object({
    schemaVersion: z8.literal(1)
  }),
  skills: z8.object({
    selected: z8.array(z8.string()).default([])
  }),
  exports: z8.object({
    agentsMd: z8.object({
      enabled: z8.boolean().default(true),
      generatedPath: z8.literal(".bridger/exports/AGENTS.generated.md"),
      rootPath: z8.literal("AGENTS.md"),
      writeRootFile: z8.boolean().default(false)
    }),
    claudeMd: z8.object({
      enabled: z8.boolean().default(false),
      generatedPath: z8.literal(".bridger/exports/CLAUDE.generated.md"),
      rootPath: z8.literal("CLAUDE.md"),
      writeRootFile: z8.boolean().default(false)
    })
  }),
  llm: z8.object({
    provider: z8.enum(["none", "openai", "bridger-sponsored"]).default("none"),
    modelProfile: z8.enum(["cheap", "balanced", "quality"]).default("balanced")
  }),
  timestamps: z8.object({
    initializedAt: z8.string(),
    lastInitAt: z8.string().optional(),
    lastUpdateAt: z8.string().optional()
  })
});

// src/core/project/read-bridger-config.ts
async function readBridgerConfig(repoRoot) {
  const configPath = getBridgerConfigPath(repoRoot);
  const rawConfig = await fs7.readFile(configPath, "utf8");
  return BridgerConfigSchema.parse(JSON.parse(rawConfig));
}

// src/core/project/load-bridger-project.ts
async function loadBridgerProject(repoRoot) {
  const bridgerDir = getBridgerDir(repoRoot);
  const configPath = getBridgerConfigPath(repoRoot);
  if (!await pathExists2(bridgerDir)) {
    return {
      status: "uninitialized",
      repoRoot,
      reason: "missing-bridger-dir"
    };
  }
  if (!await pathExists2(configPath)) {
    return {
      status: "uninitialized",
      repoRoot,
      reason: "missing-config"
    };
  }
  try {
    return {
      status: "initialized",
      repoRoot,
      config: await readBridgerConfig(repoRoot)
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      status: "invalid",
      repoRoot,
      reason: error instanceof SyntaxError ? "invalid-config" : "unreadable-config",
      message
    };
  }
}
async function pathExists2(filePath) {
  try {
    await fs8.access(filePath);
    return true;
  } catch {
    return false;
  }
}

// src/core/repo-graph/models/graph-summary.ts
import { z as z10 } from "zod";

// src/core/repo-graph/models/repo-graph.ts
import { z as z9 } from "zod";
var RepoGraphNodeKindSchema = z9.enum(["file", "directory"]);
var RepoGraphEdgeTypeSchema = z9.enum(["contains", "imports"]);
var RepoGraphEdgeConfidenceSchema = z9.enum(["high", "medium", "low"]);
var RepoGraphEdgeSourceSchema = z9.enum([
  "filesystem",
  "typescript-js-imports",
  "python-imports"
]);
var RepoGraphDiagnosticLevelSchema = z9.enum(["info", "warning"]);
var RepoGraphDiagnosticCodeSchema = z9.enum([
  "unresolved-import",
  "unsupported-language",
  "skipped-large-file",
  "ambiguous-import",
  "read-error"
]);
var RepoGraphLanguageSchema = z9.enum([
  "typescript",
  "javascript",
  "python",
  "markdown",
  "json",
  "unknown"
]);
var RepoGraphNodeTagSchema = z9.enum([
  "root",
  "config",
  "docs",
  "source",
  "test",
  "entrypoint-candidate",
  "component",
  "service",
  "utility",
  "route",
  "api-route"
]);
var RepoGraphNodeSchema = z9.object({
  id: z9.string().min(1),
  path: z9.string().min(1),
  kind: RepoGraphNodeKindSchema,
  extension: z9.string().nullable(),
  language: RepoGraphLanguageSchema,
  sizeBytes: z9.number().int().nonnegative(),
  tags: z9.array(RepoGraphNodeTagSchema)
});
var RepoGraphEdgeSchema = z9.object({
  from: z9.string().min(1),
  to: z9.string().min(1),
  type: RepoGraphEdgeTypeSchema,
  confidence: RepoGraphEdgeConfidenceSchema,
  source: RepoGraphEdgeSourceSchema,
  importSpecifier: z9.string().min(1).optional()
});
var RepoGraphDiagnosticSchema = z9.object({
  level: RepoGraphDiagnosticLevelSchema,
  code: RepoGraphDiagnosticCodeSchema,
  file: z9.string().min(1).optional(),
  message: z9.string().min(1)
});
var RepoGraphStatsSchema = z9.object({
  fileCount: z9.number().int().nonnegative(),
  directoryCount: z9.number().int().nonnegative(),
  containsEdgeCount: z9.number().int().nonnegative(),
  importEdgeCount: z9.number().int().nonnegative(),
  unresolvedImportCount: z9.number().int().nonnegative(),
  supportedLanguageFileCount: z9.number().int().nonnegative()
});
var RepoGraphSchema = z9.object({
  generatedAt: z9.iso.datetime(),
  graphVersion: z9.literal(1),
  repoRoot: z9.string().min(1),
  nodes: z9.array(RepoGraphNodeSchema),
  edges: z9.array(RepoGraphEdgeSchema),
  diagnostics: z9.array(RepoGraphDiagnosticSchema),
  stats: RepoGraphStatsSchema
});

// src/core/repo-graph/models/graph-summary.ts
var GraphSummaryRankedFileSchema = z10.object({
  path: z10.string().min(1),
  count: z10.number().int().nonnegative(),
  reason: z10.string().min(1)
});
var GraphSummarySchema = z10.object({
  generatedAt: z10.iso.datetime(),
  graphVersion: z10.literal(1),
  entrypoints: z10.array(z10.string().min(1)),
  rootFiles: z10.array(z10.string().min(1)),
  configFiles: z10.array(z10.string().min(1)),
  docsFiles: z10.array(z10.string().min(1)),
  highFanInFiles: z10.array(GraphSummaryRankedFileSchema),
  highFanOutFiles: z10.array(GraphSummaryRankedFileSchema),
  leafFiles: z10.array(z10.string().min(1)),
  isolatedFiles: z10.array(z10.string().min(1)),
  architectureFirstOrder: z10.array(z10.string().min(1)),
  dependencyFirstOrder: z10.array(z10.string().min(1)),
  stats: RepoGraphStatsSchema
});

// src/core/repo-graph/traversal/get-dependencies.ts
function getDependencies(graph, filePath, depth = 1) {
  const adjacencyMap = buildAdjacencyMap(graph);
  return traverseAdjacency({
    startPath: filePath,
    depth,
    nextPathsByFile: adjacencyMap.dependenciesByFile
  });
}

// src/core/repo-graph/traversal/get-architecture-order.ts
function getArchitectureOrder(graph) {
  const filePaths = getFilePaths(graph);
  const nodeByPath = getFileNodeByPath(graph);
  const ranks = getGraphFileRanks(graph);
  const rankByPath = new Map(ranks.map((rank) => [rank.path, rank]));
  const rootFiles = getRootFiles(graph);
  const entrypoints = getEntrypoints(graph);
  const entrypointDependencies = getDirectEntrypointDependencies(
    graph,
    entrypoints
  );
  void rankByPath;
  return uniqueStableOrder([
    ...sortPaths2(
      [
        ...rootFiles.docsFiles,
        ...rootFiles.configFiles,
        ...rootFiles.rootFiles
      ].filter((path20) => !isTestFile(path20, nodeByPath.get(path20)))
    ),
    ...sortPaths2(
      entrypoints.filter((path20) => !isTestFile(path20, nodeByPath.get(path20)))
    ),
    ...sortPaths2(
      entrypointDependencies.filter(
        (path20) => !isTestFile(path20, nodeByPath.get(path20))
      )
    ),
    ...sortPaths2(
      filePaths.filter(
        (path20) => isFeatureOrDomainFile(path20) && !isTestFile(path20, nodeByPath.get(path20))
      )
    ),
    ...sortPaths2(
      filePaths.filter(
        (path20) => isComponentServiceOrLibFile(path20, nodeByPath.get(path20)) && !isTestFile(path20, nodeByPath.get(path20))
      )
    ),
    ...sortPaths2(
      filePaths.filter(
        (path20) => isSharedUtilityFile(path20, nodeByPath.get(path20)) && !isTestFile(path20, nodeByPath.get(path20))
      )
    ),
    ...sortPaths2(
      filePaths.filter((path20) => isTestFile(path20, nodeByPath.get(path20)))
    ),
    ...filePaths
  ]);
}
function getDirectEntrypointDependencies(graph, entrypoints) {
  const dependencies = /* @__PURE__ */ new Set();
  for (const entrypoint of entrypoints) {
    for (const dependency of getDependencies(graph, entrypoint, 1)) {
      dependencies.add(dependency);
    }
  }
  return sortPaths2(dependencies);
}
function getFilePaths(graph) {
  return graph.nodes.filter((node) => node.kind === "file").map((node) => normalizeRepoPath(node.path)).sort((a, b) => a.localeCompare(b));
}
function getFileNodeByPath(graph) {
  const nodesByPath = /* @__PURE__ */ new Map();
  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }
    nodesByPath.set(normalizeRepoPath(node.path), node);
  }
  return nodesByPath;
}
function sortPaths2(paths) {
  return [...paths].sort((a, b) => a.localeCompare(b));
}
function uniqueStableOrder(paths) {
  const seen = /* @__PURE__ */ new Set();
  const ordered = [];
  for (const path20 of paths) {
    if (seen.has(path20)) {
      continue;
    }
    seen.add(path20);
    ordered.push(path20);
  }
  return ordered;
}
function hasTag(node, tag) {
  return node?.tags.includes(tag) ?? false;
}
function isFeatureOrDomainFile(path20) {
  const lowerPath = path20.toLowerCase();
  return lowerPath.startsWith("features/") || lowerPath.startsWith("feature/") || lowerPath.startsWith("domain/") || lowerPath.startsWith("domains/") || lowerPath.startsWith("modules/") || lowerPath.includes("/features/") || lowerPath.includes("/feature/") || lowerPath.includes("/domain/") || lowerPath.includes("/domains/") || lowerPath.includes("/modules/") || lowerPath.includes("/use-cases/") || lowerPath.includes("/usecases/") || lowerPath.includes("/entities/") || lowerPath.includes("/models/");
}
function isComponentServiceOrLibFile(path20, node) {
  if (isSharedUtilityFile(path20, node)) {
    return false;
  }
  const lowerPath = path20.toLowerCase();
  return hasTag(node, "component") || hasTag(node, "service") || lowerPath.startsWith("components/") || lowerPath.startsWith("services/") || lowerPath.startsWith("lib/") || lowerPath.includes("/components/") || lowerPath.includes("/services/") || lowerPath.includes("/service/") || lowerPath.includes("/lib/");
}
function isSharedUtilityFile(path20, node) {
  const lowerPath = path20.toLowerCase();
  return hasTag(node, "utility") || lowerPath.startsWith("utils/") || lowerPath.startsWith("helpers/") || lowerPath.includes("/utils/") || lowerPath.includes("/util/") || lowerPath.includes("/helpers/") || lowerPath.endsWith("utils.ts") || lowerPath.endsWith("utils.js") || lowerPath.endsWith("util.ts") || lowerPath.endsWith("util.js") || lowerPath.endsWith("helpers.ts") || lowerPath.endsWith("helpers.js");
}
function isTestFile(path20, node) {
  const lowerPath = path20.toLowerCase();
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;
  return hasTag(node, "test") || lowerPath.startsWith("tests/") || lowerPath.startsWith("test/") || lowerPath.includes("/__tests__/") || lowerPath.includes(".test.") || lowerPath.includes(".spec.") || lowerPath.endsWith("_test.py") || fileName.startsWith("test_");
}

// src/core/repo-graph/traversal/get-dependency-order.ts
function getDependencyOrder(graph) {
  const filePaths = getFilePaths2(graph);
  const nodeByPath = getFileNodeByPath2(graph);
  const ranks = getGraphFileRanks(graph);
  const rankByPath = new Map(ranks.map((rank) => [rank.path, rank]));
  return uniqueStableOrder2([
    ...sortPaths3(
      filePaths.filter((path20) => {
        const node = nodeByPath.get(path20);
        const rank = rankByPath.get(path20);
        return Boolean(rank?.isLeaf) && !isTestFile2(path20, node);
      })
    ),
    ...sortPaths3(
      filePaths.filter((path20) => {
        const node = nodeByPath.get(path20);
        const rank = rankByPath.get(path20);
        return isSharedUtilityFile2(path20, node) && (rank?.fanOut ?? 0) <= 1 && !isTestFile2(path20, node);
      })
    ),
    ...sortPaths3(
      filePaths.filter((path20) => {
        const node = nodeByPath.get(path20);
        return isServiceOrHelperFile(path20, node) && !isTestFile2(path20, node);
      })
    ),
    ...sortPaths3(
      filePaths.filter((path20) => {
        const node = nodeByPath.get(path20);
        return isFeatureOrComponentFile(path20, node) && !isTestFile2(path20, node);
      })
    ),
    ...sortPaths3(
      filePaths.filter((path20) => {
        const node = nodeByPath.get(path20);
        const rank = rankByPath.get(path20);
        return Boolean(rank?.isEntrypoint) && !isTestFile2(path20, node);
      })
    ),
    ...sortPaths3(
      filePaths.filter((path20) => isTestFile2(path20, nodeByPath.get(path20)))
    ),
    ...filePaths
  ]);
}
function getFilePaths2(graph) {
  return graph.nodes.filter((node) => node.kind === "file").map((node) => normalizeRepoPath(node.path)).sort((a, b) => a.localeCompare(b));
}
function getFileNodeByPath2(graph) {
  const nodesByPath = /* @__PURE__ */ new Map();
  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }
    nodesByPath.set(normalizeRepoPath(node.path), node);
  }
  return nodesByPath;
}
function sortPaths3(paths) {
  return [...paths].sort((a, b) => a.localeCompare(b));
}
function uniqueStableOrder2(paths) {
  const seen = /* @__PURE__ */ new Set();
  const ordered = [];
  for (const path20 of paths) {
    if (seen.has(path20)) {
      continue;
    }
    seen.add(path20);
    ordered.push(path20);
  }
  return ordered;
}
function hasTag2(node, tag) {
  return node?.tags.includes(tag) ?? false;
}
function isSharedUtilityFile2(path20, node) {
  const lowerPath = path20.toLowerCase();
  return hasTag2(node, "utility") || lowerPath.startsWith("utils/") || lowerPath.startsWith("helpers/") || lowerPath.includes("/utils/") || lowerPath.includes("/util/") || lowerPath.includes("/helpers/") || lowerPath.endsWith("utils.ts") || lowerPath.endsWith("utils.js") || lowerPath.endsWith("util.ts") || lowerPath.endsWith("util.js") || lowerPath.endsWith("helpers.ts") || lowerPath.endsWith("helpers.js");
}
function isServiceOrHelperFile(path20, node) {
  const lowerPath = path20.toLowerCase();
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;
  return hasTag2(node, "service") || lowerPath.startsWith("services/") || lowerPath.startsWith("service/") || lowerPath.startsWith("helpers/") || lowerPath.includes("/services/") || lowerPath.includes("/service/") || lowerPath.includes("/helpers/") || fileName.endsWith("service.ts") || fileName.endsWith("service.js") || fileName.endsWith("service.py") || fileName.endsWith("helper.ts") || fileName.endsWith("helper.js") || fileName.endsWith("helpers.ts") || fileName.endsWith("helpers.js");
}
function isFeatureOrDomainFile2(path20) {
  const lowerPath = path20.toLowerCase();
  return lowerPath.startsWith("features/") || lowerPath.startsWith("feature/") || lowerPath.startsWith("domain/") || lowerPath.startsWith("domains/") || lowerPath.startsWith("modules/") || lowerPath.includes("/features/") || lowerPath.includes("/feature/") || lowerPath.includes("/domain/") || lowerPath.includes("/domains/") || lowerPath.includes("/modules/") || lowerPath.includes("/use-cases/") || lowerPath.includes("/usecases/") || lowerPath.includes("/entities/") || lowerPath.includes("/models/");
}
function isFeatureOrComponentFile(path20, node) {
  const lowerPath = path20.toLowerCase();
  return isFeatureOrDomainFile2(path20) || hasTag2(node, "component") || lowerPath.startsWith("components/") || lowerPath.includes("/components/");
}
function isTestFile2(path20, node) {
  const lowerPath = path20.toLowerCase();
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;
  return hasTag2(node, "test") || lowerPath.startsWith("tests/") || lowerPath.startsWith("test/") || lowerPath.includes("/__tests__/") || lowerPath.includes(".test.") || lowerPath.includes(".spec.") || lowerPath.endsWith("_test.py") || fileName.startsWith("test_");
}

// src/core/repo-graph/build-graph-summary.ts
var MAX_RANKED_FILES = 10;
function buildGraphSummary(graph) {
  const ranks = getGraphFileRanks(graph);
  const rootFiles = getRootFiles(graph);
  const summary = {
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    graphVersion: graph.graphVersion,
    entrypoints: sortPaths4(getEntrypoints(graph)),
    rootFiles: sortPaths4(rootFiles.rootFiles),
    configFiles: sortPaths4(rootFiles.configFiles),
    docsFiles: sortPaths4(rootFiles.docsFiles),
    highFanInFiles: getHighFanInFiles(ranks),
    highFanOutFiles: getHighFanOutFiles(ranks),
    leafFiles: sortPaths4(ranks.filter((rank) => rank.isLeaf).map((rank) => rank.path)),
    isolatedFiles: sortPaths4(
      ranks.filter((rank) => rank.isIsolated).map((rank) => rank.path)
    ),
    architectureFirstOrder: getArchitectureOrder(graph),
    dependencyFirstOrder: getDependencyOrder(graph),
    stats: graph.stats
  };
  return GraphSummarySchema.parse(summary);
}
function getHighFanInFiles(ranks) {
  return ranks.filter((rank) => rank.fanIn > 0).sort(
    (left, right) => compareCountDescThenPathAsc(left, right, left.fanIn, right.fanIn)
  ).slice(0, MAX_RANKED_FILES).map((rank) => ({
    path: rank.path,
    count: rank.fanIn,
    reason: `Imported by ${rank.fanIn} file${rank.fanIn === 1 ? "" : "s"}.`
  }));
}
function getHighFanOutFiles(ranks) {
  return ranks.filter((rank) => rank.fanOut > 0).sort(
    (left, right) => compareCountDescThenPathAsc(left, right, left.fanOut, right.fanOut)
  ).slice(0, MAX_RANKED_FILES).map((rank) => ({
    path: rank.path,
    count: rank.fanOut,
    reason: `Imports ${rank.fanOut} file${rank.fanOut === 1 ? "" : "s"}.`
  }));
}
function compareCountDescThenPathAsc(left, right, leftCount, rightCount) {
  return rightCount - leftCount || left.path.localeCompare(right.path);
}
function sortPaths4(paths) {
  return [...paths].sort((left, right) => left.localeCompare(right));
}

// src/core/repo-graph/utils/detect-language.ts
var LANGUAGE_BY_EXTENSION = {
  ".ts": "typescript",
  ".tsx": "typescript",
  ".js": "javascript",
  ".jsx": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".py": "python",
  ".md": "markdown",
  ".json": "json"
};
function detectLanguageFromExtension(extension) {
  if (!extension) {
    return "unknown";
  }
  const normalizedExtension = extension.startsWith(".") ? extension.toLowerCase() : `.${extension.toLowerCase()}`;
  return LANGUAGE_BY_EXTENSION[normalizedExtension] ?? "unknown";
}

// src/core/repo-graph/utils/path-tags.ts
var TAG_ORDER = [
  "root",
  "config",
  "docs",
  "source",
  "test",
  "entrypoint-candidate",
  "component",
  "service",
  "utility",
  "route",
  "api-route"
];
var SOURCE_EXTENSIONS = /* @__PURE__ */ new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".py"
]);
function getPathTags(path20) {
  const normalizedPath = normalizeRepoPath(path20);
  const lowerPath = normalizedPath.toLowerCase();
  const segments = lowerPath.split("/");
  const fileName = segments.at(-1) ?? lowerPath;
  const extension = getLowerExtension(fileName);
  const tags = /* @__PURE__ */ new Set();
  if (!normalizedPath.includes("/")) {
    tags.add("root");
  }
  if (isConfigPath2(lowerPath, fileName)) {
    tags.add("config");
  }
  if (isDocsPath(lowerPath, fileName)) {
    tags.add("docs");
  }
  if (isSourcePath(lowerPath, extension)) {
    tags.add("source");
  }
  if (isTestPath(lowerPath, fileName)) {
    tags.add("test");
  }
  if (isEntrypointCandidatePath2(lowerPath)) {
    tags.add("entrypoint-candidate");
  }
  if (isComponentPath(lowerPath, extension)) {
    tags.add("component");
  }
  if (isServicePath(lowerPath, fileName)) {
    tags.add("service");
  }
  if (isUtilityPath(lowerPath, fileName)) {
    tags.add("utility");
  }
  if (isRoutePath(lowerPath)) {
    tags.add("route");
  }
  if (isApiRoutePath(lowerPath)) {
    tags.add("api-route");
  }
  return TAG_ORDER.filter((tag) => tags.has(tag));
}
function getLowerExtension(fileName) {
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0) {
    return null;
  }
  return fileName.slice(dotIndex);
}
function isConfigPath2(lowerPath, fileName) {
  return lowerPath.startsWith(".github/") || fileName === "package.json" || fileName === "tsconfig.json" || fileName === "jsconfig.json" || fileName === "components.json" || fileName === "pyproject.toml" || fileName === "ruff.toml" || fileName === "mypy.ini" || fileName === "pytest.ini" || fileName === "dockerfile" || fileName === "docker-compose.yml" || fileName === ".env.example" || fileName.startsWith("next.config.") || fileName.startsWith("vite.config.") || fileName.startsWith("vitest.config.") || fileName.startsWith("jest.config.") || fileName.startsWith("playwright.config.") || fileName.startsWith("tailwind.config.") || fileName.startsWith("postcss.config.") || fileName.startsWith("eslint.config.") || fileName.startsWith("prettier.config.");
}
function isDocsPath(lowerPath, fileName) {
  return lowerPath.startsWith("docs/") || fileName === "readme.md" || fileName === "agents.md" || fileName === "claude.md" || fileName.endsWith(".md");
}
function isSourcePath(lowerPath, extension) {
  return SOURCE_EXTENSIONS.has(extension ?? "") || lowerPath.startsWith("src/") || lowerPath.startsWith("app/") || lowerPath.startsWith("pages/") || lowerPath.startsWith("components/") || lowerPath.startsWith("lib/") || lowerPath.startsWith("server/") || lowerPath.startsWith("core/") || lowerPath.startsWith("cli/") || lowerPath.startsWith("api/");
}
function isTestPath(lowerPath, fileName) {
  return lowerPath.startsWith("tests/") || lowerPath.startsWith("test/") || lowerPath.includes("/__tests__/") || fileName.includes(".test.") || fileName.includes(".spec.") || fileName.startsWith("test_") || fileName.endsWith("_test.py");
}
function isEntrypointCandidatePath2(lowerPath) {
  return lowerPath === "index.ts" || lowerPath === "main.ts" || lowerPath === "main.py" || lowerPath === "app.py" || lowerPath === "src/index.ts" || lowerPath === "src/main.ts" || lowerPath === "src/main.py" || lowerPath === "src/cli/index.ts" || lowerPath.startsWith("bin/") || lowerPath === "app/page.tsx" || lowerPath === "src/app/page.tsx" || /^app\/.+\/page\.tsx$/.test(lowerPath) || /^src\/app\/.+\/page\.tsx$/.test(lowerPath) || /^app\/.+\/route\.ts$/.test(lowerPath) || /^src\/app\/.+\/route\.ts$/.test(lowerPath) || /^pages\/.+\.tsx$/.test(lowerPath) || /^src\/pages\/.+\.tsx$/.test(lowerPath);
}
function isComponentPath(lowerPath, extension) {
  return lowerPath.startsWith("components/") || lowerPath.startsWith("src/components/") || lowerPath.includes("/components/") || extension === ".tsx" || extension === ".jsx";
}
function isServicePath(lowerPath, fileName) {
  return lowerPath.startsWith("services/") || lowerPath.startsWith("service/") || lowerPath.includes("/services/") || lowerPath.includes("/service/") || fileName.endsWith("service.ts") || fileName.endsWith("service.js") || fileName.endsWith("service.py");
}
function isUtilityPath(lowerPath, fileName) {
  return lowerPath.startsWith("utils/") || lowerPath.startsWith("util/") || lowerPath.startsWith("helpers/") || lowerPath.startsWith("lib/") || lowerPath.includes("/utils/") || lowerPath.includes("/util/") || lowerPath.includes("/helpers/") || lowerPath.includes("/lib/") || fileName.endsWith("utils.ts") || fileName.endsWith("utils.js") || fileName.endsWith("util.ts") || fileName.endsWith("util.js") || fileName.endsWith("helpers.ts") || fileName.endsWith("helpers.js");
}
function isRoutePath(lowerPath) {
  return lowerPath.startsWith("pages/") || lowerPath.startsWith("src/pages/") || lowerPath.startsWith("routes/") || lowerPath.startsWith("src/routes/") || lowerPath === "app/page.tsx" || lowerPath === "src/app/page.tsx" || /^app\/.+\/page\.tsx$/.test(lowerPath) || /^src\/app\/.+\/page\.tsx$/.test(lowerPath) || /^app\/.+\/layout\.tsx$/.test(lowerPath) || /^src\/app\/.+\/layout\.tsx$/.test(lowerPath) || /^app\/.+\/route\.ts$/.test(lowerPath) || /^src\/app\/.+\/route\.ts$/.test(lowerPath);
}
function isApiRoutePath(lowerPath) {
  return lowerPath.startsWith("api/") || lowerPath.startsWith("src/api/") || lowerPath.startsWith("pages/api/") || lowerPath.startsWith("src/pages/api/") || /^app\/.+\/route\.ts$/.test(lowerPath) || /^src\/app\/.+\/route\.ts$/.test(lowerPath);
}

// src/core/repo-graph/build-filesystem-graph.ts
function buildFilesystemGraph(input) {
  const nodesById = /* @__PURE__ */ new Map();
  const edgesByKey = /* @__PURE__ */ new Map();
  for (const file of input.fileIndex.files) {
    const filePath = normalizeRepoPath(file.path);
    addParentDirectories({
      filePath,
      nodesById,
      edgesByKey
    });
    addFileNode({
      file,
      filePath,
      nodesById
    });
    addFileContainsEdge({
      filePath,
      edgesByKey
    });
  }
  return {
    nodes: Array.from(nodesById.values()).sort(compareNodes),
    edges: Array.from(edgesByKey.values()).sort(compareEdges)
  };
}
function addParentDirectories(input) {
  const parentDirectories = getParentDirectories(input.filePath);
  for (const directoryPath of parentDirectories) {
    addDirectoryNode({
      directoryPath,
      nodesById: input.nodesById
    });
    const parentDirectory = getParentDirectory(directoryPath);
    if (parentDirectory === null) {
      continue;
    }
    addContainsEdge({
      from: parentDirectory,
      to: directoryPath,
      edgesByKey: input.edgesByKey
    });
  }
}
function addDirectoryNode(input) {
  if (input.nodesById.has(input.directoryPath)) {
    return;
  }
  const node = RepoGraphNodeSchema.parse({
    id: input.directoryPath,
    path: input.directoryPath,
    kind: "directory",
    extension: null,
    language: "unknown",
    sizeBytes: 0,
    tags: getPathTags(input.directoryPath)
  });
  input.nodesById.set(node.id, node);
}
function addFileNode(input) {
  if (input.nodesById.has(input.filePath)) {
    return;
  }
  const extension = normalizeFileExtension(input.file.extension, input.filePath);
  const node = RepoGraphNodeSchema.parse({
    id: input.filePath,
    path: input.filePath,
    kind: "file",
    extension,
    language: detectLanguageFromExtension(extension),
    sizeBytes: input.file.sizeBytes,
    tags: getPathTags(input.filePath)
  });
  input.nodesById.set(node.id, node);
}
function addFileContainsEdge(input) {
  const parentDirectory = getParentDirectory(input.filePath);
  if (parentDirectory === null) {
    return;
  }
  addContainsEdge({
    from: parentDirectory,
    to: input.filePath,
    edgesByKey: input.edgesByKey
  });
}
function addContainsEdge(input) {
  const edge = RepoGraphEdgeSchema.parse({
    from: input.from,
    to: input.to,
    type: "contains",
    confidence: "high",
    source: "filesystem"
  });
  const key = getEdgeKey(edge.from, edge.to, edge.type);
  if (input.edgesByKey.has(key)) {
    return;
  }
  input.edgesByKey.set(key, edge);
}
function getParentDirectories(filePath) {
  const segments = filePath.split("/");
  if (segments.length <= 1) {
    return [];
  }
  const directories = [];
  for (let index = 1; index < segments.length; index += 1) {
    directories.push(segments.slice(0, index).join("/"));
  }
  return directories;
}
function getParentDirectory(filePath) {
  const lastSlashIndex = filePath.lastIndexOf("/");
  if (lastSlashIndex === -1) {
    return null;
  }
  return filePath.slice(0, lastSlashIndex);
}
function normalizeFileExtension(extension, filePath) {
  if (typeof extension === "string" && extension.trim() !== "") {
    const normalizedExtension = extension.startsWith(".") ? extension : `.${extension}`;
    return normalizedExtension.toLowerCase();
  }
  return inferExtensionFromPath(filePath);
}
function inferExtensionFromPath(filePath) {
  const fileName = filePath.split("/").at(-1);
  if (!fileName) {
    return null;
  }
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0) {
    return null;
  }
  return fileName.slice(dotIndex).toLowerCase();
}
function getEdgeKey(from, to, type) {
  return `${from}\0${to}\0${type}`;
}
function compareNodes(a, b) {
  return a.path.localeCompare(b.path);
}
function compareEdges(a, b) {
  return a.from.localeCompare(b.from) || a.to.localeCompare(b.to) || a.type.localeCompare(b.type);
}

// src/core/repo-graph/build-import-edges.ts
import { readFile } from "fs/promises";
import path14 from "path";

// src/core/repo-graph/resolution/resolve-python-import.ts
import path12 from "path";
function resolvePythonImport(input) {
  const specifier = input.specifier.trim();
  if (specifier === "") {
    return {
      status: "ignored",
      reason: "external-package"
    };
  }
  const repoFileSet = toNormalizedRepoFileSet(input.repoFiles);
  const importerPath = normalizeRepoPath(input.importerPath);
  if (specifier.startsWith(".")) {
    const resolvedPath2 = resolveRelativePythonImport({
      importerPath,
      specifier,
      repoFileSet
    });
    if (resolvedPath2) {
      return {
        status: "resolved",
        resolvedPath: resolvedPath2,
        confidence: "high"
      };
    }
    return {
      status: "unresolved",
      reason: "local-import-not-found"
    };
  }
  const resolvedPath = resolveAbsolutePythonImport({
    specifier,
    repoFileSet
  });
  if (resolvedPath) {
    return {
      status: "resolved",
      resolvedPath,
      confidence: "medium"
    };
  }
  return {
    status: "ignored",
    reason: "external-package"
  };
}
function resolveAbsolutePythonImport(input) {
  const modulePath = moduleSpecifierToPath(input.specifier);
  for (const candidate of getAbsoluteCandidates(modulePath)) {
    if (input.repoFileSet.has(candidate)) {
      return candidate;
    }
  }
  return null;
}
function resolveRelativePythonImport(input) {
  const parsed = parseRelativeSpecifier(input.specifier);
  if (!parsed) {
    return null;
  }
  const importerDirectory = path12.posix.dirname(input.importerPath);
  const baseDirectory = ascendDirectory(importerDirectory, parsed.level - 1);
  const modulePath = parsed.modulePath ? path12.posix.join(baseDirectory, parsed.modulePath) : baseDirectory;
  const normalizedModulePath = normalizeRepoPath(
    path12.posix.normalize(modulePath)
  );
  for (const candidate of getPythonModuleCandidates(normalizedModulePath)) {
    if (input.repoFileSet.has(candidate)) {
      return candidate;
    }
  }
  return null;
}
function parseRelativeSpecifier(specifier) {
  const match = specifier.match(/^(\.+)(.*)$/);
  if (!match?.[1]) {
    return null;
  }
  return {
    level: match[1].length,
    modulePath: moduleSpecifierToPath(match[2] ?? "")
  };
}
function moduleSpecifierToPath(specifier) {
  return specifier.split(".").filter(Boolean).join("/");
}
function getAbsoluteCandidates(modulePath) {
  return [
    ...getPythonModuleCandidates(modulePath),
    ...getPythonModuleCandidates(`src/${modulePath}`)
  ];
}
function getPythonModuleCandidates(modulePath) {
  const parts = modulePath.split("/").filter(Boolean);
  const candidates = [];
  for (let length = parts.length; length >= 1; length -= 1) {
    const candidateBase = parts.slice(0, length).join("/");
    candidates.push(`${candidateBase}.py`, `${candidateBase}/__init__.py`);
  }
  return candidates;
}
function ascendDirectory(directoryPath, levels) {
  let current = directoryPath;
  for (let index = 0; index < levels; index += 1) {
    const next = path12.posix.dirname(current);
    if (next === current || next === ".") {
      return ".";
    }
    current = next;
  }
  return current;
}
function toNormalizedRepoFileSet(repoFiles) {
  const values = Array.isArray(repoFiles) ? repoFiles : Array.from(repoFiles);
  return new Set(values.map(normalizeRepoPath));
}

// src/core/repo-graph/resolution/resolve-typescript-js-import.ts
import path13 from "path";
var TYPESCRIPT_JS_RESOLUTION_EXTENSIONS = [
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs"
];
function resolveTypeScriptJsImport(input) {
  const specifier = input.specifier.trim();
  if (!isRelativeImportSpecifier(specifier)) {
    return {
      status: "ignored",
      reason: "external-package"
    };
  }
  const repoFileSet = toNormalizedRepoFileSet2(input.repoFiles);
  const importerPath = normalizeRepoPath(input.importerPath);
  const importerDirectory = path13.posix.dirname(importerPath);
  const basePath = normalizeRepoPath(
    path13.posix.normalize(path13.posix.join(importerDirectory, specifier))
  );
  for (const candidate of getTypeScriptJsResolutionCandidates(basePath)) {
    if (repoFileSet.has(candidate)) {
      return {
        status: "resolved",
        resolvedPath: candidate,
        confidence: "high"
      };
    }
  }
  return {
    status: "unresolved",
    reason: "local-import-not-found"
  };
}
function isRelativeImportSpecifier(specifier) {
  return specifier.startsWith("./") || specifier.startsWith("../");
}
function toNormalizedRepoFileSet2(repoFiles) {
  const values = Array.isArray(repoFiles) ? repoFiles : Array.from(repoFiles);
  return new Set(values.map(normalizeRepoPath));
}
function getTypeScriptJsResolutionCandidates(basePath) {
  if (hasSupportedExtension(basePath)) {
    return [basePath];
  }
  return [
    ...TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.map(
      (extension) => `${basePath}${extension}`
    ),
    ...TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.map(
      (extension) => `${basePath}/index${extension}`
    )
  ];
}
function hasSupportedExtension(pathValue) {
  return TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.some(
    (extension) => pathValue.endsWith(extension)
  );
}

// src/core/repo-graph/build-import-edges.ts
var DEFAULT_MAX_IMPORT_SCAN_FILE_BYTES = 25e4;
var IMPORT_EXTRACTORS = [
  typescriptJsImportExtractor,
  pythonImportExtractor
];
async function buildImportEdges(input) {
  const maxFileBytes = input.maxFileBytes ?? DEFAULT_MAX_IMPORT_SCAN_FILE_BYTES;
  const repoFiles = new Set(
    input.fileIndex.files.map((file) => normalizeRepoPath(file.path))
  );
  const importEdgesByKey = /* @__PURE__ */ new Map();
  const diagnosticsByKey = /* @__PURE__ */ new Map();
  for (const file of input.fileIndex.files) {
    const filePath = normalizeRepoPath(file.path);
    const extractor = getExtractorForFile(filePath);
    if (!extractor) {
      continue;
    }
    if (file.sizeBytes > maxFileBytes) {
      addDiagnostic({
        diagnosticsByKey,
        diagnostic: {
          level: "info",
          code: "skipped-large-file",
          file: filePath,
          message: `Skipped import extraction for ${filePath} because it exceeds ${maxFileBytes} bytes.`
        }
      });
      continue;
    }
    let content;
    try {
      content = await readFile(path14.join(input.repoRoot, filePath), "utf8");
    } catch {
      addDiagnostic({
        diagnosticsByKey,
        diagnostic: {
          level: "warning",
          code: "read-error",
          file: filePath,
          message: `Could not read ${filePath} for import extraction.`
        }
      });
      continue;
    }
    const extractedImports = extractor.extractImports({
      filePath,
      content
    });
    for (const extractedImport of extractedImports) {
      processExtractedImport({
        filePath,
        extractedImport,
        extractor,
        repoFiles,
        importEdgesByKey,
        diagnosticsByKey
      });
    }
  }
  return {
    edges: Array.from(importEdgesByKey.values()).sort(compareEdges2),
    diagnostics: Array.from(diagnosticsByKey.values()).sort(compareDiagnostics)
  };
}
function processExtractedImport(input) {
  const resolution = resolveImport({
    filePath: input.filePath,
    extractedImport: input.extractedImport,
    extractor: input.extractor,
    repoFiles: input.repoFiles
  });
  if (resolution.status === "ignored") {
    return;
  }
  if (resolution.status === "unresolved") {
    addDiagnostic({
      diagnosticsByKey: input.diagnosticsByKey,
      diagnostic: {
        level: "warning",
        code: "unresolved-import",
        file: input.filePath,
        message: `Could not resolve local import "${input.extractedImport.specifier}" from ${input.filePath}.`
      }
    });
    return;
  }
  addImportEdge({
    importEdgesByKey: input.importEdgesByKey,
    edge: {
      from: input.filePath,
      to: resolution.resolvedPath,
      type: "imports",
      confidence: resolution.confidence,
      source: input.extractedImport.source,
      importSpecifier: input.extractedImport.specifier
    }
  });
}
function resolveImport(input) {
  if (input.extractor.source === "typescript-js-imports") {
    return resolveTypeScriptJsImport({
      importerPath: input.filePath,
      specifier: input.extractedImport.specifier,
      repoFiles: input.repoFiles
    });
  }
  if (input.extractor.source === "python-imports") {
    return resolvePythonImport({
      importerPath: input.filePath,
      specifier: input.extractedImport.specifier,
      repoFiles: input.repoFiles
    });
  }
  return {
    status: "ignored",
    reason: "external-package"
  };
}
function addImportEdge(input) {
  const key = getImportEdgeKey(input.edge);
  if (input.importEdgesByKey.has(key)) {
    return;
  }
  input.importEdgesByKey.set(key, RepoGraphEdgeSchema.parse(input.edge));
}
function getImportEdgeKey(edge) {
  return `${edge.from}\0${edge.to}\0${edge.type}`;
}
function addDiagnostic(input) {
  const key = getDiagnosticKey(input.diagnostic);
  if (input.diagnosticsByKey.has(key)) {
    return;
  }
  input.diagnosticsByKey.set(
    key,
    RepoGraphDiagnosticSchema.parse(input.diagnostic)
  );
}
function getDiagnosticKey(diagnostic) {
  return `${diagnostic.file ?? ""}\0${diagnostic.code}\0${diagnostic.message}`;
}
function getExtractorForFile(filePath) {
  const extension = getLowerExtension2(filePath);
  if (!extension) {
    return null;
  }
  return IMPORT_EXTRACTORS.find(
    (extractor) => extractor.extensions.includes(extension)
  ) ?? null;
}
function getLowerExtension2(filePath) {
  const fileName = filePath.split("/").at(-1) ?? filePath;
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return null;
  }
  return fileName.slice(dotIndex).toLowerCase();
}
function compareEdges2(a, b) {
  return a.from.localeCompare(b.from) || a.to.localeCompare(b.to) || a.type.localeCompare(b.type) || a.source.localeCompare(b.source) || (a.importSpecifier ?? "").localeCompare(b.importSpecifier ?? "");
}
function compareDiagnostics(a, b) {
  return (a.file ?? "").localeCompare(b.file ?? "") || a.code.localeCompare(b.code) || a.message.localeCompare(b.message);
}

// src/core/repo-graph/build-repo-graph.ts
async function buildRepoGraph(input) {
  const filesystemGraph = buildFilesystemGraph({
    repoRoot: input.repoRoot,
    fileIndex: input.fileIndex
  });
  const importGraph = await buildImportEdges({
    repoRoot: input.repoRoot,
    filesystemGraph,
    fileIndex: input.fileIndex
  });
  const nodes = sortNodes(dedupeNodes(filesystemGraph.nodes));
  const edges = sortEdges(
    dedupeEdges([...filesystemGraph.edges, ...importGraph.edges])
  );
  const diagnostics = sortDiagnostics(
    dedupeDiagnostics(importGraph.diagnostics)
  );
  const graph = {
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    graphVersion: 1,
    repoRoot: input.repoRoot,
    nodes,
    edges,
    diagnostics,
    stats: computeRepoGraphStats({
      nodes,
      edges,
      diagnostics
    })
  };
  return RepoGraphSchema.parse(graph);
}
function computeRepoGraphStats(input) {
  return {
    fileCount: input.nodes.filter((node) => node.kind === "file").length,
    directoryCount: input.nodes.filter((node) => node.kind === "directory").length,
    containsEdgeCount: input.edges.filter((edge) => edge.type === "contains").length,
    importEdgeCount: input.edges.filter((edge) => edge.type === "imports").length,
    unresolvedImportCount: input.diagnostics.filter(
      (diagnostic) => diagnostic.code === "unresolved-import"
    ).length,
    supportedLanguageFileCount: input.nodes.filter(
      (node) => node.kind === "file" && isSupportedImportLanguage(node.language)
    ).length
  };
}
function dedupeNodes(nodes) {
  const nodesById = /* @__PURE__ */ new Map();
  for (const node of nodes) {
    if (!nodesById.has(node.id)) {
      nodesById.set(node.id, node);
    }
  }
  return Array.from(nodesById.values());
}
function dedupeEdges(edges) {
  const edgesByKey = /* @__PURE__ */ new Map();
  for (const edge of edges) {
    const key = `${edge.from}\0${edge.to}\0${edge.type}`;
    if (!edgesByKey.has(key)) {
      edgesByKey.set(key, edge);
    }
  }
  return Array.from(edgesByKey.values());
}
function dedupeDiagnostics(diagnostics) {
  const diagnosticsByKey = /* @__PURE__ */ new Map();
  for (const diagnostic of diagnostics) {
    const key = `${diagnostic.file ?? ""}\0${diagnostic.code}\0${diagnostic.message}`;
    if (!diagnosticsByKey.has(key)) {
      diagnosticsByKey.set(key, diagnostic);
    }
  }
  return Array.from(diagnosticsByKey.values());
}
function sortNodes(nodes) {
  return [...nodes].sort((a, b) => a.path.localeCompare(b.path));
}
function sortEdges(edges) {
  return [...edges].sort(compareEdges3);
}
function sortDiagnostics(diagnostics) {
  return [...diagnostics].sort(compareDiagnostics2);
}
function compareEdges3(a, b) {
  return a.from.localeCompare(b.from) || a.to.localeCompare(b.to) || a.type.localeCompare(b.type) || a.source.localeCompare(b.source) || (a.importSpecifier ?? "").localeCompare(b.importSpecifier ?? "");
}
function compareDiagnostics2(a, b) {
  return (a.file ?? "").localeCompare(b.file ?? "") || a.code.localeCompare(b.code) || a.message.localeCompare(b.message);
}
function isSupportedImportLanguage(language) {
  return language === "typescript" || language === "javascript" || language === "python";
}

// src/core/reading-plans/reading-plan-budgets.ts
var READING_PLAN_BATCH_BUDGET = {
  maxFiles: 10,
  maxBytes: 6e4
};
var READING_PLAN_BUDGETS = {
  "repo-analysis": { maxFiles: 40, maxBytes: 24e4 },
  architecture: { maxFiles: 60, maxBytes: 36e4 },
  "business-logic": { maxFiles: 50, maxBytes: 3e5 },
  conventions: { maxFiles: 50, maxBytes: 3e5 },
  testing: { maxFiles: 50, maxBytes: 3e5 }
};

// src/core/reading-plans/build-plan-common.ts
function createBuildContext(input) {
  return {
    ...input,
    fileIndexByPath: new Map(input.fileIndex.files.map((file) => [file.path, file])),
    codebaseFileByPath: new Map(input.codebaseMap.files.map((file) => [file.path, file]))
  };
}
function getFilesByRole(context, roles) {
  return context.codebaseMap.files.filter(
    (file) => roles.some((role) => file.roles.includes(role))
  );
}
function getFilesBySignalKind(context, signalKinds) {
  return context.codebaseMap.files.filter(
    (file) => file.signals.some((signal) => signalKinds.includes(signal.kind))
  );
}
function getEntrypointFiles(context) {
  const paths = new Set(context.codebaseMap.entrypoints.map((entrypoint) => entrypoint.path));
  for (const file of context.codebaseMap.files) {
    if (file.isEntrypoint) paths.add(file.path);
  }
  if (paths.size === 0) {
    for (const filePath of context.graphSummary.entrypoints) paths.add(filePath);
  }
  return filesForPaths(context, paths);
}
function getCentralFiles2(context) {
  const paths = new Set(
    context.codebaseMap.files.filter((file) => file.isCentral).map((file) => file.path)
  );
  for (const cluster of context.codebaseMap.clusters) {
    for (const file of cluster.centralFiles) paths.add(file.path);
  }
  return filesForPaths(context, paths);
}
function getTestFiles(context) {
  return context.codebaseMap.files.filter((file) => file.isTest);
}
function getFixtureFiles(context) {
  return context.codebaseMap.files.filter((file) => file.isFixture);
}
function getConfigFiles(context) {
  return getFilesByRole(context, ["config", "project-config"]);
}
function getFilesWithWarningsOrUnresolvedImports(context) {
  const paths = new Set(context.codebaseMap.unresolvedImports.byFile.map((item) => item.path));
  for (const warning of context.fileIndex.warnings ?? []) {
    if (warning.filePath) paths.add(warning.filePath);
  }
  return filesForPaths(context, paths);
}
function rankCandidates(context, candidates, ranking = {}) {
  const unique = new Map(candidates.map((file) => [file.path, file]));
  return [...unique.values()].sort((left, right) => {
    const scoreDifference = scoreCandidate(context, right, ranking) - scoreCandidate(context, left, ranking);
    return scoreDifference || left.path.localeCompare(right.path);
  });
}
function dedupePlanFilesWithinBatch(files) {
  const seen = /* @__PURE__ */ new Set();
  return files.filter((file) => {
    if (seen.has(file.path)) return false;
    seen.add(file.path);
    return true;
  });
}
function applyBatchBudget(files) {
  const selected = [];
  let estimatedBytes = 0;
  for (const file of files) {
    if (selected.length >= READING_PLAN_BATCH_BUDGET.maxFiles) break;
    if (estimatedBytes + file.estimatedBytes > READING_PLAN_BATCH_BUDGET.maxBytes) break;
    selected.push(file);
    estimatedBytes += file.estimatedBytes;
  }
  return { files: selected, estimatedBytes, truncated: selected.length < files.length };
}
function estimateBytesForPath(context, filePath) {
  return context.fileIndexByPath.get(filePath)?.sizeBytes ?? context.repoGraph.nodes.find((node) => node.kind === "file" && node.path === filePath)?.sizeBytes ?? 0;
}
function buildBatch(context, planKind, order, definition) {
  const ranked = rankCandidates(context, definition.candidates, definition.ranking);
  const planFiles = dedupePlanFilesWithinBatch(
    ranked.map((file) => toPlanFile(context, file, definition))
  );
  const budgeted = applyBatchBudget(planFiles);
  const warnings = [];
  if (planFiles.length === 0) {
    warnings.push({
      code: "missing-batch-category",
      message: `No files matched the ${definition.title.toLowerCase()} selection rule.`,
      planKind,
      batchId: definition.id,
      severity: "info"
    });
  }
  if (budgeted.truncated) {
    warnings.push({
      code: "batch-truncated",
      message: `Batch ${definition.id} was truncated from ${planFiles.length} to ${budgeted.files.length} files.`,
      planKind,
      batchId: definition.id,
      severity: "warning"
    });
  }
  return {
    batch: {
      id: definition.id,
      title: definition.title,
      purpose: definition.purpose,
      order,
      selectionRule: definition.selectionRule,
      files: budgeted.files,
      budget: {
        maxFiles: READING_PLAN_BATCH_BUDGET.maxFiles,
        estimatedBytes: budgeted.estimatedBytes,
        truncated: budgeted.truncated
      }
    },
    warnings
  };
}
function buildPlan(context, definition) {
  const built = definition.batches.map(
    (batch, index) => buildBatch(context, definition.kind, index + 1, batch)
  );
  const warnings = built.flatMap((item) => item.warnings);
  const limit = READING_PLAN_BUDGETS[definition.kind];
  let fileCount = 0;
  let estimatedBytes = 0;
  let planTruncated = false;
  const batches = built.map(({ batch }) => {
    const files = [];
    for (const file of batch.files) {
      if (fileCount >= limit.maxFiles || estimatedBytes + file.estimatedBytes > limit.maxBytes) {
        planTruncated = true;
        continue;
      }
      files.push(file);
      fileCount += 1;
      estimatedBytes += file.estimatedBytes;
    }
    const batchTruncated = batch.budget.truncated || files.length < batch.files.length;
    if (files.length < batch.files.length && !batch.budget.truncated) {
      warnings.push({
        code: "plan-batch-truncated",
        message: `Batch ${batch.id} lost ${batch.files.length - files.length} file references to the plan budget.`,
        planKind: definition.kind,
        batchId: batch.id,
        severity: "warning"
      });
    }
    return {
      ...batch,
      files,
      budget: {
        ...batch.budget,
        estimatedBytes: files.reduce((total, file) => total + file.estimatedBytes, 0),
        truncated: batchTruncated
      }
    };
  });
  if (planTruncated) {
    warnings.push({
      code: "plan-truncated",
      message: `Plan ${definition.kind} was truncated to ${fileCount} file references.`,
      planKind: definition.kind,
      severity: "warning"
    });
  }
  return {
    kind: definition.kind,
    targetMemoryFile: definition.targetMemoryFile,
    title: definition.title,
    purpose: definition.purpose,
    inputStrategy: {
      agentFocus: definition.agentFocus,
      shouldAnswer: definition.shouldAnswer,
      shouldAvoid: definition.shouldAvoid
    },
    batches,
    budget: {
      maxFiles: limit.maxFiles,
      estimatedBytes,
      truncated: planTruncated
    },
    warnings: sortWarnings(warnings)
  };
}
function combineFiles(...groups) {
  return groups.flat();
}
function codebaseEvidence(detail) {
  return [{ source: "codebase-map", detail }];
}
function filesForPaths(context, paths) {
  return [...paths].sort((left, right) => left.localeCompare(right)).flatMap((filePath) => {
    const file = context.codebaseFileByPath.get(filePath);
    return file ? [file] : [];
  });
}
function scoreCandidate(context, file, ranking) {
  let score = 0;
  score += (ranking.roles ?? []).filter((role) => file.roles.includes(role)).length * 1e3;
  score += file.signals.filter((signal) => (ranking.signalKinds ?? []).includes(signal.kind)).length * 700;
  if (ranking.preferredPaths?.has(file.path)) score += 1500;
  if (ranking.preferEntrypoints && file.isEntrypoint) score += 1200;
  if (ranking.preferCentral && file.isCentral) score += 1e3;
  score += file.fanIn * 20 + file.fanOut * 10;
  score -= Math.floor(estimateBytesForPath(context, file.path) / 1e4);
  return score;
}
function toPlanFile(context, file, definition) {
  const indexFile = context.fileIndexByPath.get(file.path);
  const roleInBatch = typeof definition.roleInBatch === "function" ? definition.roleInBatch(file) : definition.roleInBatch;
  const reason = typeof definition.reason === "function" ? definition.reason(file) : definition.reason;
  const evidence = definition.evidence?.(file) ?? codebaseEvidence(
    `Selected from roles [${file.roles.join(", ") || "none"}], signals [${file.signals.map((signal) => signal.kind).join(", ") || "none"}], central=${file.isCentral}, entrypoint=${file.isEntrypoint}.`
  );
  return {
    path: file.path,
    roleInBatch,
    reason,
    evidence: [...evidence].sort(
      (left, right) => left.source.localeCompare(right.source) || left.detail.localeCompare(right.detail)
    ),
    confidence: getConfidence(file, indexFile),
    estimatedBytes: estimateBytesForPath(context, file.path)
  };
}
function getConfidence(file, indexFile) {
  if (file.signals.some((signal) => signal.confidence === "observed")) return "observed";
  return indexFile?.confidence ?? "inferred";
}
function sortWarnings(warnings) {
  return [...warnings].sort(
    (left, right) => (left.planKind ?? "").localeCompare(right.planKind ?? "") || (left.batchId ?? "").localeCompare(right.batchId ?? "") || (left.path ?? "").localeCompare(right.path ?? "") || left.code.localeCompare(right.code) || left.message.localeCompare(right.message)
  );
}

// src/core/reading-plans/build-architecture-plan.ts
function buildArchitecturePlan(context) {
  const sourceCentral = getCentralFiles2(context).filter((file) => !file.isTest && !file.isFixture);
  const relatedClusterPaths = new Set(
    context.codebaseMap.clusters.filter((cluster) => cluster.dependencies.length > 0 || cluster.consumers.length > 0).flatMap((cluster) => cluster.centralFiles.map((file) => file.path))
  );
  const crossCluster = context.codebaseMap.files.filter(
    (file) => relatedClusterPaths.has(file.path) && !file.isTest && !file.isFixture
  );
  const architectureContracts = combineFiles(
    getFilesByRole(context, ["schema", "type", "model"]),
    getFilesBySignalKind(context, ["schema", "validation", "database"])
  ).filter((file) => !file.isTest && !file.isFixture);
  return buildPlan(context, {
    kind: "architecture",
    targetMemoryFile: ".bridger/memory/architecture.md",
    title: "Architecture reading plan",
    purpose: "Explain entrypoints, subsystems, dependency flow, central files, and contract boundaries.",
    agentFocus: "Trace execution starts, subsystem boundaries, existing cluster relations, and shared contracts.",
    shouldAnswer: ["Where does execution start?", "What are the main subsystems and dependency directions?", "Which files define central contracts or schemas?"],
    shouldAvoid: ["Test-heavy context.", "Affected-file traversal.", "Invented architectural layers."],
    batches: [
      {
        id: "entrypoints-and-command-surfaces",
        title: "Entrypoints and command surfaces",
        purpose: "Understand how execution starts.",
        selectionRule: "Entrypoints plus implemented command, route, API route, and CLI metadata.",
        candidates: combineFiles(getEntrypointFiles(context), getFilesByRole(context, ["command", "route", "api-route"]), getFilesBySignalKind(context, ["cli"])).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : file.roles.includes("route") || file.roles.includes("api-route") ? "route" : "supporting-context",
        reason: "Defines an existing entry or command surface.",
        ranking: { roles: ["command", "route", "api-route"], signalKinds: ["cli"], preferEntrypoints: true }
      },
      {
        id: "source-clusters",
        title: "Source clusters and central files",
        purpose: "Understand the main source subsystems and their central files.",
        selectionRule: "Non-test central files from source and mixed CodebaseMap clusters.",
        candidates: sourceCentral.filter((file) => {
          const cluster = context.codebaseMap.clusters.find((item) => item.id === file.clusterId);
          return cluster?.kind === "source" || cluster?.kind === "mixed";
        }),
        roleInBatch: "cluster-central-file",
        reason: "Is central to a source or mixed cluster.",
        ranking: { preferCentral: true }
      },
      {
        id: "cross-cluster-dependencies",
        title: "Cross-cluster dependency flow",
        purpose: "Read central files in clusters with existing dependency or consumer relations.",
        selectionRule: "Cluster central files where CodebaseMap dependencies or consumers are non-empty.",
        candidates: crossCluster,
        roleInBatch: "cluster-central-file",
        reason: "Belongs to a cluster with an existing cross-cluster relation.",
        ranking: { preferCentral: true }
      },
      {
        id: "contracts-and-schemas",
        title: "Contracts, schemas, and types",
        purpose: "Identify shared contracts and validation boundaries.",
        selectionRule: "Implemented schema, type, and model roles plus schema, validation, and database signals.",
        candidates: architectureContracts,
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : "contract",
        reason: "Carries an implemented contract role or contract-related signal.",
        ranking: { roles: ["schema", "type", "model"], signalKinds: ["schema", "validation", "database"], preferCentral: true }
      },
      {
        id: "architecture-warnings",
        title: "Architecture warnings and unresolved imports",
        purpose: "Highlight deterministic structural uncertainty.",
        selectionRule: "Unresolved-import paths and path-specific FileIndex warnings.",
        candidates: getFilesWithWarningsOrUnresolvedImports(context),
        roleInBatch: "risk-signal",
        reason: "Has a deterministic structural diagnostic."
      }
    ]
  });
}

// src/core/reading-plans/build-business-logic-plan.ts
function buildBusinessLogicPlan(context) {
  const workflowRoles = ["service", "builder", "writer", "reader", "generator"];
  return buildPlan(context, {
    kind: "business-logic",
    targetMemoryFile: ".bridger/memory/business-logic.md",
    title: "Business logic reading plan",
    purpose: "Extract visible product workflows, user-facing behavior, and durable artifact contracts.",
    agentFocus: "Understand commands, workflow implementation, artifacts, and behavior demonstrated by tests.",
    shouldAnswer: ["What workflows and commands exist?", "What artifacts are produced?", "How does repository evidence become context?"],
    shouldAvoid: ["Invented domain concepts.", "Generic low-signal utilities.", "Behavior not visible in selected files."],
    batches: [
      {
        id: "user-facing-workflow-entrypoints",
        title: "User-facing workflow entrypoints",
        purpose: "Read files that expose user-visible workflows.",
        selectionRule: "Entrypoints, command and route roles, and implemented CLI signals.",
        candidates: combineFiles(getEntrypointFiles(context), getFilesByRole(context, ["command", "route", "api-route"]), getFilesBySignalKind(context, ["cli"])),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : file.roles.includes("route") || file.roles.includes("api-route") ? "route" : "supporting-context",
        reason: "Exposes a deterministic user-facing workflow surface.",
        ranking: { roles: ["command", "route", "api-route"], signalKinds: ["cli"], preferEntrypoints: true }
      },
      {
        id: "workflow-implementation-files",
        title: "Workflow implementation files",
        purpose: "Read central implementation files for product workflows.",
        selectionRule: "Implemented service, builder, writer, reader, and generator roles, prioritized by centrality.",
        candidates: combineFiles(getFilesByRole(context, [...workflowRoles]), getCentralFiles2(context).filter((file) => file.roles.some((role) => workflowRoles.includes(role)))).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.roles.includes("service") ? "service" : "supporting-context",
        reason: "Has an implemented workflow role in the current artifacts.",
        ranking: { roles: [...workflowRoles], preferCentral: true }
      },
      {
        id: "artifacts-and-contracts",
        title: "Artifacts, schemas, and contracts",
        purpose: "Understand durable objects and output contracts.",
        selectionRule: "Implemented schema, model, type, config, writer, or generator roles and contract signals.",
        candidates: combineFiles(getFilesByRole(context, ["schema", "model", "type", "config", "project-config", "writer", "generator"]), getFilesBySignalKind(context, ["schema", "validation", "database"])).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : file.roles.includes("config") || file.roles.includes("project-config") ? "config" : "contract",
        reason: "Defines or writes a durable artifact or contract using implemented metadata.",
        ranking: { roles: ["schema", "model", "type", "writer", "generator", "project-config", "config"], signalKinds: ["schema", "validation", "database"] }
      },
      {
        id: "behavior-tests",
        title: "Representative behavior tests",
        purpose: "Include tests that clarify product behavior.",
        selectionRule: "CodebaseMap isTest files ranked by centrality and graph degree.",
        candidates: getTestFiles(context),
        roleInBatch: "representative-test",
        reason: "Demonstrates behavior using an existing test classification.",
        ranking: { signalKinds: ["testing"], preferCentral: true }
      }
    ]
  });
}

// src/core/reading-plans/build-conventions-plan.ts
var REPRESENTATIVE_ROLES = [
  "service",
  "utility",
  "component",
  "command",
  "route",
  "api-route",
  "builder",
  "generator",
  "resolver",
  "extractor",
  "reader",
  "writer"
];
function buildConventionsPlan(context) {
  const representatives = REPRESENTATIVE_ROLES.flatMap(
    (role) => rankCandidates(context, getFilesByRole(context, [role]), { roles: [role], preferCentral: true }).slice(0, 3)
  );
  return buildPlan(context, {
    kind: "conventions",
    targetMemoryFile: ".bridger/memory/conventions.md",
    title: "Conventions reading plan",
    purpose: "Explain implementation style, organization, naming, typing, and recurring code patterns.",
    agentFocus: "Compare representative implementations across only the roles already classified by deterministic artifacts.",
    shouldAnswer: ["How is code organized?", "How are contracts and workflows implemented?", "How are commands and tests written?"],
    shouldAvoid: ["Exhaustive implementation coverage.", "Conventions inferred only from filenames.", "Random files without role evidence."],
    batches: [
      {
        id: "representative-source-by-role",
        title: "Representative source files by role",
        purpose: "Show implementation style across existing role categories.",
        selectionRule: "Up to three ranked files for each implemented representative source role.",
        candidates: representatives,
        roleInBatch: (file) => file.roles.includes("service") ? "service" : file.roles.includes("utility") ? "utility" : "convention-example",
        reason: (file) => `Represents implemented role metadata: ${file.roles.filter((role) => REPRESENTATIVE_ROLES.includes(role)).join(", ")}.`,
        ranking: { roles: REPRESENTATIVE_ROLES, preferCentral: true }
      },
      {
        id: "models-schemas-types",
        title: "Models, schemas, and types",
        purpose: "Show data-contract and typing style.",
        selectionRule: "Implemented schema, model, and type roles plus schema and validation signals.",
        candidates: combineFiles(getFilesByRole(context, ["schema", "model", "type"]), getFilesBySignalKind(context, ["schema", "validation"])),
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : "contract",
        reason: "Demonstrates an existing data-contract pattern.",
        ranking: { roles: ["schema", "model", "type"], signalKinds: ["schema", "validation"] }
      },
      {
        id: "cli-and-workflow-style",
        title: "CLI and workflow style",
        purpose: "Show user-facing command implementation patterns.",
        selectionRule: "Command roles, CLI signals, and relevant deterministic entrypoints.",
        candidates: combineFiles(getFilesByRole(context, ["command"]), getFilesBySignalKind(context, ["cli"]), getEntrypointFiles(context)),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : "convention-example",
        reason: "Demonstrates an implemented command or workflow entry pattern.",
        ranking: { roles: ["command"], signalKinds: ["cli"], preferEntrypoints: true }
      },
      {
        id: "representative-tests",
        title: "Representative test style",
        purpose: "Show testing conventions and expectations.",
        selectionRule: "Files classified as tests by CodebaseMap.",
        candidates: getTestFiles(context),
        roleInBatch: "representative-test",
        reason: "Provides an existing example of test style.",
        ranking: { signalKinds: ["testing"] }
      },
      {
        id: "config-and-tooling",
        title: "Config and tooling conventions",
        purpose: "Show build, test, lint, and tooling configuration.",
        selectionRule: "Config and project-config roles, prioritizing testing signals.",
        candidates: combineFiles(
          getConfigFiles(context),
          getFilesBySignalKind(context, ["testing"]).filter(
            (file) => file.roles.includes("config") || file.roles.includes("project-config")
          )
        ),
        roleInBatch: "config",
        reason: "Defines an existing tooling or project convention.",
        ranking: { roles: ["project-config", "config"], signalKinds: ["testing"] }
      }
    ]
  });
}

// src/core/reading-plans/build-repo-analysis-plan.ts
function buildRepoAnalysisPlan(context) {
  const clusterRepresentatives = [];
  for (const cluster of context.codebaseMap.clusters) {
    if (!(/* @__PURE__ */ new Set(["source", "mixed", "scripts"])).has(cluster.kind)) continue;
    const centralPath = cluster.centralFiles[0]?.path;
    const fallbackPath = [...cluster.files].sort()[0];
    const file = context.codebaseFileByPath.get(centralPath ?? fallbackPath ?? "");
    if (file && !file.isTest && !file.isFixture) clusterRepresentatives.push(file);
  }
  return buildPlan(context, {
    kind: "repo-analysis",
    targetMemoryFile: ".bridger/memory/repo-analysis.md",
    title: "Repository analysis reading plan",
    purpose: "Provide broad repository orientation from deterministic project metadata and codebase structure.",
    agentFocus: "Identify the project, stack, major areas, executable surfaces, and deterministic unknowns.",
    shouldAnswer: [
      "What kind of project is this and what stack does it use?",
      "What are the main directories, clusters, and executable surfaces?",
      "What is known and what remains uncertain?"
    ],
    shouldAvoid: ["Exhaustive source coverage.", "Deep implementation summaries.", "Claims unsupported by selected evidence."],
    batches: [
      {
        id: "project-metadata",
        title: "Project metadata and root orientation",
        purpose: "Read project-level files that explain repository identity, stack, scripts, and documentation.",
        selectionRule: "Project config, package metadata, and documentation roles from CodebaseMap.",
        candidates: combineFiles(getConfigFiles(context), getFilesByRole(context, ["docs"])),
        roleInBatch: (file) => file.roles.includes("docs") ? "orientation" : "config",
        reason: "Provides deterministic project-level orientation.",
        evidence: (file) => [
          {
            source: "codebase-map",
            detail: `Selected from implemented roles [${file.roles.join(", ")}].`
          },
          ...file.roles.includes("project-config") ? [{
            source: "repo-context",
            detail: `Repository context reports package manager ${context.repoContext.stack.packageManager || "unknown"} and ${Object.values(context.repoContext.commands).filter(Boolean).length} detected commands.`
          }] : []
        ],
        ranking: { roles: ["project-config", "config", "docs"] }
      },
      {
        id: "main-entrypoints",
        title: "Main entrypoints",
        purpose: "Identify how the project is entered or executed.",
        selectionRule: "CodebaseMap entrypoints and isEntrypoint files; GraphSummary only when the map has none.",
        candidates: getEntrypointFiles(context),
        roleInBatch: "entrypoint",
        reason: "Marks an existing deterministic executable surface.",
        ranking: { preferEntrypoints: true }
      },
      {
        id: "major-clusters",
        title: "Major codebase areas",
        purpose: "Provide one representative central file for each major source cluster.",
        selectionRule: "Central file, or first stable file, from source, mixed, and scripts clusters.",
        candidates: clusterRepresentatives,
        roleInBatch: "cluster-central-file",
        reason: "Represents a major non-test codebase cluster.",
        ranking: { preferCentral: true }
      },
      {
        id: "warnings-and-unknowns",
        title: "Warnings and uncertain areas",
        purpose: "Surface files tied to deterministic warnings and unresolved imports.",
        selectionRule: "CodebaseMap unresolved-import paths and FileIndex path-specific warning files.",
        candidates: getFilesWithWarningsOrUnresolvedImports(context),
        roleInBatch: "risk-signal",
        reason: "Has an existing unresolved import or path-specific scan warning."
      }
    ]
  });
}

// src/core/reading-plans/build-testing-plan.ts
function buildTestingPlan(context) {
  const tests = getTestFiles(context);
  const rankedTests = rankCandidates(context, tests, {
    signalKinds: ["testing"],
    preferCentral: true
  });
  const selectedTestPaths = /* @__PURE__ */ new Set();
  let selectedTestBytes = 0;
  for (const test of rankedTests) {
    const estimatedBytes = estimateBytesForPath(context, test.path);
    if (selectedTestPaths.size >= READING_PLAN_BATCH_BUDGET.maxFiles) break;
    if (selectedTestBytes + estimatedBytes > READING_PLAN_BATCH_BUDGET.maxBytes) break;
    selectedTestPaths.add(test.path);
    selectedTestBytes += estimatedBytes;
  }
  const sourceUnderTestPaths = new Set(
    context.repoGraph.edges.filter((edge) => edge.type === "imports" && selectedTestPaths.has(edge.from)).map((edge) => edge.to)
  );
  const sourceUnderTest = context.codebaseMap.files.filter(
    (file) => sourceUnderTestPaths.has(file.path) && !file.isTest && !file.isFixture
  );
  const testWarnings = getFilesWithWarningsOrUnresolvedImports(context).filter((file) => file.isTest);
  const plan = buildPlan(context, {
    kind: "testing",
    targetMemoryFile: ".bridger/memory/testing.md",
    title: "Testing reading plan",
    purpose: "Explain test tooling, test patterns, fixtures, source relationships, and verification behavior.",
    agentFocus: "Identify real test commands and configuration, representative tests, fixtures, and directly imported source files.",
    shouldAnswer: ["What framework and commands are used?", "What patterns do tests and fixtures follow?", "Which source areas have direct test import evidence?"],
    shouldAvoid: ["Every test file.", "Speculative source-under-test matching.", "Architecture-only entrypoints."],
    batches: [
      {
        id: "test-setup-and-commands",
        title: "Test setup and commands",
        purpose: "Identify test tooling and verification commands from real files.",
        selectionRule: "Project metadata/config files and files carrying implemented testing signals.",
        candidates: combineFiles(
          getConfigFiles(context),
          getFilesBySignalKind(context, ["testing"]).filter(
            (file) => file.roles.includes("config") || file.roles.includes("project-config")
          )
        ),
        roleInBatch: "config",
        reason: "Provides file-backed evidence for test setup or commands.",
        evidence: (file) => [
          {
            source: "codebase-map",
            detail: `Selected from implemented config roles [${file.roles.join(", ")}].`
          },
          {
            source: "repo-context",
            detail: `Repository context reports test frameworks [${[...context.repoContext.stack.testFramework].sort().join(", ") || "none"}] and test command ${context.repoContext.commands.test ?? "none"}.`
          }
        ],
        ranking: { roles: ["project-config", "config"], signalKinds: ["testing"] }
      },
      {
        id: "representative-tests",
        title: "Representative tests",
        purpose: "Read tests that demonstrate test style across available clusters.",
        selectionRule: "CodebaseMap isTest files ranked by testing signals, centrality, graph degree, and path.",
        candidates: tests,
        roleInBatch: "representative-test",
        reason: "Is classified as a test by CodebaseMap.",
        ranking: { signalKinds: ["testing"], preferCentral: true }
      },
      {
        id: "fixtures-and-test-data",
        title: "Fixtures and test data",
        purpose: "Understand existing fixture patterns.",
        selectionRule: "CodebaseMap isFixture files and cluster fixture lists.",
        candidates: getFixtureFiles(context),
        roleInBatch: "fixture",
        reason: "Is classified as fixture data by CodebaseMap."
      },
      {
        id: "source-under-test",
        title: "Source files under test",
        purpose: "Read source files directly imported by selected tests.",
        selectionRule: "Targets of existing RepoGraph import edges whose source is a CodebaseMap test file.",
        candidates: sourceUnderTest,
        roleInBatch: "supporting-context",
        reason: "Is the target of an existing graph import edge from a classified test file.",
        evidence: () => [{ source: "repo-graph", detail: "Direct target of an existing import edge from a CodebaseMap test file." }],
        ranking: { preferCentral: true }
      },
      {
        id: "test-warnings",
        title: "Test coverage warnings",
        purpose: "Surface files tied to deterministic test diagnostics.",
        selectionRule: "Test files with unresolved imports or path-specific FileIndex warnings.",
        candidates: testWarnings,
        roleInBatch: "risk-signal",
        reason: "Has an existing test-related diagnostic."
      }
    ]
  });
  if (tests.length === 0 && context.repoContext.stack.testFramework.length > 0) {
    plan.warnings = sortWarnings([
      ...plan.warnings,
      {
        code: "test-framework-without-tests",
        message: "RepoContext reports a test framework, but CodebaseMap contains no test files.",
        planKind: "testing",
        severity: "warning"
      }
    ]);
  }
  return plan;
}

// src/core/reading-plans/models/reading-plans.ts
import { z as z11 } from "zod";
var ReadingPlanKindSchema = z11.enum([
  "repo-analysis",
  "architecture",
  "business-logic",
  "conventions",
  "testing"
]);
var ReadingPlanFileRoleSchema = z11.enum([
  "orientation",
  "entrypoint",
  "cluster-central-file",
  "contract",
  "schema",
  "model",
  "service",
  "route",
  "utility",
  "test-setup",
  "representative-test",
  "fixture",
  "config",
  "convention-example",
  "risk-signal",
  "supporting-context"
]);
var ReadingPlanEvidenceSchema = z11.object({
  source: z11.enum([
    "file-index",
    "repo-context",
    "repo-graph",
    "graph-summary",
    "codebase-map"
  ]),
  detail: z11.string().min(1)
});
var ReadingPlanFileSchema = z11.object({
  path: z11.string().min(1),
  roleInBatch: ReadingPlanFileRoleSchema,
  reason: z11.string().min(1),
  evidence: z11.array(ReadingPlanEvidenceSchema).min(1),
  confidence: ConfidenceSchema,
  estimatedBytes: z11.number().int().nonnegative()
});
var ReadingPlanWarningSchema = z11.object({
  code: z11.string().min(1),
  message: z11.string().min(1),
  planKind: ReadingPlanKindSchema.optional(),
  batchId: z11.string().min(1).optional(),
  path: z11.string().min(1).optional(),
  severity: z11.enum(["info", "warning"])
});
var ReadingBudgetSchema = z11.object({
  maxFiles: z11.number().int().positive(),
  estimatedBytes: z11.number().int().nonnegative(),
  truncated: z11.boolean()
});
var ReadingBatchSchema = z11.object({
  id: z11.string().min(1),
  title: z11.string().min(1),
  purpose: z11.string().min(1),
  order: z11.number().int().positive(),
  selectionRule: z11.string().min(1),
  files: z11.array(ReadingPlanFileSchema),
  budget: ReadingBudgetSchema
});
var ReadingPlanSchema = z11.object({
  kind: ReadingPlanKindSchema,
  targetMemoryFile: z11.string().min(1),
  title: z11.string().min(1),
  purpose: z11.string().min(1),
  inputStrategy: z11.object({
    agentFocus: z11.string().min(1),
    shouldAnswer: z11.array(z11.string().min(1)),
    shouldAvoid: z11.array(z11.string().min(1))
  }),
  batches: z11.array(ReadingBatchSchema),
  budget: ReadingBudgetSchema,
  warnings: z11.array(ReadingPlanWarningSchema)
});
var ReadingPlansStatsSchema = z11.object({
  planCount: z11.number().int().nonnegative(),
  batchCount: z11.number().int().nonnegative(),
  uniqueFileCount: z11.number().int().nonnegative(),
  repeatedFileReferences: z11.number().int().nonnegative(),
  estimatedTotalBytes: z11.number().int().nonnegative()
});
var ReadingPlansSchema = z11.object({
  schemaVersion: z11.literal(1),
  generatedAt: z11.iso.datetime(),
  sourceArtifacts: z11.object({
    fileIndexSchemaVersion: z11.number().int().positive().optional(),
    repoGraphVersion: z11.union([z11.string(), z11.number()]).optional(),
    graphSummaryVersion: z11.union([z11.string(), z11.number()]).optional(),
    codebaseMapSchemaVersion: z11.number().int().positive().optional()
  }),
  plans: z11.array(ReadingPlanSchema).length(5),
  stats: ReadingPlansStatsSchema,
  warnings: z11.array(ReadingPlanWarningSchema)
});

// src/core/reading-plans/build-reading-plans.ts
function buildReadingPlans(input) {
  const context = createBuildContext(input);
  const plans = [
    buildRepoAnalysisPlan(context),
    buildArchitecturePlan(context),
    buildBusinessLogicPlan(context),
    buildConventionsPlan(context),
    buildTestingPlan(context)
  ];
  const warnings = [
    ...input.codebaseMap.warnings.map((message) => ({
      code: "codebase-map-warning",
      message,
      severity: "warning"
    })),
    ...(input.fileIndex.warnings ?? []).map((warning) => ({
      code: warning.code,
      message: warning.message,
      ...warning.filePath ? { path: warning.filePath } : {},
      severity: warning.severity
    }))
  ];
  const allFiles = plans.flatMap(
    (plan) => plan.batches.flatMap((batch) => batch.files)
  );
  const uniquePaths = new Set(allFiles.map((file) => file.path));
  return ReadingPlansSchema.parse({
    schemaVersion: 1,
    generatedAt: (/* @__PURE__ */ new Date()).toISOString(),
    sourceArtifacts: {
      ...input.fileIndex.schemaVersion ? { fileIndexSchemaVersion: input.fileIndex.schemaVersion } : {},
      repoGraphVersion: input.repoGraph.graphVersion,
      graphSummaryVersion: input.graphSummary.graphVersion,
      codebaseMapSchemaVersion: input.codebaseMap.schemaVersion
    },
    plans,
    stats: {
      planCount: plans.length,
      batchCount: plans.reduce((total, plan) => total + plan.batches.length, 0),
      uniqueFileCount: uniquePaths.size,
      repeatedFileReferences: allFiles.length - uniquePaths.size,
      estimatedTotalBytes: allFiles.reduce(
        (total, file) => total + file.estimatedBytes,
        0
      )
    },
    warnings: sortWarnings(warnings)
  });
}

// src/shared/logger.ts
function isDebugLoggingEnabled() {
  if (process.env.DEBUG === "bridger") {
    return true;
  }
  return process.env.npm_lifecycle_event === "dev";
}
var logger = {
  info(message) {
    console.log(message);
  },
  warn(message) {
    console.warn(`Warning: ${message}`);
  },
  error(message) {
    console.error(`Error: ${message}`);
  },
  debug(message) {
    if (isDebugLoggingEnabled()) {
      console.log(message);
    }
  }
};

// src/core/utils/paths.ts
import path15 from "path";
function resolveRepoRoot(input) {
  return path15.resolve(input ?? process.cwd());
}

// src/cli/commands/inspect.ts
var COMMAND_ORDER = [
  "install",
  "dev",
  "build",
  "lint",
  "typecheck",
  "test",
  "format"
];
function formatList(values) {
  return values.length > 0 ? values.join(", ") : "none";
}
function formatCommandValue(value) {
  return value !== void 0 ? value : "none";
}
function formatQuantity(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}
function formatBytes(bytes) {
  if (bytes === void 0) {
    return "unknown";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}
function buildImportantFileInspection(importantFile, fileByPath) {
  const indexedFile = fileByPath.get(importantFile.path);
  return {
    path: importantFile.path,
    reason: importantFile.reason,
    sizeBytes: indexedFile?.sizeBytes,
    tags: indexedFile?.tags
  };
}
async function buildInspectResult(repoRoot) {
  const { repoContext, fileIndex } = await buildRepoContextArtifacts(repoRoot);
  const projectState = await buildProjectStateInspection(repoRoot);
  const fileByPath = new Map(fileIndex.files.map((file) => [file.path, file]));
  const importantFiles = repoContext.importantFiles.map(
    (importantFile) => buildImportantFileInspection(importantFile, fileByPath)
  );
  const estimatedImportantFilesSizeBytes = importantFiles.reduce((total, file) => {
    return total + (file.sizeBytes ?? 0);
  }, 0);
  return {
    repoContext,
    fileIndex,
    projectState,
    inspection: {
      indexedFileCount: fileIndex.files.length,
      importantFileCount: importantFiles.length,
      estimatedImportantFilesSizeBytes,
      importantFiles
    }
  };
}
async function buildProjectStateInspection(repoRoot) {
  const project = await loadBridgerProject(repoRoot);
  const configPath = getBridgerConfigPath(repoRoot);
  const artifactsDir = getArtifactsDir(repoRoot);
  const memoryDir = getMemoryDir(repoRoot);
  const skillsDir = getSkillsDir(repoRoot);
  const templatesDir = getTemplatesDir(repoRoot);
  const exportsDir = getExportsDir(repoRoot);
  const artifactFiles = await buildFileInspections([
    ["file-index.json", getFileIndexPath(repoRoot)],
    ["repo-context.json", getRepoContextPath(repoRoot)],
    ["repo-graph.json", getRepoGraphPath(repoRoot)],
    ["graph-summary.json", getGraphSummaryPath(repoRoot)],
    ["codebase-map.json", getCodebaseMapPath(repoRoot)],
    ["reading-plans.json", getReadingPlansPath(repoRoot)]
  ]);
  const memoryFiles = await buildFileInspections([
    ["repo-analysis.md", getGeneratedKnowledgeDocPath(repoRoot, "repoAnalysis")],
    ["architecture.md", getGeneratedKnowledgeDocPath(repoRoot, "architecture")],
    ["business-logic.md", getGeneratedKnowledgeDocPath(repoRoot, "businessLogic")],
    ["conventions.md", getGeneratedKnowledgeDocPath(repoRoot, "conventions")],
    ["testing.md", getGeneratedKnowledgeDocPath(repoRoot, "testing")]
  ]);
  const supportFiles = await buildFileInspections([
    ["selected-skills.json", getSelectedSkillsPath(repoRoot)],
    ["ticket-template.md", getTicketTemplatePath(repoRoot)],
    ["AGENTS.generated.md", getAgentsGeneratedExportPath(repoRoot)],
    ["CLAUDE.generated.md", getClaudeGeneratedExportPath(repoRoot)],
    ["root AGENTS.md", getRootAgentsPath(repoRoot)]
  ]);
  return {
    status: project.status,
    reason: project.status === "initialized" ? void 0 : project.reason,
    message: project.status === "invalid" ? project.message : void 0,
    configPath,
    projectName: project.status === "initialized" ? project.config.project.name : void 0,
    projectMode: project.status === "initialized" ? project.config.project.mode : void 0,
    detectedStack: project.status === "initialized" ? project.config.detected.stack : void 0,
    packageManager: project.status === "initialized" ? project.config.detected.packageManager : void 0,
    artifactsDir,
    memoryDir,
    skillsDir,
    templatesDir,
    exportsDir,
    artifactFiles,
    memoryFiles,
    supportFiles,
    exists: {
      config: await pathExists3(configPath),
      artifactsDir: await pathExists3(artifactsDir),
      memoryDir: await pathExists3(memoryDir),
      skillsDir: await pathExists3(skillsDir),
      templatesDir: await pathExists3(templatesDir),
      exportsDir: await pathExists3(exportsDir)
    }
  };
}
function formatInspectSummary(input) {
  const lines = [
    "bridger Inspect",
    "",
    `Repo: ${input.repoRoot}`,
    `Framework: ${input.stack.framework || "unknown"}`,
    `Language: ${input.stack.language || "unknown"}`,
    `Package manager: ${input.stack.packageManager || "unknown"}`,
    `Styling: ${formatList(input.stack.styling)}`,
    `Validation: ${formatList(input.stack.validation)}`,
    `Database: ${formatList(input.stack.database)}`,
    `Testing: ${formatList(input.stack.testFramework)}`,
    "",
    "Commands:"
  ];
  const commandLines = [];
  for (const commandName of COMMAND_ORDER) {
    const value = input.commands[commandName];
    if (value !== void 0) {
      commandLines.push(`- ${commandName}: ${formatCommandValue(value)}`);
    }
  }
  if (commandLines.length === 0) {
    lines.push("- none");
  } else {
    lines.push(...commandLines);
  }
  lines.push("");
  lines.push(`Indexed files: ${input.indexedFileCount}`);
  return lines.join("\n");
}
function formatProjectStateSection(projectState) {
  const lines = [
    "Project state:",
    `- Status: ${projectState.status}`,
    `- Config: ${projectState.configPath} (${formatExists(projectState.exists.config)})`,
    `- Artifacts dir: ${projectState.artifactsDir} (${formatExists(projectState.exists.artifactsDir)})`,
    `- Memory dir: ${projectState.memoryDir} (${formatExists(projectState.exists.memoryDir)})`,
    `- Skills dir: ${projectState.skillsDir} (${formatExists(projectState.exists.skillsDir)})`,
    `- Templates dir: ${projectState.templatesDir} (${formatExists(projectState.exists.templatesDir)})`,
    `- Exports dir: ${projectState.exportsDir} (${formatExists(projectState.exists.exportsDir)})`,
    "",
    "Canonical artifact files:",
    ...formatCanonicalFileLines(projectState.artifactFiles),
    "",
    "Canonical memory files:",
    ...formatCanonicalFileLines(projectState.memoryFiles),
    "",
    "Canonical skills/templates/exports:",
    ...formatCanonicalFileLines(projectState.supportFiles)
  ];
  if (projectState.packageManager !== void 0) {
    lines.splice(2, 0, `- Config package manager: ${projectState.packageManager}`);
  }
  if (projectState.detectedStack !== void 0) {
    lines.splice(2, 0, `- Config detected stack: ${formatList(projectState.detectedStack)}`);
  }
  if (projectState.projectMode !== void 0) {
    lines.splice(2, 0, `- Project mode: ${projectState.projectMode}`);
  }
  if (projectState.projectName !== void 0) {
    lines.splice(2, 0, `- Project name: ${projectState.projectName}`);
  }
  if (projectState.reason !== void 0) {
    lines.push(`- Reason: ${projectState.reason}`);
  }
  if (projectState.message !== void 0) {
    lines.push(`- Message: ${projectState.message}`);
  }
  return lines.join("\n");
}
function formatExists(exists) {
  return exists ? "exists" : "missing";
}
function formatCanonicalFileLines(files) {
  return files.map((file) => `- ${file.label}: ${formatExists(file.exists)}`);
}
async function buildFileInspections(files) {
  const inspections = [];
  for (const [label, filePath] of files) {
    inspections.push({
      label,
      path: filePath,
      exists: await pathExists3(filePath)
    });
  }
  return inspections;
}
function formatGraphInspectOutput(input) {
  const { graph, summary, codebaseMap } = input;
  const fileIndex = input.fileIndex ?? EMPTY_FILE_INDEX;
  const readingPlans = input.readingPlans ?? EMPTY_READING_PLANS;
  return [
    "Repo graph",
    "",
    formatRepositoryInventorySection(fileIndex),
    "",
    formatDiagnosticsSection(fileIndex, codebaseMap, readingPlans),
    "",
    "Stats",
    `- Files: ${graph.stats.fileCount}`,
    `- Directories: ${graph.stats.directoryCount}`,
    `- Contains edges: ${graph.stats.containsEdgeCount}`,
    `- Import edges: ${graph.stats.importEdgeCount}`,
    `- Unresolved imports: ${graph.stats.unresolvedImportCount}`,
    `- Supported language files: ${graph.stats.supportedLanguageFileCount}`,
    `- Diagnostics: ${graph.diagnostics.length}`,
    "",
    "Entrypoint candidates",
    formatPathList(summary.entrypoints),
    "",
    "Top high fan-in files",
    formatRankedFiles(summary.highFanInFiles, "incoming"),
    "",
    "Top high fan-out files",
    formatRankedFiles(summary.highFanOutFiles, "outgoing"),
    "",
    "Architecture-first order preview",
    formatOrderedPreview(summary.architectureFirstOrder.slice(0, 10)),
    "",
    "Clusters",
    formatClusterPreview(codebaseMap),
    "",
    formatReadingPlansSection(readingPlans),
    "",
    formatReadingPlanPreviewSection(readingPlans)
  ].join("\n");
}
function formatRepositoryInventorySection(fileIndex) {
  const inventory = buildFileIndexInventory(fileIndex);
  return [
    "Repository Inventory",
    `- Included files: ${inventory.includedFileCount}`,
    `- Skipped files: ${inventory.skippedFileCount}`,
    `- Warnings: ${inventory.warningCount}`,
    `- Top skip reasons: ${formatCountEntries(inventory.topSkipReasons, 5)}`,
    `- Top roles: ${formatCountEntries(inventory.topRoles, 8)}`,
    `- Languages: ${formatCountEntries(inventory.topLanguages, 8)}`
  ].join("\n");
}
function formatDiagnosticsSection(fileIndex, codebaseMap, readingPlans) {
  return [
    "Diagnostics",
    `- FileIndex warnings: ${fileIndex.warnings?.length ?? 0}`,
    `- CodebaseMap warnings: ${codebaseMap.warnings.length}`,
    `- ReadingPlans warnings: ${readingPlans.warnings.length}`,
    "- Plan warnings:",
    ...formatPlanWarningCounts(readingPlans)
  ].join("\n");
}
function formatReadingPlansSection(readingPlans) {
  const lines = ["Reading Plans"];
  for (const kind of READING_PLAN_KINDS) {
    const plan = readingPlans.plans.find((item) => item.kind === kind);
    if (!plan) {
      lines.push(`- Missing plan: ${kind}`);
      continue;
    }
    const fileReferenceCount = plan.batches.reduce(
      (total, batch) => total + batch.files.length,
      0
    );
    const uniqueFileCount = new Set(
      plan.batches.flatMap((batch) => batch.files.map((file) => file.path))
    ).size;
    lines.push(
      `- ${plan.kind}: ${formatQuantity(plan.batches.length, "batch", "batches")}, ${formatQuantity(fileReferenceCount, "file reference")}, ${formatQuantity(uniqueFileCount, "unique file")}, ${formatQuantity(plan.warnings.length, "warning")}, truncated: ${plan.budget.truncated ? "yes" : "no"}`
    );
  }
  return lines.join("\n");
}
function formatReadingPlanPreviewSection(readingPlans) {
  const lines = ["Reading Plan Preview"];
  for (const kind of ["architecture", "testing"]) {
    const plan = readingPlans.plans.find((item) => item.kind === kind);
    if (!plan) {
      lines.push("");
      lines.push(`${kind}`);
      lines.push("- Missing plan");
      continue;
    }
    lines.push("");
    lines.push(plan.kind);
    lines.push(...formatReadingPlanPreview(plan));
  }
  return lines.join("\n");
}
function formatReadingPlanPreview(plan) {
  const lines = [];
  for (const batch of plan.batches.slice(0, 3)) {
    lines.push(`- ${batch.title}`);
    const filePaths = batch.files.slice(0, 3).map((file) => file.path);
    if (filePaths.length === 0) {
      lines.push("  - none");
      continue;
    }
    for (const filePath of filePaths) {
      lines.push(`  - ${filePath}`);
    }
  }
  return lines;
}
var READING_PLAN_KINDS = [
  "repo-analysis",
  "architecture",
  "business-logic",
  "conventions",
  "testing"
];
function buildFileIndexInventory(fileIndex) {
  const stats = fileIndex.stats;
  return {
    includedFileCount: stats?.includedFileCount ?? fileIndex.files.length,
    skippedFileCount: stats?.skippedFileCount ?? fileIndex.skippedFiles?.length ?? 0,
    warningCount: fileIndex.warnings?.length ?? 0,
    topSkipReasons: formatCountEntriesToList(
      stats?.bySkipReason ?? countSkippedFiles(fileIndex)
    ),
    topRoles: formatCountEntriesToList(
      stats?.byRole ?? countFileRoles(fileIndex)
    ),
    topLanguages: formatCountEntriesToList(
      stats?.byLanguage ?? countFileLanguages(fileIndex)
    )
  };
}
function countSkippedFiles(fileIndex) {
  const counts = {};
  for (const skippedFile of fileIndex.skippedFiles ?? []) {
    counts[skippedFile.reason] = (counts[skippedFile.reason] ?? 0) + 1;
  }
  return counts;
}
function countFileRoles(fileIndex) {
  const counts = {};
  for (const file of fileIndex.files) {
    for (const role of file.roles ?? []) {
      counts[role] = (counts[role] ?? 0) + 1;
    }
  }
  return counts;
}
function countFileLanguages(fileIndex) {
  const counts = {};
  for (const file of fileIndex.files) {
    const language = file.language ?? "unknown";
    counts[language] = (counts[language] ?? 0) + 1;
  }
  return counts;
}
function formatCountEntries(counts, maxEntries) {
  if (counts.length === 0) {
    return "none";
  }
  return counts.slice(0, maxEntries).map((entry) => `${entry.key}: ${entry.count}`).join(", ");
}
function formatCountEntriesToList(counts) {
  return Object.entries(counts).flatMap(
    ([key, count]) => typeof count === "number" ? [{ key, count }] : []
  ).sort(
    (left, right) => right.count - left.count || left.key.localeCompare(right.key)
  );
}
function formatPlanWarningCounts(readingPlans) {
  return READING_PLAN_KINDS.map((kind) => {
    const plan = readingPlans.plans.find((item) => item.kind === kind);
    return `  - ${kind}: ${plan?.warnings.length ?? 0}`;
  });
}
var EMPTY_FILE_INDEX = {
  generatedAt: "2026-05-01T00:00:00.000Z",
  files: []
};
var EMPTY_READING_PLANS = {
  schemaVersion: 1,
  generatedAt: "2026-05-01T00:00:00.000Z",
  sourceArtifacts: {},
  plans: [],
  stats: {
    planCount: 0,
    batchCount: 0,
    uniqueFileCount: 0,
    repeatedFileReferences: 0,
    estimatedTotalBytes: 0
  },
  warnings: []
};
function formatClusterPreview(codebaseMap) {
  const maxClusters = 10;
  const lines = codebaseMap.clusters.slice(0, maxClusters).map((cluster) => {
    const details = [`${cluster.files.length} files`, cluster.kind];
    const centralPath = cluster.centralFiles[0]?.path;
    if (centralPath) {
      details.push(`central: ${centralPath}`);
    } else if (cluster.entrypoints[0]) {
      details.push(`entrypoint: ${cluster.entrypoints[0]}`);
    }
    return `- ${cluster.id}: ${details.join(", ")}`;
  });
  if (lines.length === 0) {
    return "- None";
  }
  const remainingCount = codebaseMap.clusters.length - maxClusters;
  if (remainingCount > 0) {
    lines.push(
      `- ${remainingCount} more cluster${remainingCount === 1 ? "" : "s"}`
    );
  }
  return lines.join("\n");
}
function formatPathList(paths) {
  if (paths.length === 0) {
    return "- None";
  }
  return paths.map((path20) => `- ${path20}`).join("\n");
}
function formatRankedFiles(files, label) {
  if (files.length === 0) {
    return "- None";
  }
  return files.slice(0, 10).map(
    (file) => `- ${file.path} - ${file.count} ${label} import${file.count === 1 ? "" : "s"}`
  ).join("\n");
}
function formatOrderedPreview(paths) {
  if (paths.length === 0) {
    return "- None";
  }
  return paths.map((path20, index) => `${index + 1}. ${path20}`).join("\n");
}
function formatImportantFileInspectionLines(importantFile) {
  const lines = [`- ${importantFile.path}`, `  Reason: ${importantFile.reason}`];
  if (importantFile.sizeBytes !== void 0) {
    lines.push(`  Size: ${formatBytes(importantFile.sizeBytes)}`);
  }
  return lines;
}
function formatImportantFileList(result) {
  if (result.inspection.importantFiles.length === 0) {
    return "- none";
  }
  const lines = [];
  for (const importantFile of result.inspection.importantFiles) {
    lines.push(...formatImportantFileInspectionLines(importantFile));
    lines.push("");
  }
  lines.pop();
  return lines.join("\n");
}
function formatImportantFilesSection(result) {
  return [
    `Important files: ${result.inspection.importantFileCount}`,
    "",
    formatImportantFileList(result)
  ].join("\n");
}
function formatContextPreview(result) {
  const estimatedSelectedContextSize = result.inspection.estimatedImportantFilesSizeBytes !== void 0 ? formatBytes(result.inspection.estimatedImportantFilesSizeBytes) : "unknown";
  return [
    "Context preview",
    "",
    `Indexed files: ${result.inspection.indexedFileCount}`,
    `Important files: ${result.inspection.importantFileCount}`,
    `Estimated selected context size: ${estimatedSelectedContextSize}`,
    "",
    "Important files:",
    "",
    formatImportantFileList(result)
  ].join("\n");
}
function printSummary(result) {
  logger.info(
    [
      formatInspectSummary({
        repoRoot: result.repoContext.repoRoot,
        stack: result.repoContext.stack,
        commands: result.repoContext.commands,
        indexedFileCount: result.inspection.indexedFileCount
      }),
      "",
      formatProjectStateSection(result.projectState)
    ].join("\n")
  );
}
function printImportantFiles(result) {
  logger.info(formatImportantFilesSection(result));
}
function printContextPreview(result) {
  logger.info(formatContextPreview(result));
}
async function buildGraphInspectArtifacts(repoRoot) {
  const { repoContext, fileIndex } = await buildRepoContextArtifacts(repoRoot);
  const graph = await buildRepoGraph({
    repoRoot,
    fileIndex
  });
  const summary = buildGraphSummary(graph);
  const codebaseMap = buildCodebaseMap({
    repoRoot,
    fileIndex,
    repoContext,
    repoGraph: graph,
    graphSummary: summary
  });
  const readingPlans = buildReadingPlans({
    repoRoot,
    fileIndex,
    repoContext,
    repoGraph: graph,
    graphSummary: summary,
    codebaseMap
  });
  return {
    fileIndex,
    graph,
    summary,
    codebaseMap,
    readingPlans
  };
}
function printGraphInspectOutput(input) {
  logger.info(formatGraphInspectOutput(input));
}
async function runInspectCommand(options) {
  try {
    const repoRoot = resolveRepoRoot(options?.repo);
    if (options?.graph) {
      const graphResult = await buildGraphInspectArtifacts(repoRoot);
      printGraphInspectOutput(graphResult);
      return;
    }
    const result = await buildInspectResult(repoRoot);
    if (options?.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    printSummary(result);
    if (options?.context) {
      printContextPreview(result);
      return;
    }
    if (options?.importantFiles) {
      printImportantFiles(result);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`bridger inspect failed: ${message}`);
    process.exitCode = 1;
  }
}
async function pathExists3(filePath) {
  try {
    await fs9.access(filePath);
    return true;
  } catch {
    return false;
  }
}
var inspectCommand = new Command("inspect").description("Inspect the current repository without using the LLM").option("--repo <path>", "Path to the repository to inspect").option("--context", "Show deterministic context preview").option("--important-files", "Show selected important files and selection reasons").option("--graph", "Print repo graph inspection output").option("--json", "Print inspect result as JSON").action(async (options) => {
  await runInspectCommand(options);
});

// src/cli/commands/init.ts
import path19 from "path";
import { Command as Command2 } from "commander";

// src/core/output/write-json.ts
import fs10 from "fs/promises";
import path16 from "path";
async function writeJson(filePath, data) {
  await fs10.mkdir(path16.dirname(filePath), { recursive: true });
  const content = `${JSON.stringify(data, null, 2)}
`;
  await fs10.writeFile(filePath, content, "utf8");
}

// src/core/codebase-map/write-codebase-map.ts
async function writeCodebaseMapArtifact(input) {
  const outputPath = getCodebaseMapPath(input.repoRoot);
  await writeJson(outputPath, CodebaseMapSchema.parse(input.codebaseMap));
  return outputPath;
}

// src/core/project/ensure-bridger-layout.ts
import fs11 from "fs/promises";
var SELECTED_SKILLS_JSON = {
  schemaVersion: 1,
  selected: []
};
var TICKET_TEMPLATE = `# Ticket

## Goal

## Context

## Implementation notes

## Acceptance criteria

## Validation
`;
async function ensureBridgerLayout(repoRoot) {
  await fs11.mkdir(getBridgerDir(repoRoot), { recursive: true });
  await fs11.mkdir(getMemoryDir(repoRoot), { recursive: true });
  await fs11.mkdir(getArtifactsDir(repoRoot), { recursive: true });
  await fs11.mkdir(getSkillsDir(repoRoot), { recursive: true });
  await fs11.mkdir(getTemplatesDir(repoRoot), { recursive: true });
  await fs11.mkdir(getExportsDir(repoRoot), { recursive: true });
  await writeFileIfMissing(getBridgerIndexPath(repoRoot), "# Bridger Index\n");
  await writeFileIfMissing(getBridgerLogPath(repoRoot), "# Bridger Log\n");
  await writeFileIfMissing(
    getSelectedSkillsPath(repoRoot),
    `${JSON.stringify(SELECTED_SKILLS_JSON, null, 2)}
`
  );
  await writeFileIfMissing(getTicketTemplatePath(repoRoot), TICKET_TEMPLATE);
}
async function writeFileIfMissing(filePath, content) {
  try {
    await fs11.writeFile(filePath, content, { encoding: "utf8", flag: "wx" });
  } catch (error) {
    if (isExistingFileError(error)) {
      return;
    }
    throw error;
  }
}
function isExistingFileError(error) {
  return typeof error === "object" && error !== null && "code" in error && error.code === "EEXIST";
}

// src/core/output/ensure-output-dirs.ts
async function ensureOutputDirs(repoRoot) {
  await ensureBridgerLayout(repoRoot);
}

// src/core/project/create-bridger-config.ts
import path17 from "path";
function createBridgerConfig(input) {
  const now = input.now ?? /* @__PURE__ */ new Date();
  const timestamp = now.toISOString();
  const projectName = input.projectName ?? path17.basename(input.repoRoot);
  return BridgerConfigSchema.parse({
    schemaVersion: 1,
    project: {
      name: projectName,
      mode: input.mode
    },
    detected: {
      packageManager: input.packageManager,
      stack: input.detectedStack ?? []
    },
    paths: {
      memoryDir: ".bridger/memory",
      artifactsDir: ".bridger/artifacts",
      skillsDir: ".bridger/skills",
      templatesDir: ".bridger/templates",
      exportsDir: ".bridger/exports"
    },
    memory: {
      schemaVersion: 1
    },
    artifacts: {
      schemaVersion: 1
    },
    skills: {
      selected: []
    },
    exports: {
      agentsMd: {
        enabled: true,
        generatedPath: ".bridger/exports/AGENTS.generated.md",
        rootPath: "AGENTS.md",
        writeRootFile: input.writeRootAgentsFile ?? false
      },
      claudeMd: {
        enabled: false,
        generatedPath: ".bridger/exports/CLAUDE.generated.md",
        rootPath: "CLAUDE.md",
        writeRootFile: false
      }
    },
    llm: {
      provider: "none",
      modelProfile: "balanced"
    },
    timestamps: {
      initializedAt: timestamp,
      lastInitAt: timestamp
    }
  });
}

// src/core/project/write-bridger-config.ts
import fs12 from "fs/promises";
import path18 from "path";
async function writeBridgerConfig(repoRoot, config) {
  const parsedConfig = BridgerConfigSchema.parse(config);
  const configPath = getBridgerConfigPath(repoRoot);
  await fs12.mkdir(path18.dirname(configPath), { recursive: true });
  await fs12.writeFile(
    configPath,
    `${JSON.stringify(parsedConfig, null, 2)}
`,
    "utf8"
  );
}

// src/core/reading-plans/write-reading-plans.ts
async function writeReadingPlansArtifact(input) {
  const outputPath = getReadingPlansPath(input.repoRoot);
  await writeJson(outputPath, ReadingPlansSchema.parse(input.readingPlans));
  return outputPath;
}

// src/core/repo-graph/write-repo-graph.ts
async function writeRepoGraph(input) {
  const outputPath = getRepoGraphPath(input.repoRoot);
  await writeJson(outputPath, RepoGraphSchema.parse(input.graph));
  return outputPath;
}
async function writeGraphSummary(input) {
  const outputPath = getGraphSummaryPath(input.repoRoot);
  await writeJson(outputPath, GraphSummarySchema.parse(input.summary));
  return outputPath;
}
async function writeRepoGraphArtifacts(input) {
  const repoGraphPath = await writeRepoGraph({
    repoRoot: input.repoRoot,
    graph: input.graph
  });
  const graphSummaryPath = await writeGraphSummary({
    repoRoot: input.repoRoot,
    summary: input.summary
  });
  return {
    repoGraphPath,
    graphSummaryPath
  };
}

// src/cli/commands/init.ts
function logInitStep(message) {
  logger.debug(`bridger init: ${message}`);
}
function formatInitSummary(input) {
  const lines = [
    "SUCCESS: bridger init complete",
    "",
    `Repo: ${input.repoRoot}`,
    `Indexed files: ${input.indexedFileCount}`,
    "",
    "Generated:"
  ];
  for (const filePath of input.generatedFiles) {
    lines.push(`- ${filePath}`);
  }
  return lines.join("\n");
}
function getGeneratedFilePaths(repoRoot) {
  return [
    getBridgerConfigPath(repoRoot),
    getRepoContextPath(repoRoot),
    getFileIndexPath(repoRoot),
    getRepoGraphPath(repoRoot),
    getGraphSummaryPath(repoRoot),
    getCodebaseMapPath(repoRoot),
    getReadingPlansPath(repoRoot),
    getTicketTemplatePath(repoRoot)
  ].map((filePath) => path19.relative(repoRoot, filePath));
}
function getDetectedStackNames(stack) {
  return [
    stack.framework,
    stack.language,
    ...stack.styling,
    ...stack.validation,
    ...stack.database,
    ...stack.testFramework
  ].filter((value) => value.length > 0 && value !== "unknown");
}
async function runInitCommand(options = {}) {
  const repoRoot = resolveRepoRoot(options.repo);
  try {
    logInitStep(`starting for ${repoRoot}`);
    logInitStep("ensuring output directories");
    await ensureOutputDirs(repoRoot);
    logInitStep("output directories ready");
    logInitStep("building repo context");
    const { repoContext, fileIndex, importantFiles } = await buildRepoContextArtifacts(repoRoot);
    logInitStep(
      `repo context ready (${fileIndex.files.length} indexed files, ${importantFiles.length} important files)`
    );
    logInitStep("writing project config");
    await writeBridgerConfig(
      repoRoot,
      createBridgerConfig({
        repoRoot,
        mode: fileIndex.files.length > 0 ? "existing" : "unknown",
        detectedStack: getDetectedStackNames(repoContext.stack),
        packageManager: repoContext.stack.packageManager || void 0
      })
    );
    logInitStep("project config written");
    logInitStep("building deterministic artifacts");
    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex
    });
    const graphSummary = buildGraphSummary(graph);
    const codebaseMap = buildCodebaseMap({
      repoRoot,
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary
    });
    const readingPlans = buildReadingPlans({
      repoRoot,
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary,
      codebaseMap
    });
    logInitStep("deterministic artifacts ready");
    logInitStep("writing deterministic artifacts");
    await writeJson(getRepoContextPath(repoRoot), repoContext);
    await writeJson(getFileIndexPath(repoRoot), fileIndex);
    await writeRepoGraphArtifacts({
      repoRoot,
      graph,
      summary: graphSummary
    });
    await writeCodebaseMapArtifact({ repoRoot, codebaseMap });
    await writeReadingPlansArtifact({ repoRoot, readingPlans });
    logInitStep("deterministic artifacts written");
    logger.info(
      formatInitSummary({
        repoRoot,
        indexedFileCount: fileIndex.files.length,
        generatedFiles: getGeneratedFilePaths(repoRoot)
      })
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`bridger init failed: ${message}`);
    process.exitCode = 1;
  }
}
var initCommand = new Command2("init").description("Generate deterministic Bridger repository artifacts").option("--repo <path>", "Path to the repository to initialize").action(async (options) => {
  await runInitCommand({
    repo: options.repo
  });
});

// src/cli/cli.ts
function buildCliProgram() {
  const program = new Command3();
  program.name("bridger").description("Prepare a repository for AI coding agents").version("0.1.0");
  program.addCommand(initCommand);
  program.addCommand(inspectCommand);
  return program;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  buildCliProgram().parse();
}
export {
  buildCliProgram
};
