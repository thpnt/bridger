import fs from "fs-extra";
import ignore from "ignore";
import path from "node:path";

function toPosixPath(value: string): string {
  return value.replaceAll(path.sep, "/");
}

export async function createGitignoreFilter(
  repoRoot: string,
): Promise<(relativePath: string) => boolean> {
  const gitignorePath = path.join(repoRoot, ".gitignore");
  const ignoreRules = ignore();

  if (await fs.pathExists(gitignorePath)) {
    const content = await fs.readFile(gitignorePath, "utf8");
    ignoreRules.add(content);
  }

  return (relativePath: string) => {
    const normalizedPath = toPosixPath(relativePath);

    return !ignoreRules.ignores(normalizedPath);
  };
}
