import path from "node:path";

export type ImportantFileCategory =
  | "agent"
  | "docs"
  | "entrypoint"
  | "domain"
  | "component"
  | "test"
  | "config";

export type ImportantFileCandidate = {
  path: string;
  reason: string;
  priority: number;
  category: ImportantFileCategory;
};

export const IMPORTANT_FILE_BUDGETS = {
  maxSingleFileBytes: 20 * 1024,
  maxTotalContentBytes: 120 * 1024,
  maxConfigTotalBytes: 20 * 1024,
} as const;

export const IMPORTANT_FILE_CATEGORY_LIMITS = {
  agent: 3,
  docs: 6,
  entrypoint: 12,
  domain: 20,
  component: 10,
  test: 6,
  config: 5,
} as const;

export const ALLOWED_TEXT_EXTENSIONS = new Set([
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
  ".toml",
]);

const LOCKFILE_NAMES = new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb",
]);

function normalizeRelativePath(relativePath: string): string {
  return relativePath.replaceAll("\\", "/");
}

function hasPathPrefix(relativePath: string, prefix: string): boolean {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}

function hasFileName(relativePath: string, fileName: string): boolean {
  return path.posix.basename(relativePath) === fileName;
}

function hasSuffixMatch(relativePath: string, suffix: string): boolean {
  return relativePath.includes(`/${suffix}`) || path.posix.basename(relativePath).includes(suffix);
}

export function isAllowedImportantFileExtension(relativePath: string): boolean {
  const normalizedPath = normalizeRelativePath(relativePath);
  const fileName = path.posix.basename(normalizedPath);

  if (LOCKFILE_NAMES.has(fileName)) {
    return false;
  }

  const extension = path.extname(normalizedPath);

  return ALLOWED_TEXT_EXTENSIONS.has(extension);
}

