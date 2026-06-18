import fs from "fs-extra";
import path from "node:path";

import type { FileIndex } from "../models/file-index";
import { ImportantFilesSchema } from "../models/important-file";
import type { ImportantFile } from "../models/important-file";
import {
  classifyImportantFile,
  IMPORTANT_FILE_BUDGETS,
  IMPORTANT_FILE_CATEGORY_LIMITS,
  isAllowedImportantFileExtension,
  type ImportantFileCandidate,
  type ImportantFileCategory,
} from "./important-file-rules";

function dedupeCandidates(
  candidates: ImportantFileCandidate[],
): ImportantFileCandidate[] {
  const byPath = new Map<string, ImportantFileCandidate>();

  for (const candidate of candidates) {
    const existing = byPath.get(candidate.path);

    if (existing === undefined) {
      byPath.set(candidate.path, candidate);
      continue;
    }

    if (candidate.priority < existing.priority) {
      byPath.set(candidate.path, candidate);
    }
  }

  return [...byPath.values()];
}

function createCategoryCounts(): Record<ImportantFileCategory, number> {
  return {
    agent: 0,
    docs: 0,
    entrypoint: 0,
    domain: 0,
    component: 0,
    test: 0,
    config: 0,
  };
}

export async function readImportantFiles(input: {
  repoRoot: string;
  fileIndex: FileIndex;
}): Promise<ImportantFile[]> {
  const normalizedRepoRoot = path.resolve(input.repoRoot);
  const candidates: ImportantFileCandidate[] = [];

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

  const selectedFiles: ImportantFile[] = [];
  const categoryCounts = createCategoryCounts();
  let totalBytes = 0;
  let configBytes = 0;

  for (const candidate of selectedCandidates) {
    const entry = input.fileIndex.files.find((file) => file.path === candidate.path);

    if (entry === undefined) {
      continue;
    }

    if (entry.sizeBytes > IMPORTANT_FILE_BUDGETS.maxSingleFileBytes) {
      continue;
    }

    if (
      categoryCounts[candidate.category] >=
      IMPORTANT_FILE_CATEGORY_LIMITS[candidate.category]
    ) {
      continue;
    }

    if (
      totalBytes + entry.sizeBytes >
      IMPORTANT_FILE_BUDGETS.maxTotalContentBytes
    ) {
      continue;
    }

    if (
      candidate.category === "config" &&
      configBytes + entry.sizeBytes > IMPORTANT_FILE_BUDGETS.maxConfigTotalBytes
    ) {
      continue;
    }

    const absolutePath = path.resolve(normalizedRepoRoot, candidate.path);

    if (
      !absolutePath.startsWith(`${normalizedRepoRoot}${path.sep}`) &&
      absolutePath !== normalizedRepoRoot
    ) {
      continue;
    }

    let content: string;

    try {
      content = await fs.readFile(absolutePath, "utf8");
    } catch {
      continue;
    }

    const contentBytes = Buffer.byteLength(content, "utf8");

    if (contentBytes > IMPORTANT_FILE_BUDGETS.maxSingleFileBytes) {
      continue;
    }

    if (
      totalBytes + contentBytes >
      IMPORTANT_FILE_BUDGETS.maxTotalContentBytes
    ) {
      continue;
    }

    if (
      candidate.category === "config" &&
      configBytes + contentBytes > IMPORTANT_FILE_BUDGETS.maxConfigTotalBytes
    ) {
      continue;
    }

    selectedFiles.push({
      path: candidate.path,
      reason: candidate.reason,
      content,
    });

    totalBytes += contentBytes;
    categoryCounts[candidate.category] += 1;

    if (candidate.category === "config") {
      configBytes += contentBytes;
    }
  }

  return ImportantFilesSchema.parse(selectedFiles);
}
