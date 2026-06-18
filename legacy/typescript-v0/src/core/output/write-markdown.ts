import fs from "node:fs/promises";
import path from "node:path";

export async function writeMarkdown(filePath: string, content: string): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });

  const output = content.endsWith("\n") ? content : `${content}\n`;
  await fs.writeFile(filePath, output, "utf8");
}
