import { Command } from "commander";
import { pathToFileURL } from "node:url";
import { inspectCommand } from "./commands/inspect";
import { initCommand } from "./commands/init";

export function buildCliProgram(): Command {
  const program = new Command();

  program
    .name("bridger")
    .description("Prepare a repository for AI coding agents")
    .version("0.1.0");

  program.addCommand(initCommand);
  program.addCommand(inspectCommand);

  return program;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  buildCliProgram().parse();
}
