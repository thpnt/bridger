import { describe, expect, it, afterEach } from "vitest";
import { z } from "zod";

import { generateJson, generateText } from "../src/core/llm/client";

const originalOpenAIKey = process.env.OPENAI_API_KEY;

afterEach(() => {
  process.env.OPENAI_API_KEY = originalOpenAIKey;
});

describe("llm client", () => {
  it("throws a clear error when text generation is called without an API key", async () => {
    delete process.env.OPENAI_API_KEY;

    await expect(
      generateText({
        system: "You are a helpful assistant.",
        prompt: "Say hello.",
      }),
    ).rejects.toThrow(
      "Missing OPENAI_API_KEY. Add it to your .env file or environment.",
    );
  });

  it("throws a clear error when structured generation is called without an API key", async () => {
    delete process.env.OPENAI_API_KEY;

    await expect(
      generateJson({
        system: "You are a helpful assistant.",
        prompt: "Return {\"value\":\"hello\"}.",
        schemaName: "example output",
        schema: z.object({
          value: z.string(),
        }),
      }),
    ).rejects.toThrow(
      "Missing OPENAI_API_KEY. Add it to your .env file or environment.",
    );
  });
});
