import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { ImportantFilesSchema } from "../src/core/models/important-file";
import {
  IMPORTANT_FILE_BUDGETS,
  classifyImportantFile,
} from "../src/core/repo-scanner/important-file-rules";
import { buildFileIndex } from "../src/core/repo-scanner/build-file-index";
import { readImportantFiles } from "../src/core/repo-scanner/read-important-files";
import { getGeneratedKnowledgeDocRelativePath } from "../src/core/models/generated-paths";

let tempDir = "";

async function writeFixtureFile(relativePath: string, content: string | Buffer): Promise<void> {
  const absolutePath = path.join(tempDir, relativePath);

  await fs.outputFile(absolutePath, content);
}

async function createFixtureRepo(): Promise<string> {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-important-files-"));

  await writeFixtureFile("README.md", "# Fixture repo\n");
  await writeFixtureFile("AGENTS.md", "# Agent instructions\n");
  await writeFixtureFile("package.json", '{\n  "name": "fixture",\n  "private": true\n}\n');
  await writeFixtureFile("tsconfig.json", '{\n  "compilerOptions": {\n    "strict": true\n  }\n}\n');
  await writeFixtureFile("next.config.ts", "const nextConfig = {};\nexport default nextConfig;\n");
  await writeFixtureFile("pnpm-lock.yaml", "lockfileVersion: 9\n");
  await writeFixtureFile("src/app/layout.tsx", "export default function Layout({ children }: { children: React.ReactNode }) {\n  return <html><body>{children}</body></html>;\n}\n");
  await writeFixtureFile("src/app/page.tsx", "export default function Page() {\n  return <main>Home</main>;\n}\n");
  await writeFixtureFile("src/app/api/health/route.ts", "export async function GET() {\n  return Response.json({ ok: true });\n}\n");
  await writeFixtureFile("src/domains/billing/schema.ts", "export const billingSchema = {\n  plan: 'pro',\n};\n");
  await writeFixtureFile("src/domains/billing/service.ts", "export function createBillingService() {\n  return {\n    createInvoice() {\n      return true;\n    },\n  };\n}\n");
  await writeFixtureFile("src/lib/supabase.ts", "export const supabase = {\n  url: 'https://example.com',\n};\n");
  await writeFixtureFile("src/components/ui/button.tsx", "export function Button() {\n  return <button type=\"button\">Click</button>;\n}\n");
  await writeFixtureFile("src/components/navigation/sidebar.tsx", "export function Sidebar() {\n  return <nav>Sidebar</nav>;\n}\n");
  await writeFixtureFile("src/__tests__/billing.test.ts", "import { describe, expect, it } from 'vitest';\n\ndescribe('billing', () => {\n  it('works', () => {\n    expect(true).toBe(true);\n  });\n});\n");
  await writeFixtureFile("public/logo.png", Buffer.from([0, 1, 2, 3]));
  await writeFixtureFile(
    getGeneratedKnowledgeDocRelativePath("architecture"),
    "# Generated architecture\n",
  );
  await writeFixtureFile(".agents/skills/generated-skill/SKILL.md", "# Generated skill\n");
  await writeFixtureFile(
    "src/domains/large/huge-service.ts",
    `export const hugeServiceNotes = [\n${Array.from({ length: 3000 }, (_, index) => `  "note ${index}",\n`).join("")}];\n`,
  );

  return tempDir;
}

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("readImportantFiles", () => {
  it("reads a prioritized, budgeted set of important files from a FileIndex", async () => {
    const fixtureRoot = await createFixtureRepo();
    const fileIndex = await buildFileIndex(fixtureRoot);
    const importantFiles = await readImportantFiles({
      repoRoot: fixtureRoot,
      fileIndex,
    });

    expect(ImportantFilesSchema.parse(importantFiles)).toEqual(importantFiles);
    expect(importantFiles.length).toBeGreaterThan(0);

    const paths = importantFiles.map((entry) => entry.path);
    const totalContentBytes = importantFiles.reduce(
      (sum, entry) => sum + Buffer.byteLength(entry.content, "utf8"),
      0,
    );
    const configContentBytes = importantFiles.reduce((sum, entry) => {
      const candidate = classifyImportantFile(entry.path);

      return candidate?.category === "config"
        ? sum + Buffer.byteLength(entry.content, "utf8")
        : sum;
    }, 0);

    expect(paths).toEqual(
      expect.arrayContaining([
        "AGENTS.md",
        "README.md",
        "src/app/layout.tsx",
        "src/app/page.tsx",
        "src/app/api/health/route.ts",
        "src/domains/billing/schema.ts",
        "src/domains/billing/service.ts",
        "src/lib/supabase.ts",
        "src/components/ui/button.tsx",
        "src/components/navigation/sidebar.tsx",
        "src/__tests__/billing.test.ts",
      ]),
    );

    expect(paths).toEqual(
      expect.arrayContaining(["package.json", "tsconfig.json", "next.config.ts"]),
    );

    expect(paths).not.toEqual(expect.arrayContaining(["pnpm-lock.yaml"]));
    expect(paths).not.toEqual(expect.arrayContaining(["public/logo.png"]));
    expect(paths).not.toEqual(
      expect.arrayContaining([
        getGeneratedKnowledgeDocRelativePath("architecture"),
      ]),
    );
    expect(paths).not.toEqual(
      expect.arrayContaining([".agents/skills/generated-skill/SKILL.md"]),
    );
    expect(paths).not.toEqual(expect.arrayContaining(["src/domains/large/huge-service.ts"]));

    expect(paths.every((value) => !path.isAbsolute(value))).toBe(true);
    expect(totalContentBytes).toBeLessThanOrEqual(
      IMPORTANT_FILE_BUDGETS.maxTotalContentBytes,
    );
    expect(configContentBytes).toBeLessThanOrEqual(
      IMPORTANT_FILE_BUDGETS.maxConfigTotalBytes,
    );
  });

  it("skips files that disappear after indexing", async () => {
    const fixtureRoot = await createFixtureRepo();
    const fileIndex = await buildFileIndex(fixtureRoot);

    await fs.remove(path.join(fixtureRoot, "README.md"));

    const importantFiles = await readImportantFiles({
      repoRoot: fixtureRoot,
      fileIndex,
    });

    expect(importantFiles.some((entry) => entry.path === "README.md")).toBe(false);
    expect(importantFiles.length).toBeGreaterThan(0);
  });
});
