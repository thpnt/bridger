import { describe, expect, it } from "vitest";

import { buildCliProgram } from "../../src/cli/cli";

describe("cli bootstrap", () => {
  it("registers the expected top-level commands", () => {
    const program = buildCliProgram();
    const commands = program.commands.map((command) => command.name());

    expect(program.name()).toBe("bridger");
    expect(commands).toEqual(["init", "inspect", "enrich-ticket"]);
  });
});
