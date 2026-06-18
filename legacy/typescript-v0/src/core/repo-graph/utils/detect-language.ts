import type { RepoGraphLanguage } from "../models/repo-graph";

const LANGUAGE_BY_EXTENSION: Record<string, RepoGraphLanguage> = {
  ".ts": "typescript",
  ".tsx": "typescript",
  ".js": "javascript",
  ".jsx": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".py": "python",
  ".md": "markdown",
  ".json": "json",
};

export function detectLanguageFromExtension(
  extension?: string | null,
): RepoGraphLanguage {
  if (!extension) {
    return "unknown";
  }

  const normalizedExtension = extension.startsWith(".")
    ? extension.toLowerCase()
    : `.${extension.toLowerCase()}`;

  return LANGUAGE_BY_EXTENSION[normalizedExtension] ?? "unknown";
}
