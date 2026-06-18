import type { RepoGraphNodeTag } from "../models/repo-graph";
import { normalizeRepoPath } from "./normalize-path";

const TAG_ORDER: RepoGraphNodeTag[] = [
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
  "api-route",
];

const SOURCE_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".py",
]);

export function getPathTags(path: string): RepoGraphNodeTag[] {
  const normalizedPath = normalizeRepoPath(path);
  const lowerPath = normalizedPath.toLowerCase();
  const segments = lowerPath.split("/");
  const fileName = segments.at(-1) ?? lowerPath;
  const extension = getLowerExtension(fileName);
  const tags = new Set<RepoGraphNodeTag>();

  if (!normalizedPath.includes("/")) {
    tags.add("root");
  }

  if (isConfigPath(lowerPath, fileName)) {
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

  if (isEntrypointCandidatePath(lowerPath)) {
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

function getLowerExtension(fileName: string): string | null {
  const dotIndex = fileName.lastIndexOf(".");

  if (dotIndex <= 0) {
    return null;
  }

  return fileName.slice(dotIndex);
}

function isConfigPath(lowerPath: string, fileName: string): boolean {
  return (
    lowerPath.startsWith(".github/") ||
    fileName === "package.json" ||
    fileName === "tsconfig.json" ||
    fileName === "jsconfig.json" ||
    fileName === "components.json" ||
    fileName === "pyproject.toml" ||
    fileName === "ruff.toml" ||
    fileName === "mypy.ini" ||
    fileName === "pytest.ini" ||
    fileName === "dockerfile" ||
    fileName === "docker-compose.yml" ||
    fileName === ".env.example" ||
    fileName.startsWith("next.config.") ||
    fileName.startsWith("vite.config.") ||
    fileName.startsWith("vitest.config.") ||
    fileName.startsWith("jest.config.") ||
    fileName.startsWith("playwright.config.") ||
    fileName.startsWith("tailwind.config.") ||
    fileName.startsWith("postcss.config.") ||
    fileName.startsWith("eslint.config.") ||
    fileName.startsWith("prettier.config.")
  );
}

function isDocsPath(lowerPath: string, fileName: string): boolean {
  return (
    lowerPath.startsWith("docs/") ||
    fileName === "readme.md" ||
    fileName === "agents.md" ||
    fileName === "claude.md" ||
    fileName.endsWith(".md")
  );
}

function isSourcePath(lowerPath: string, extension: string | null): boolean {
  return (
    SOURCE_EXTENSIONS.has(extension ?? "") ||
    lowerPath.startsWith("src/") ||
    lowerPath.startsWith("app/") ||
    lowerPath.startsWith("pages/") ||
    lowerPath.startsWith("components/") ||
    lowerPath.startsWith("lib/") ||
    lowerPath.startsWith("server/") ||
    lowerPath.startsWith("core/") ||
    lowerPath.startsWith("cli/") ||
    lowerPath.startsWith("api/")
  );
}

function isTestPath(lowerPath: string, fileName: string): boolean {
  return (
    lowerPath.startsWith("tests/") ||
    lowerPath.startsWith("test/") ||
    lowerPath.includes("/__tests__/") ||
    fileName.includes(".test.") ||
    fileName.includes(".spec.") ||
    fileName.startsWith("test_") ||
    fileName.endsWith("_test.py")
  );
}

function isEntrypointCandidatePath(lowerPath: string): boolean {
  return (
    lowerPath === "index.ts" ||
    lowerPath === "main.ts" ||
    lowerPath === "main.py" ||
    lowerPath === "app.py" ||
    lowerPath === "src/index.ts" ||
    lowerPath === "src/main.ts" ||
    lowerPath === "src/main.py" ||
    lowerPath === "src/cli/index.ts" ||
    lowerPath.startsWith("bin/") ||
    lowerPath === "app/page.tsx" ||
    lowerPath === "src/app/page.tsx" ||
    /^app\/.+\/page\.tsx$/.test(lowerPath) ||
    /^src\/app\/.+\/page\.tsx$/.test(lowerPath) ||
    /^app\/.+\/route\.ts$/.test(lowerPath) ||
    /^src\/app\/.+\/route\.ts$/.test(lowerPath) ||
    /^pages\/.+\.tsx$/.test(lowerPath) ||
    /^src\/pages\/.+\.tsx$/.test(lowerPath)
  );
}

function isComponentPath(
  lowerPath: string,
  extension: string | null,
): boolean {
  return (
    lowerPath.startsWith("components/") ||
    lowerPath.startsWith("src/components/") ||
    lowerPath.includes("/components/") ||
    extension === ".tsx" ||
    extension === ".jsx"
  );
}

function isServicePath(lowerPath: string, fileName: string): boolean {
  return (
    lowerPath.startsWith("services/") ||
    lowerPath.startsWith("service/") ||
    lowerPath.includes("/services/") ||
    lowerPath.includes("/service/") ||
    fileName.endsWith("service.ts") ||
    fileName.endsWith("service.js") ||
    fileName.endsWith("service.py")
  );
}

function isUtilityPath(lowerPath: string, fileName: string): boolean {
  return (
    lowerPath.startsWith("utils/") ||
    lowerPath.startsWith("util/") ||
    lowerPath.startsWith("helpers/") ||
    lowerPath.startsWith("lib/") ||
    lowerPath.includes("/utils/") ||
    lowerPath.includes("/util/") ||
    lowerPath.includes("/helpers/") ||
    lowerPath.includes("/lib/") ||
    fileName.endsWith("utils.ts") ||
    fileName.endsWith("utils.js") ||
    fileName.endsWith("util.ts") ||
    fileName.endsWith("util.js") ||
    fileName.endsWith("helpers.ts") ||
    fileName.endsWith("helpers.js")
  );
}

function isRoutePath(lowerPath: string): boolean {
  return (
    lowerPath.startsWith("pages/") ||
    lowerPath.startsWith("src/pages/") ||
    lowerPath.startsWith("routes/") ||
    lowerPath.startsWith("src/routes/") ||
    lowerPath === "app/page.tsx" ||
    lowerPath === "src/app/page.tsx" ||
    /^app\/.+\/page\.tsx$/.test(lowerPath) ||
    /^src\/app\/.+\/page\.tsx$/.test(lowerPath) ||
    /^app\/.+\/layout\.tsx$/.test(lowerPath) ||
    /^src\/app\/.+\/layout\.tsx$/.test(lowerPath) ||
    /^app\/.+\/route\.ts$/.test(lowerPath) ||
    /^src\/app\/.+\/route\.ts$/.test(lowerPath)
  );
}

function isApiRoutePath(lowerPath: string): boolean {
  return (
    lowerPath.startsWith("api/") ||
    lowerPath.startsWith("src/api/") ||
    lowerPath.startsWith("pages/api/") ||
    lowerPath.startsWith("src/pages/api/") ||
    /^app\/.+\/route\.ts$/.test(lowerPath) ||
    /^src\/app\/.+\/route\.ts$/.test(lowerPath)
  );
}
