import { describe, expect, it } from "vitest";

import { buildCliProgram } from "../../src/cli/cli";

describe("cli bootstrap", () => {
  it("registers the expected top-level commands", () => {
    const program = buildCliProgram();
    const commands = program.commands.map((command) => command.name());
    const initCommand = program.commands.find(
      (command) => command.name() === "init",
    );

    expect(program.name()).toBe("bridger");
    expect(commands).toEqual(["init", "inspect", "enrich-ticket"]);
    expect(
      initCommand?.options.some(
        (option) => option.long === "--write-agents-md",
      ),
    ).toBe(true);
    expect(
      initCommand?.options.some((option) => option.long === "--repo"),
    ).toBe(true);
  });
});
