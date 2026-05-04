import { Command } from "commander";

export const enrichTicketCommand = new Command("enrich-ticket")
  .description("Expand a rough request into an implementation-ready ticket")
  .argument("<request>", "Rough product or engineering request")
  .action(async (request: string) => {
    console.log("Enriching ticket POC...");
    console.log("Request:", request);
  });
