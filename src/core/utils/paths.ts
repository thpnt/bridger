import path from "node:path";

export const BRIDGER_DIR_NAME = ".bridger";
export const GENERATED_DIR_NAME = "generated";
export const TICKETS_DIR_NAME = "tickets";

export function resolveRepoRoot(input?: string): string {
  if (input !== undefined) {
    return path.resolve(input);
  }

  return path.resolve(process.cwd());
}

export function getAgentReadyDir(repoRoot: string): string {
  return path.join(repoRoot, BRIDGER_DIR_NAME);
}

export function getGeneratedDir(repoRoot: string): string {
  return path.join(getAgentReadyDir(repoRoot), GENERATED_DIR_NAME);
}

export function getTicketsDir(repoRoot: string): string {
  return path.join(getAgentReadyDir(repoRoot), TICKETS_DIR_NAME);
}
