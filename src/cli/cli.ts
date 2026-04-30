import { Command } from "commander";
import { inspectCommand } from "./commands/inspect";
import { initCommand } from "./commands/init";

const program = new Command();

program
  .name("bridger")
  .description("Prepare a repository for AI coding agents")
  .version("0.1.0");

program.addCommand(initCommand);
program.addCommand(inspectCommand);

program.parse();
