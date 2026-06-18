import { afterEach, describe, expect, it, vi } from "vitest";

import { logger } from "../../src/shared/logger";

const originalDebug = process.env.DEBUG;
const originalLifecycleEvent = process.env.npm_lifecycle_event;

function restoreEnv(name: "DEBUG" | "npm_lifecycle_event", value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
    return;
  }

  process.env[name] = value;
}

afterEach(() => {
  restoreEnv("DEBUG", originalDebug);
  restoreEnv("npm_lifecycle_event", originalLifecycleEvent);
  vi.restoreAllMocks();
});

describe("logger.debug", () => {
  it("logs debug output when launched through the dev script", () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);

    delete process.env.DEBUG;
    process.env.npm_lifecycle_event = "dev";

    logger.debug("dev message");

    expect(logSpy).toHaveBeenCalledWith("dev message");
  });

  it("logs debug output when DEBUG is bridger", () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);

    delete process.env.npm_lifecycle_event;
    process.env.DEBUG = "bridger";

    logger.debug("debug message");

    expect(logSpy).toHaveBeenCalledWith("debug message");
  });

  it("stays silent otherwise", () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);

    delete process.env.DEBUG;
    delete process.env.npm_lifecycle_event;

    logger.debug("hidden message");

    expect(logSpy).not.toHaveBeenCalled();
  });
});
