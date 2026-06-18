export function normalizeRepoPath(input: string): string {
  if (input === "") {
    return ".";
  }

  const normalized = input
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .replace(/^\.\//, "");

  if (normalized === "/") {
    return "/";
  }

  const withoutTrailingSlash = normalized.replace(/\/$/, "");

  return withoutTrailingSlash === "" ? "." : withoutTrailingSlash;
}
