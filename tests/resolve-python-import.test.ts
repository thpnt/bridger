import { describe, expect, it } from "vitest";

import { resolvePythonImport } from "../src/core/repo-graph/resolution/resolve-python-import";

describe("resolvePythonImport", () => {
  it("resolves simple absolute local imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app",
        repoFiles: ["main.py", "app.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app.py",
      confidence: "medium",
    });
  });

  it("resolves package-style imports to __init__.py", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app",
        repoFiles: ["main.py", "app/__init__.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app/__init__.py",
      confidence: "medium",
    });
  });

  it("resolves nested absolute local imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app.service",
        repoFiles: ["main.py", "app/service.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app/service.py",
      confidence: "medium",
    });
  });

  it("resolves src-layout absolute local imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "src/app/main.py",
        specifier: "app.service",
        repoFiles: ["src/app/main.py", "src/app/service.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app/service.py",
      confidence: "medium",
    });
  });

  it("resolves current-package relative imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "src/app/main.py",
        specifier: ".service",
        repoFiles: ["src/app/main.py", "src/app/service.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app/service.py",
      confidence: "high",
    });
  });

  it("resolves parent-package relative imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "src/app/routes/user.py",
        specifier: "..domain.users",
        repoFiles: ["src/app/routes/user.py", "src/app/domain/users.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app/domain/users.py",
      confidence: "high",
    });
  });

  it("ignores external packages with no local match", () => {
    for (const specifier of ["os", "sys", "requests", "fastapi"]) {
      expect(
        resolvePythonImport({
          importerPath: "main.py",
          specifier,
          repoFiles: ["main.py"],
        }),
      ).toEqual({
        status: "ignored",
        reason: "external-package",
      });
    }
  });

  it("returns unresolved for missing relative imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "src/app/main.py",
        specifier: ".missing",
        repoFiles: ["src/app/main.py"],
      }),
    ).toEqual({
      status: "unresolved",
      reason: "local-import-not-found",
    });
  });

  it("falls back to parent modules for symbol imports", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app.service",
        repoFiles: ["main.py", "app.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app.py",
      confidence: "medium",
    });
  });

  it("prefers more-specific modules over parent fallback", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app.service",
        repoFiles: ["main.py", "app.py", "app/service.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app/service.py",
      confidence: "medium",
    });
  });

  it("normalizes Windows-style importer and repo file paths", () => {
    expect(
      resolvePythonImport({
        importerPath: "src\\app\\main.py",
        specifier: ".service",
        repoFiles: ["src\\app\\main.py", "src\\app\\service.py"],
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "src/app/service.py",
      confidence: "high",
    });
  });

  it("accepts a readonly set of repo files", () => {
    expect(
      resolvePythonImport({
        importerPath: "main.py",
        specifier: "app",
        repoFiles: new Set(["main.py", "app.py"]),
      }),
    ).toEqual({
      status: "resolved",
      resolvedPath: "app.py",
      confidence: "medium",
    });
  });
});
