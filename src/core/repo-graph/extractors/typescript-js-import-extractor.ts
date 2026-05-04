import {
  ExtractedImportSchema,
  type DependencyExtractor,
  type ExtractedImport,
  type ExtractedImportKind,
} from "./dependency-extractor";

const TYPESCRIPT_JS_EXTENSIONS = [
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
] as const;

const STATIC_IMPORT_REGEX =
  /\bimport\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']/g;

const REEXPORT_REGEX =
  /\bexport\s+(?:type\s+)?(?:\*|\{[\s\S]*?\})\s+from\s+["']([^"']+)["']/g;

const REQUIRE_REGEX = /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g;

const DYNAMIC_IMPORT_REGEX = /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g;

export const typescriptJsImportExtractor: DependencyExtractor = {
  language: "typescript-javascript",
  extensions: TYPESCRIPT_JS_EXTENSIONS,
  source: "typescript-js-imports",
  extractImports(input) {
    return extractTypeScriptJsImports(input.content);
  },
};

export function extractTypeScriptJsImports(content: string): ExtractedImport[] {
  const imports: ExtractedImport[] = [];
  const seen = new Set<string>();

  collectMatches({
    content,
    regex: STATIC_IMPORT_REGEX,
    kind: "static",
    imports,
    seen,
  });

  collectMatches({
    content,
    regex: REEXPORT_REGEX,
    kind: "reexport",
    imports,
    seen,
  });

  collectMatches({
    content,
    regex: REQUIRE_REGEX,
    kind: "require",
    imports,
    seen,
  });

  collectMatches({
    content,
    regex: DYNAMIC_IMPORT_REGEX,
    kind: "dynamic",
    imports,
    seen,
  });

  return imports;
}

function collectMatches(input: {
  content: string;
  regex: RegExp;
  kind: ExtractedImportKind;
  imports: ExtractedImport[];
  seen: Set<string>;
}): void {
  input.regex.lastIndex = 0;

  for (const match of input.content.matchAll(input.regex)) {
    const specifier = match[1];

    if (!specifier || isCommentedOutLine(input.content, match.index ?? 0)) {
      continue;
    }

    const line = getLineNumber(input.content, match.index ?? 0);
    const key = `${input.kind}\0${specifier}\0${line}`;

    if (input.seen.has(key)) {
      continue;
    }

    input.seen.add(key);

    input.imports.push(
      ExtractedImportSchema.parse({
        specifier,
        kind: input.kind,
        source: "typescript-js-imports",
        line,
      }),
    );
  }
}

function getLineNumber(content: string, index: number): number {
  return content.slice(0, index).split("\n").length;
}

function isCommentedOutLine(content: string, index: number): boolean {
  const lineStart = content.lastIndexOf("\n", index) + 1;
  const lineEnd = content.indexOf("\n", index);
  const line =
    lineEnd === -1
      ? content.slice(lineStart)
      : content.slice(lineStart, lineEnd);

  return line.trimStart().startsWith("//");
}