export function classifyImportantFile(
  relativePath: string,
): ImportantFileCandidate | null {
  const normalizedPath = normalizeRelativePath(relativePath);

  if (LOCKFILE_NAMES.has(path.posix.basename(normalizedPath))) {
    return null;
  }

  if (hasFileName(normalizedPath, "AGENTS.md")) {
    return {
      path: normalizedPath,
      reason: "Existing agent instruction file",
      priority: 10,
      category: "agent",
    };
  }

  if (hasFileName(normalizedPath, "CLAUDE.md")) {
    return {
      path: normalizedPath,
      reason: "Existing Claude instruction file",
      priority: 10,
      category: "agent",
    };
  }

  if (hasFileName(normalizedPath, "components.json")) {
    return {
      path: normalizedPath,
      reason: "Design system or component alias configuration",
      priority: 70,
      category: "config",
    };
  }

  if (hasFileName(normalizedPath, "tsconfig.json")) {
    return {
      path: normalizedPath,
      reason: "TypeScript path alias configuration",
      priority: 70,
      category: "config",
    };
  }

  if (normalizedPath.startsWith("next.config.")) {
    return {
      path: normalizedPath,
      reason: "Framework configuration with possible repo-specific behavior",
      priority: 70,
      category: "config",
    };
  }

  if (normalizedPath.startsWith("tailwind.config.")) {
    return {
      path: normalizedPath,
      reason: "Tailwind theme/configuration",
      priority: 70,
      category: "config",
    };
  }

  if (hasFileName(normalizedPath, "package.json")) {
    return {
      path: normalizedPath,
      reason: "Package scripts and dependency manifest",
      priority: 70,
      category: "config",
    };
  }

  if (hasFileName(normalizedPath, "README.md")) {
    return {
      path: normalizedPath,
      reason: "Project README",
      priority: 60,
      category: "docs",
    };
  }

  if (hasPathPrefix(normalizedPath, "docs") && path.extname(normalizedPath) === ".md") {
    return {
      path: normalizedPath,
      reason: "Project documentation",
      priority: 60,
      category: "docs",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "app") ||
    hasPathPrefix(normalizedPath, "src/app")
  ) {
    const fileName = path.posix.basename(normalizedPath);

    if (fileName.startsWith("layout.")) {
      return {
        path: normalizedPath,
        reason: "Application layout entry point",
        priority: 20,
        category: "entrypoint",
      };
    }

    if (fileName.startsWith("page.")) {
      return {
        path: normalizedPath,
        reason: "Application page/route entry point",
        priority: 20,
        category: "entrypoint",
      };
    }

    if (fileName.startsWith("route.")) {
      return {
        path: normalizedPath,
        reason: "API route entry point",
        priority: 20,
        category: "entrypoint",
      };
    }
  }

  if (
    hasPathPrefix(normalizedPath, "pages") ||
    hasPathPrefix(normalizedPath, "src/pages")
  ) {
    const fileName = path.posix.basename(normalizedPath);

    if (
      normalizedPath.startsWith("pages/api/") ||
      normalizedPath.startsWith("src/pages/api/") ||
      normalizedPath.startsWith("src/pages/") ||
      fileName.startsWith("_app.") ||
      fileName.startsWith("index.")
    ) {
      return {
        path: normalizedPath,
        reason: "Pages router entry point",
        priority: 20,
        category: "entrypoint",
      };
    }
  }

  if (
    hasPathPrefix(normalizedPath, "src/core") ||
    hasPathPrefix(normalizedPath, "src/domain") ||
    hasPathPrefix(normalizedPath, "src/domains")
  ) {
    if (
      hasPathPrefix(normalizedPath, "src/models") ||
      hasPathPrefix(normalizedPath, "src/entities") ||
      hasPathPrefix(normalizedPath, "src/schemas") ||
      hasPathPrefix(normalizedPath, "src/types") ||
      hasSuffixMatch(normalizedPath, "schema.") ||
      hasSuffixMatch(normalizedPath, "types.")
    ) {
      return {
        path: normalizedPath,
        reason: "Model/schema/type definition file",
        priority: 30,
        category: "domain",
      };
    }

    return {
      path: normalizedPath,
      reason:
        hasPathPrefix(normalizedPath, "src/domain") ||
        hasPathPrefix(normalizedPath, "src/domains")
          ? "Domain/business logic file"
          : hasPathPrefix(normalizedPath, "src/core")
            ? "Core application logic file"
            : "Infrastructure/helper file",
      priority: 30,
      category: "domain",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "src/models") ||
    hasPathPrefix(normalizedPath, "src/entities") ||
    hasPathPrefix(normalizedPath, "src/schemas") ||
    hasPathPrefix(normalizedPath, "src/types") ||
    hasSuffixMatch(normalizedPath, "schema.") ||
    hasSuffixMatch(normalizedPath, "types.")
  ) {
    return {
      path: normalizedPath,
      reason: "Model/schema/type definition file",
      priority: 30,
      category: "domain",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "db") ||
    hasPathPrefix(normalizedPath, "src/db") ||
    hasPathPrefix(normalizedPath, "prisma") ||
    hasPathPrefix(normalizedPath, "drizzle") ||
    hasPathPrefix(normalizedPath, "supabase")
  ) {
    return {
      path: normalizedPath,
      reason: "Data access or persistence file",
      priority: 30,
      category: "domain",
    };
  }

  if (hasPathPrefix(normalizedPath, "src/lib") || hasPathPrefix(normalizedPath, "lib")) {
    return {
      path: normalizedPath,
      reason: "Infrastructure/helper file",
      priority: 30,
      category: "domain",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "components/ui") ||
    hasPathPrefix(normalizedPath, "src/components/ui")
  ) {
    return {
      path: normalizedPath,
      reason: "Representative UI component file",
      priority: 40,
      category: "component",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "components/layout") ||
    hasPathPrefix(normalizedPath, "src/components/layout") ||
    hasPathPrefix(normalizedPath, "components/navigation") ||
    hasPathPrefix(normalizedPath, "src/components/navigation")
  ) {
    return {
      path: normalizedPath,
      reason: "Representative layout/navigation component file",
      priority: 40,
      category: "component",
    };
  }

  if (hasPathPrefix(normalizedPath, "components") || hasPathPrefix(normalizedPath, "src/components")) {
    return {
      path: normalizedPath,
      reason: "Representative component file",
      priority: 40,
      category: "component",
    };
  }

  if (
    hasPathPrefix(normalizedPath, "tests") ||
    hasPathPrefix(normalizedPath, "__tests__") ||
    hasPathPrefix(normalizedPath, "src/__tests__") ||
    normalizedPath.includes(".test.") ||
    normalizedPath.includes(".spec.")
  ) {
    return {
      path: normalizedPath,
      reason: "Representative test file",
      priority: 50,
      category: "test",
    };
  }

  return null;
}
