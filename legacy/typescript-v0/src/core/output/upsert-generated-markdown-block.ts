import fs from "node:fs/promises";
import path from "node:path";

async function readExistingContent(filePath: string): Promise<string | null> {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch (error) {
    if (
      error instanceof Error &&
      "code" in error &&
      (error as NodeJS.ErrnoException).code === "ENOENT"
    ) {
      return null;
    }

    throw error;
  }
}

function buildGeneratedBlock(
  content: string,
  startMarker: string,
  endMarker: string,
): string {
  return `${startMarker}\n\n${content.trimEnd()}\n\n${endMarker}\n`;
}

export async function upsertGeneratedMarkdownBlock(input: {
  filePath: string;
  content: string;
  startMarker: string;
  endMarker: string;
}): Promise<void> {
  const existingContent = await readExistingContent(input.filePath);
  const generatedBlock = buildGeneratedBlock(
    input.content,
    input.startMarker,
    input.endMarker,
  );

  if (existingContent === null) {
    await fs.mkdir(path.dirname(input.filePath), { recursive: true });
    await fs.writeFile(input.filePath, generatedBlock, "utf8");
    return;
  }

  const startIndex = existingContent.indexOf(input.startMarker);
  const endIndex = existingContent.indexOf(input.endMarker);

  if (startIndex === -1 && endIndex === -1) {
    const separator = existingContent.endsWith("\n") ? "\n" : "\n\n";
    const contentToWrite = `${existingContent}${separator}${generatedBlock}`;

    await fs.writeFile(input.filePath, contentToWrite, "utf8");
    return;
  }

  if (startIndex === -1 || endIndex === -1) {
    throw new Error(
      `Malformed generated block in ${input.filePath}: expected both markers "${input.startMarker}" and "${input.endMarker}".`,
    );
  }

  if (endIndex < startIndex) {
    throw new Error(
      `Malformed generated block in ${input.filePath}: end marker appears before start marker.`,
    );
  }

  const before = existingContent.slice(0, startIndex);
  const after = existingContent.slice(endIndex + input.endMarker.length);
  const normalizedAfter = after.startsWith("\n") ? after.slice(1) : after;
  const nextContent = `${before}${generatedBlock}${normalizedAfter}`;

  await fs.writeFile(input.filePath, nextContent, "utf8");
}
