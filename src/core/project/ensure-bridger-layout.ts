import fs from "node:fs/promises";

import {
  getArtifactsDir,
  getBridgerDir,
  getBridgerIndexPath,
  getBridgerLogPath,
  getExportsDir,
  getMemoryDir,
  getSelectedSkillsPath,
  getSkillsDir,
  getTicketTemplatePath,
  getTemplatesDir,
} from "./bridger-paths";

const SELECTED_SKILLS_JSON = {
  schemaVersion: 1,
  selected: [],
};

const TICKET_TEMPLATE = `# Ticket

## Goal

## Context

## Implementation notes

## Acceptance criteria

## Validation
`;

export async function ensureBridgerLayout(repoRoot: string): Promise<void> {
  await fs.mkdir(getBridgerDir(repoRoot), { recursive: true });
  await fs.mkdir(getMemoryDir(repoRoot), { recursive: true });
  await fs.mkdir(getArtifactsDir(repoRoot), { recursive: true });
  await fs.mkdir(getSkillsDir(repoRoot), { recursive: true });
  await fs.mkdir(getTemplatesDir(repoRoot), { recursive: true });
  await fs.mkdir(getExportsDir(repoRoot), { recursive: true });

  await writeFileIfMissing(getBridgerIndexPath(repoRoot), "# Bridger Index\n");
  await writeFileIfMissing(getBridgerLogPath(repoRoot), "# Bridger Log\n");
  await writeFileIfMissing(
    getSelectedSkillsPath(repoRoot),
    `${JSON.stringify(SELECTED_SKILLS_JSON, null, 2)}\n`,
  );
  await writeFileIfMissing(getTicketTemplatePath(repoRoot), TICKET_TEMPLATE);
}

async function writeFileIfMissing(
  filePath: string,
  content: string,
): Promise<void> {
  try {
    await fs.writeFile(filePath, content, { encoding: "utf8", flag: "wx" });
  } catch (error) {
    if (isExistingFileError(error)) {
      return;
    }

    throw error;
  }
}

function isExistingFileError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "EEXIST"
  );
}
