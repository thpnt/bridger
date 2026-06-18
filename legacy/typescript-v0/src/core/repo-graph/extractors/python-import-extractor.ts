import {
  ExtractedImportSchema,
  type DependencyExtractor,
  type ExtractedImport,
} from "./dependency-extractor";

const PYTHON_EXTENSIONS = [".py"] as const;

const IMPORT_REGEX = /^import\s+(.+)$/;
const FROM_IMPORT_REGEX = /^from\s+([.\w]+)\s+import\s+(.+)$/;

export const pythonImportExtractor: DependencyExtractor = {
  language: "python",
  extensions: PYTHON_EXTENSIONS,
  source: "python-imports",
  extractImports(input) {
    return extractPythonImports(input.content);
  },
};

export function extractPythonImports(content: string): ExtractedImport[] {
  const imports: ExtractedImport[] = [];
  const seen = new Set<string>();
  const lines = content.split(/\r?\n/);

  lines.forEach((rawLine, index) => {
    const lineNumber = index + 1;
    const line = stripInlineComment(rawLine).trim();

    if (!line) {
      return;
    }

    collectImportLine({
      line,
      lineNumber,
      imports,
      seen,
    });

    collectFromImportLine({
      line,
      lineNumber,
      imports,
      seen,
    });
  });

  return imports;
}

function collectImportLine(input: {
  line: string;
  lineNumber: number;
  imports: ExtractedImport[];
  seen: Set<string>;
}): void {
  const match = input.line.match(IMPORT_REGEX);

  if (!match?.[1]) {
    return;
  }

  for (const rawModuleName of match[1].split(",")) {
    const moduleName = stripAlias(rawModuleName.trim());

    if (!isValidPythonModuleSpecifier(moduleName)) {
      continue;
    }

    addImport({
      specifier: moduleName,
      lineNumber: input.lineNumber,
      imports: input.imports,
      seen: input.seen,
    });
  }
}

function collectFromImportLine(input: {
  line: string;
  lineNumber: number;
  imports: ExtractedImport[];
  seen: Set<string>;
}): void {
  const match = input.line.match(FROM_IMPORT_REGEX);

  if (!match?.[1] || !match[2]) {
    return;
  }

  const moduleName = match[1].trim();
  const importedNames = match[2].split(",");

  if (!isValidPythonModuleSpecifier(moduleName)) {
    return;
  }

  for (const rawImportedName of importedNames) {
    const importedName = stripAlias(rawImportedName.trim());

    if (!isValidPythonImportedName(importedName)) {
      continue;
    }

    addImport({
      specifier: buildFromImportSpecifier(moduleName, importedName),
      lineNumber: input.lineNumber,
      imports: input.imports,
      seen: input.seen,
    });
  }
}

function addImport(input: {
  specifier: string;
  lineNumber: number;
  imports: ExtractedImport[];
  seen: Set<string>;
}): void {
  const key = `${input.specifier}\0${input.lineNumber}`;

  if (input.seen.has(key)) {
    return;
  }

  input.seen.add(key);

  input.imports.push(
    ExtractedImportSchema.parse({
      specifier: input.specifier,
      kind: "static",
      source: "python-imports",
      line: input.lineNumber,
    }),
  );
}

function stripAlias(value: string): string {
  return value.split(/\s+as\s+/i)[0]?.trim() ?? "";
}

function stripInlineComment(line: string): string {
  const trimmed = line.trimStart();

  if (trimmed.startsWith("#")) {
    return "";
  }

  const commentIndex = line.indexOf("#");

  if (commentIndex === -1) {
    return line;
  }

  return line.slice(0, commentIndex);
}

function buildFromImportSpecifier(
  moduleName: string,
  importedName: string,
): string {
  if (importedName === "*") {
    return moduleName;
  }

  if (moduleName === ".") {
    return `.${importedName}`;
  }

  if (moduleName === "..") {
    return `..${importedName}`;
  }

  return `${moduleName}.${importedName}`;
}

function isValidPythonModuleSpecifier(value: string): boolean {
  return (
    /^\.+$/.test(value) ||
    /^\.*[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$/.test(value)
  );
}

function isValidPythonImportedName(value: string): boolean {
  return value === "*" || /^[A-Za-z_][\w]*$/.test(value);
}
