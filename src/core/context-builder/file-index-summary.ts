import type { FileIndex, FileIndexEntry } from "../models/file-index";

export type FileIndexSummaryOptions = {
  maxPaths?: number;
  maxTopFolders?: number;
  maxTags?: number;
  maxTaggedPathsPerTag?: number;
};

const DEFAULT_MAX_PATHS = 120;
const DEFAULT_MAX_TOP_FOLDERS = 30;
const DEFAULT_MAX_TAGS = 30;
const DEFAULT_MAX_TAGGED_PATHS_PER_TAG = 8;

const TAGS_TO_SHOW = [
  "app",
  "route",
  "components",
  "lib",
  "server",
  "database",
  "documentation",
  "config",
  "test",
];

export function summarizeFileIndexForPrompt(
  fileIndex: FileIndex,
  options?: FileIndexSummaryOptions,
): string {
  const maxPaths = options?.maxPaths ?? DEFAULT_MAX_PATHS;
  const maxTopFolders = options?.maxTopFolders ?? DEFAULT_MAX_TOP_FOLDERS;
  const maxTags = options?.maxTags ?? DEFAULT_MAX_TAGS;
  const maxTaggedPathsPerTag =
    options?.maxTaggedPathsPerTag ?? DEFAULT_MAX_TAGGED_PATHS_PER_TAG;

  const topFolders = summarizeTopFolders(fileIndex.files, maxTopFolders);
  const taggedAreas = summarizeTaggedAreas(fileIndex.files, maxTags);
  const representativeFiles = [...fileIndex.files]
    .sort(compareRepresentativeFiles)
    .slice(0, maxPaths);
  const filesByTag = summarizeFilesByTag(fileIndex.files, maxTaggedPathsPerTag);

  return [
    `Total indexed files: ${fileIndex.files.length}`,
    "",
    "Top-level folders:",
    ...formatCountLines(topFolders),
    "",
    "Detected tagged areas:",
    ...formatCountLines(taggedAreas),
    "",
    "Representative paths:",
    ...formatRepresentativeFiles(representativeFiles),
    "",
    "Representative paths by tag:",
    ...formatFilesByTag(filesByTag),
  ].join("\n");
}

function summarizeTopFolders(
  files: FileIndexEntry[],
  maxTopFolders: number,
): Array<{ name: string; count: number }> {
  const counts = new Map<string, number>();

  for (const file of files) {
    const folder = getTopFolder(file.path);
    counts.set(folder, (counts.get(folder) ?? 0) + 1);
  }

  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(compareCountAndName)
    .slice(0, maxTopFolders);
}

function summarizeTaggedAreas(
  files: FileIndexEntry[],
  maxTags: number,
): Array<{ name: string; count: number }> {
  const counts = new Map<string, number>();

  for (const file of files) {
    for (const tag of file.tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(compareCountAndName)
    .slice(0, maxTags);
}

function summarizeFilesByTag(
  files: FileIndexEntry[],
  maxTaggedPathsPerTag: number,
): Array<{ tag: string; paths: FileIndexEntry[] }> {
  const result: Array<{ tag: string; paths: FileIndexEntry[] }> = [];

  for (const tag of TAGS_TO_SHOW) {
    const taggedFiles = files
      .filter((file) => file.tags.includes(tag))
      .sort(compareRepresentativeFiles)
      .slice(0, maxTaggedPathsPerTag);

    if (taggedFiles.length === 0) {
      continue;
    }

    result.push({
      tag,
      paths: taggedFiles,
    });
  }

  return result;
}

function compareCountAndName(
  left: { name: string; count: number },
  right: { name: string; count: number },
): number {
  if (left.count !== right.count) {
    return right.count - left.count;
  }

  return compareStrings(left.name, right.name);
}

function compareRepresentativeFiles(
  left: FileIndexEntry,
  right: FileIndexEntry,
): number {
  const scoreDifference = scoreFileForPrompt(right) - scoreFileForPrompt(left);

  if (scoreDifference !== 0) {
    return scoreDifference;
  }

  return compareStrings(left.path, right.path);
}

function compareStrings(left: string, right: string): number {
  if (left < right) {
    return -1;
  }

  if (left > right) {
    return 1;
  }

  return 0;
}

function formatCountLines(items: Array<{ name: string; count: number }>): string[] {
  if (items.length === 0) {
    return ["- none"];
  }

  return items.map((item) => `- ${item.name} — ${item.count} files`);
}

function formatRepresentativeFiles(files: FileIndexEntry[]): string[] {
  if (files.length === 0) {
    return ["- none"];
  }

  return files.map((file) => `- ${formatFileIndexEntry(file)}`);
}

function formatFilesByTag(
  taggedFiles: Array<{ tag: string; paths: FileIndexEntry[] }>,
): string[] {
  if (taggedFiles.length === 0) {
    return ["- none"];
  }

  const lines: string[] = [];

  for (const entry of taggedFiles) {
    lines.push(`${entry.tag}:`);

    for (const file of entry.paths) {
      lines.push(`- ${file.path}`);
    }
  }

  return lines;
}

function getTopFolder(filePath: string): string {
  const separatorIndex = filePath.indexOf("/");

  if (separatorIndex === -1) {
    return ".";
  }

  return `${filePath.slice(0, separatorIndex + 1)}`;
}

function formatFileIndexEntry(file: FileIndexEntry): string {
  const parts: string[] = [file.path];

  if (file.tags.length > 0) {
    parts.push(`[${file.tags.join(", ")}]`);
  }

  if (file.reason) {
    parts.push(`— ${file.reason}`);
  }

  return parts.join(" ");
}

function scoreFileForPrompt(file: FileIndexEntry): number {
  let score = 0;

  for (const tag of file.tags) {
    score += getTagScore(tag);
  }

  if (file.path.includes("/schema.")) {
    score += 40;
  }

  if (file.path.includes("/schemas/")) {
    score += 35;
  }

  if (file.path.includes("/types.")) {
    score += 25;
  }

  if (file.path.includes("/models/")) {
    score += 25;
  }

  if (file.path.endsWith("/page.tsx")) {
    score += 35;
  }

  if (file.path.endsWith("/layout.tsx")) {
    score += 35;
  }

  if (file.path.endsWith("/route.ts")) {
    score += 35;
  }

  if (file.path.endsWith("schema.prisma")) {
    score += 50;
  }

  return score;
}

function getTagScore(tag: string): number {
  switch (tag) {
    case "important":
      return 100;
    case "readme":
    case "agent-rules":
      return 90;
    case "package":
      return 70;
    case "app":
    case "route":
      return 60;
    case "database":
      return 55;
    case "server":
    case "components":
    case "lib":
      return 45;
    case "documentation":
    case "test":
      return 35;
    case "config":
      return 30;
    default:
      return 0;
  }
}
