import path from "node:path";

export {
  getAgentsGeneratedExportPath as getAgentsGeneratedPath,
  getArtifactsDir,
  getBridgerConfigPath,
  getBridgerDir,
  getBridgerIndexPath,
  getBridgerLogPath,
  getCodebaseMapPath,
  getExportsDir,
  getFileIndexPath,
  getGeneratedKnowledgeDocPath,
  getGraphSummaryPath,
  getMemoryDir,
  getMemoryFilePath,
  getReadingPlansPath,
  getRepoContextPath,
  getRepoGraphPath,
  getRootAgentsPath as getAgentsMdPath,
  getSelectedSkillsPath,
  getSkillsDir,
  getTemplatesDir,
  getTicketTemplatePath,
} from "../project/bridger-paths";

export const BRIDGER_DIR_NAME = ".bridger";

export function resolveRepoRoot(input?: string): string {
  return path.resolve(input ?? process.cwd());
}

export function getAgentReadyDir(repoRoot: string): string {
  return path.join(repoRoot, BRIDGER_DIR_NAME);
}
