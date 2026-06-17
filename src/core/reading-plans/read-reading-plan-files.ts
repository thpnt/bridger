import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  ReadingBatch,
  ReadingPlan,
  ReadingPlanFile,
} from "./models/reading-plans";

export interface ReadReadingPlanFilesOptions {
  repoRoot: string;
  plan: ReadingPlan;
  maxBytesPerFile?: number;
}

export interface ReadingPlanReadDiagnostic {
  code:
    | "file-not-found"
    | "file-outside-repo"
    | "file-read-failed"
    | "file-truncated"
    | "duplicate-file-read";
  message: string;
  path?: string;
  batchId?: string;
  severity: "info" | "warning";
}

export interface ReadingPlanFileContent {
  path: string;
  roleInBatch: ReadingPlanFile["roleInBatch"];
  reason: string;
  evidence: ReadingPlanFile["evidence"];
  confidence: ReadingPlanFile["confidence"];
  estimatedBytes: number;
  content: string;
  bytesRead: number;
  truncated: boolean;
}

export interface ReadingBatchContent {
  id: string;
  title: string;
  purpose: string;
  order: number;
  selectionRule: string;
  budget: ReadingBatch["budget"];
  files: ReadingPlanFileContent[];
}

export interface ReadReadingPlanFilesResult {
  planKind: ReadingPlan["kind"];
  targetMemoryFile: string;
  title: string;
  purpose: string;
  inputStrategy: ReadingPlan["inputStrategy"];
  budget: ReadingPlan["budget"];
  warnings: ReadingPlan["warnings"];
  batches: ReadingBatchContent[];
  diagnostics: ReadingPlanReadDiagnostic[];
}

interface CachedFileRead {
  content: string;
  bytesRead: number;
  truncated: boolean;
}

export async function readReadingPlanFiles(
  options: ReadReadingPlanFilesOptions,
): Promise<ReadReadingPlanFilesResult> {
  const repoRoot = path.resolve(options.repoRoot);
  const maxBytesPerFile = normalizeMaxBytes(options.maxBytesPerFile);
  const diagnostics: ReadingPlanReadDiagnostic[] = [];
  const readCache = new Map<string, CachedFileRead>();
  const batches: ReadingBatchContent[] = [];

  for (const batch of options.plan.batches) {
    const files: ReadingPlanFileContent[] = [];

    for (const file of batch.files) {
      const fileContent = await readPlanFile({
        repoRoot,
        batchId: batch.id,
        file,
        maxBytesPerFile,
        diagnostics,
        readCache,
      });

      files.push(fileContent);
    }

    batches.push({
      id: batch.id,
      title: batch.title,
      purpose: batch.purpose,
      order: batch.order,
      selectionRule: batch.selectionRule,
      budget: batch.budget,
      files,
    });
  }

  return {
    planKind: options.plan.kind,
    targetMemoryFile: options.plan.targetMemoryFile,
    title: options.plan.title,
    purpose: options.plan.purpose,
    inputStrategy: options.plan.inputStrategy,
    budget: options.plan.budget,
    warnings: options.plan.warnings,
    batches,
    diagnostics,
  };
}

async function readPlanFile(input: {
  repoRoot: string;
  batchId: string;
  file: ReadingPlanFile;
  maxBytesPerFile?: number;
  diagnostics: ReadingPlanReadDiagnostic[];
  readCache: Map<string, CachedFileRead>;
}): Promise<ReadingPlanFileContent> {
  const emptyResult = createEmptyFileContent(input.file);
  const normalizedPath = normalizePlanPath(input.file.path);
  const absolutePath = path.resolve(input.repoRoot, normalizedPath);

  if (!isPathInsideRepo(input.repoRoot, absolutePath)) {
    input.diagnostics.push({
      code: "file-outside-repo",
      message: `Reading plan file resolves outside repo root: ${input.file.path}`,
      path: input.file.path,
      batchId: input.batchId,
      severity: "warning",
    });

    return emptyResult;
  }

  const cached = input.readCache.get(absolutePath);
  if (cached) {
    return {
      ...emptyResult,
      content: cached.content,
      bytesRead: cached.bytesRead,
      truncated: cached.truncated,
    };
  }

  let content: string;
  try {
    content = await readFile(absolutePath, "utf8");
  } catch (error) {
    const code =
      error instanceof Error && "code" in error ? String(error.code) : undefined;
    input.diagnostics.push({
      code: code === "ENOENT" ? "file-not-found" : "file-read-failed",
      message:
        code === "ENOENT"
          ? `Reading plan file not found: ${input.file.path}`
          : `Failed to read reading plan file: ${input.file.path}`,
      path: input.file.path,
      batchId: input.batchId,
      severity: "warning",
    });

    return emptyResult;
  }

  const truncatedResult = truncateContent(content, input.maxBytesPerFile);
  const cachedResult: CachedFileRead = {
    content: truncatedResult.content,
    bytesRead: truncatedResult.bytesRead,
    truncated: truncatedResult.truncated,
  };

  input.readCache.set(absolutePath, cachedResult);

  if (truncatedResult.truncated) {
    input.diagnostics.push({
      code: "file-truncated",
      message: `Reading plan file exceeded maxBytesPerFile and was truncated: ${input.file.path}`,
      path: input.file.path,
      batchId: input.batchId,
      severity: "warning",
    });
  }

  return {
    ...emptyResult,
    content: cachedResult.content,
    bytesRead: cachedResult.bytesRead,
    truncated: cachedResult.truncated,
  };
}

function createEmptyFileContent(file: ReadingPlanFile): ReadingPlanFileContent {
  return {
    path: file.path,
    roleInBatch: file.roleInBatch,
    reason: file.reason,
    evidence: file.evidence,
    confidence: file.confidence,
    estimatedBytes: file.estimatedBytes,
    content: "",
    bytesRead: 0,
    truncated: false,
  };
}

function normalizeMaxBytes(maxBytesPerFile?: number): number | undefined {
  if (
    typeof maxBytesPerFile !== "number" ||
    !Number.isFinite(maxBytesPerFile)
  ) {
    return undefined;
  }

  return Math.max(0, Math.floor(maxBytesPerFile));
}

function normalizePlanPath(filePath: string): string {
  return filePath.replace(/\\/g, "/");
}

function isPathInsideRepo(repoRoot: string, candidatePath: string): boolean {
  const relative = path.relative(repoRoot, candidatePath);

  return (
    relative === "" ||
    (!relative.startsWith("..") && !path.isAbsolute(relative))
  );
}

function truncateContent(
  content: string,
  maxBytesPerFile?: number,
): CachedFileRead {
  const bytesRead = Buffer.byteLength(content, "utf8");

  if (maxBytesPerFile === undefined || bytesRead <= maxBytesPerFile) {
    return {
      content,
      bytesRead,
      truncated: false,
    };
  }

  let end = Math.min(content.length, maxBytesPerFile);

  while (end > 0) {
    const truncatedContent = content.slice(0, end);
    const truncatedBytes = Buffer.byteLength(truncatedContent, "utf8");

    if (truncatedBytes <= maxBytesPerFile) {
      return {
        content: truncatedContent,
        bytesRead: truncatedBytes,
        truncated: true,
      };
    }

    end -= 1;
  }

  return {
    content: "",
    bytesRead: 0,
    truncated: true,
  };
}
