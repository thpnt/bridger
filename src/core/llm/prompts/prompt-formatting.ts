import type { ImportantFile } from "../../models/important-file";

export function formatImportantFilesForPrompt(files: ImportantFile[]): string {
  if (files.length === 0) {
    return "none";
  }

  return files
    .map((file) =>
      [
        `--- FILE: ${file.path}`,
        `Reason: ${file.reason}`,
        file.content,
        "--- END FILE",
      ].join("\n"),
    )
    .join("\n\n");
}
