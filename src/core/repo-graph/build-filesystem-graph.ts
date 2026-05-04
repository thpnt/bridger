import type { FileIndex } from "../models/file-index";
import {
  RepoGraphEdgeSchema,
  RepoGraphNodeSchema,
  type RepoGraphEdge,
  type RepoGraphNode,
} from "./models/repo-graph";
import { detectLanguageFromExtension } from "./utils/detect-language";
import { normalizeRepoPath } from "./utils/normalize-path";
import { getPathTags } from "./utils/path-tags";

export type FilesystemGraphBuildResult = {
  nodes: RepoGraphNode[];
  edges: RepoGraphEdge[];
};

export function buildFilesystemGraph(input: {
  repoRoot: string;
  fileIndex: FileIndex;
}): FilesystemGraphBuildResult {
  const nodesById = new Map<string, RepoGraphNode>();
  const edgesByKey = new Map<string, RepoGraphEdge>();

  for (const file of input.fileIndex.files) {
    const filePath = normalizeRepoPath(file.path);

    addParentDirectories({
      filePath,
      nodesById,
      edgesByKey,
    });

    addFileNode({
      file,
      filePath,
      nodesById,
    });

    addFileContainsEdge({
      filePath,
      edgesByKey,
    });
  }

  return {
    nodes: Array.from(nodesById.values()).sort(compareNodes),
    edges: Array.from(edgesByKey.values()).sort(compareEdges),
  };
}

function addParentDirectories(input: {
  filePath: string;
  nodesById: Map<string, RepoGraphNode>;
  edgesByKey: Map<string, RepoGraphEdge>;
}): void {
  const parentDirectories = getParentDirectories(input.filePath);

  for (const directoryPath of parentDirectories) {
    addDirectoryNode({
      directoryPath,
      nodesById: input.nodesById,
    });

    const parentDirectory = getParentDirectory(directoryPath);

    if (parentDirectory === null) {
      continue;
    }

    addContainsEdge({
      from: parentDirectory,
      to: directoryPath,
      edgesByKey: input.edgesByKey,
    });
  }
}

function addDirectoryNode(input: {
  directoryPath: string;
  nodesById: Map<string, RepoGraphNode>;
}): void {
  if (input.nodesById.has(input.directoryPath)) {
    return;
  }

  const node = RepoGraphNodeSchema.parse({
    id: input.directoryPath,
    path: input.directoryPath,
    kind: "directory",
    extension: null,
    language: "unknown",
    sizeBytes: 0,
    tags: getPathTags(input.directoryPath),
  });

  input.nodesById.set(node.id, node);
}

function addFileNode(input: {
  file: FileIndex["files"][number];
  filePath: string;
  nodesById: Map<string, RepoGraphNode>;
}): void {
  if (input.nodesById.has(input.filePath)) {
    return;
  }

  const extension = normalizeFileExtension(input.file.extension, input.filePath);

  const node = RepoGraphNodeSchema.parse({
    id: input.filePath,
    path: input.filePath,
    kind: "file",
    extension,
    language: detectLanguageFromExtension(extension),
    sizeBytes: input.file.sizeBytes,
    tags: getPathTags(input.filePath),
  });

  input.nodesById.set(node.id, node);
}

function addFileContainsEdge(input: {
  filePath: string;
  edgesByKey: Map<string, RepoGraphEdge>;
}): void {
  const parentDirectory = getParentDirectory(input.filePath);

  if (parentDirectory === null) {
    return;
  }

  addContainsEdge({
    from: parentDirectory,
    to: input.filePath,
    edgesByKey: input.edgesByKey,
  });
}

function addContainsEdge(input: {
  from: string;
  to: string;
  edgesByKey: Map<string, RepoGraphEdge>;
}): void {
  const edge = RepoGraphEdgeSchema.parse({
    from: input.from,
    to: input.to,
    type: "contains",
    confidence: "high",
    source: "filesystem",
  });

  const key = getEdgeKey(edge.from, edge.to, edge.type);

  if (input.edgesByKey.has(key)) {
    return;
  }

  input.edgesByKey.set(key, edge);
}

function getParentDirectories(filePath: string): string[] {
  const segments = filePath.split("/");

  if (segments.length <= 1) {
    return [];
  }

  const directories: string[] = [];

  for (let index = 1; index < segments.length; index += 1) {
    directories.push(segments.slice(0, index).join("/"));
  }

  return directories;
}

function getParentDirectory(filePath: string): string | null {
  const lastSlashIndex = filePath.lastIndexOf("/");

  if (lastSlashIndex === -1) {
    return null;
  }

  return filePath.slice(0, lastSlashIndex);
}

function normalizeFileExtension(
  extension: string | undefined,
  filePath: string,
): string | null {
  if (typeof extension === "string" && extension.trim() !== "") {
    const normalizedExtension = extension.startsWith(".")
      ? extension
      : `.${extension}`;

    return normalizedExtension.toLowerCase();
  }

  return inferExtensionFromPath(filePath);
}

function inferExtensionFromPath(filePath: string): string | null {
  const fileName = filePath.split("/").at(-1);

  if (!fileName) {
    return null;
  }

  const dotIndex = fileName.lastIndexOf(".");

  if (dotIndex <= 0) {
    return null;
  }

  return fileName.slice(dotIndex).toLowerCase();
}

function getEdgeKey(from: string, to: string, type: string): string {
  return `${from}\0${to}\0${type}`;
}

function compareNodes(a: RepoGraphNode, b: RepoGraphNode): number {
  return a.path.localeCompare(b.path);
}

function compareEdges(a: RepoGraphEdge, b: RepoGraphEdge): number {
  return (
    a.from.localeCompare(b.from) ||
    a.to.localeCompare(b.to) ||
    a.type.localeCompare(b.type)
  );
}
