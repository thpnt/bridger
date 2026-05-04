import { z } from "zod";

import { generateJson, generateText } from "../src/core/llm/client";

interface TestLlmResult {
  text: string;
  json: {
    message: string;
  };
}

async function main(): Promise<void> {
  console.log("Testing Bridger LLM client...");

  const text = await generateText({
    system: "You write short, direct confirmations.",
    prompt: "Reply with exactly: Bridger LLM client is working.",
  });

  const json = await generateJson({
    system: "You return only structured data.",
    prompt: "Return an object with message exactly equal to 'Bridger LLM client is working'.",
    schemaName: "llm_client_test",
    schema: z.object({
      message: z.string(),
    }),
  });

  const result: TestLlmResult = {
    text,
    json,
  };

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);

  console.error(message);
  process.exitCode = 1;
});
