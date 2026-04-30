#!/usr/bin/env node

// src/cli/cli.ts
import { Command as Command2 } from "commander";

// src/cli/commands/init.ts
import { Command } from "commander";
var initCommand = new Command("init").description(
  "Analyze the current repository and generate an AI-ready package"
).option("--dry-run", "Preview changes without writing files").action(async (options) => {
  console.log("Initializing bridger POC...");
  console.log("Options:", options);
});

// src/cli/cli.ts
var program = new Command2();
program.name("bridger").description("Prepare a repository for AI coding agents").version("0.1.0");
program.addCommand(initCommand);
program.parse();
