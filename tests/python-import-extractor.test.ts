import { describe, expect, it } from "vitest";

import type { ExtractedImport } from "../src/core/repo-graph/extractors/dependency-extractor";
import {
  extractPythonImports,
  pythonImportExtractor,
} from "../src/core/repo-graph/extractors/python-import-extractor";

function simplify(imports: ExtractedImport[]) {
  return imports.map((item) => ({
    specifier: item.specifier,
    kind: item.kind,
  }));
}

describe("pythonImportExtractor", () => {
  it("extracts import statements", () => {
    const imports = extractPythonImports(`
import foo
import foo.bar
import os, sys
import package.module as pm
`);

    expect(simplify(imports)).toEqual([
      { specifier: "foo", kind: "static" },
      { specifier: "foo.bar", kind: "static" },
      { specifier: "os", kind: "static" },
      { specifier: "sys", kind: "static" },
      { specifier: "package.module", kind: "static" },
    ]);
  });

  it("extracts from-import statements", () => {
    const imports = extractPythonImports(`
from foo import bar
from foo.bar import baz
from package import service as svc
from package import a, b
from package import *
`);

    expect(simplify(imports)).toEqual([
      { specifier: "foo.bar", kind: "static" },
      { specifier: "foo.bar.baz", kind: "static" },
      { specifier: "package.service", kind: "static" },
      { specifier: "package.a", kind: "static" },
      { specifier: "package.b", kind: "static" },
      { specifier: "package", kind: "static" },
    ]);
  });

  it("extracts relative imports", () => {
    const imports = extractPythonImports(`
from . import local_module
from .local_module import thing
from ..domain import service
from .. import settings
`);

    expect(simplify(imports)).toEqual([
      { specifier: ".local_module", kind: "static" },
      { specifier: ".local_module.thing", kind: "static" },
      { specifier: "..domain.service", kind: "static" },
      { specifier: "..settings", kind: "static" },
    ]);
  });

  it("ignores commented import lines", () => {
    const imports = extractPythonImports(`
# import old
# from old import thing
import current
`);

    expect(simplify(imports)).toEqual([
      { specifier: "current", kind: "static" },
    ]);
  });

  it("strips inline comments", () => {
    const imports = extractPythonImports(`
import foo  # comment
from bar import baz  # comment
`);

    expect(simplify(imports)).toEqual([
      { specifier: "foo", kind: "static" },
      { specifier: "bar.baz", kind: "static" },
    ]);
  });

  it("declares Python extractor metadata", () => {
    expect(pythonImportExtractor.language).toBe("python");
    expect(pythonImportExtractor.extensions).toEqual([".py"]);
    expect(pythonImportExtractor.source).toBe("python-imports");
  });

  it("can be used through the dependency extractor interface", () => {
    const imports = pythonImportExtractor.extractImports({
      filePath: "src/app/main.py",
      content: "from . import service",
    });

    expect(simplify(imports)).toEqual([
      { specifier: ".service", kind: "static" },
    ]);
  });

  it("includes positive line numbers", () => {
    const imports = extractPythonImports(`

import foo
`);

    expect(imports[0]?.line).toBe(3);
  });
});
