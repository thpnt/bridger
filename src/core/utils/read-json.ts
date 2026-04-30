import fs from "node:fs/promises";

export async function readJsonFile<T>(filePath: string): Promise<T> {
  let content: string;

  try {
    content = await fs.readFile(filePath, "utf8");
  } catch {
    throw new Error(`Failed to read JSON file: ${filePath}`);
  }

  try {
    return JSON.parse(content) as T;
  } catch {
    throw new Error(`Invalid JSON file: ${filePath}`);
  }
}
