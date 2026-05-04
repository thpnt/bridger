import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

const originalOpenAIKey = process.env.OPENAI_API_KEY;

function mockOpenAIClient(input: {
  create?: ReturnType<typeof vi.fn>;
  parse?: ReturnType<typeof vi.fn>;
}) {
  class MockOpenAI {
    responses = {
      create: input.create ?? vi.fn(),
      parse: input.parse ?? vi.fn(),
    };
  }

  return {
    default: MockOpenAI,
  };
}

describe("llm client with a mocked OpenAI provider", () => {
  beforeEach(() => {
    process.env.OPENAI_API_KEY = "test-key";
  });

  afterEach(() => {
    process.env.OPENAI_API_KEY = originalOpenAIKey;
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("returns generated text from the provider", async () => {
    const responsesCreate = vi.fn().mockResolvedValue({
      output_text: "Generated markdown",
    });

    vi.doMock("openai", () =>
      mockOpenAIClient({
        create: responsesCreate,
      }),
    );

    const { generateText } = await import("../src/core/llm/client");

    await expect(
      generateText({
        system: "system",
        prompt: "prompt",
      }),
    ).resolves.toBe("Generated markdown");

    expect(responsesCreate).toHaveBeenCalledTimes(1);
  });

  it("wraps provider errors during text generation", async () => {
    const responsesCreate = vi.fn().mockRejectedValue(new Error("boom"));

    vi.doMock("openai", () =>
      mockOpenAIClient({
        create: responsesCreate,
      }),
    );

    const { generateText } = await import("../src/core/llm/client");

    await expect(
      generateText({
        system: "system",
        prompt: "prompt",
      }),
    ).rejects.toThrow("OpenAI text generation failed: boom");
  });

  it("fails with a useful error when parsed structured output does not match the schema", async () => {
    vi.doMock("openai", () =>
      mockOpenAIClient({
        parse: vi.fn().mockResolvedValue({
          output_parsed: {
            value: 42,
          },
        }),
      }),
    );

    vi.doMock("openai/helpers/zod", () => ({
      zodTextFormat: vi.fn().mockReturnValue({ type: "json_schema" }),
    }));

    const { generateJson } = await import("../src/core/llm/client");

    await expect(
      generateJson({
        system: "system",
        prompt: "prompt",
        schemaName: "example output",
        schema: z.object({
          value: z.string(),
        }),
      }),
    ).rejects.toThrow("Structured output validation failed for example_output");
  });

  it("fails with a useful error when the provider returns no parsed structured output", async () => {
    vi.doMock("openai", () =>
      mockOpenAIClient({
        parse: vi.fn().mockResolvedValue({
          output_parsed: undefined,
        }),
      }),
    );

    vi.doMock("openai/helpers/zod", () => ({
      zodTextFormat: vi.fn().mockReturnValue({ type: "json_schema" }),
    }));

    const { generateJson } = await import("../src/core/llm/client");

    await expect(
      generateJson({
        system: "system",
        prompt: "prompt",
        schemaName: "example output",
        schema: z.object({
          value: z.string(),
        }),
      }),
    ).rejects.toThrow("OpenAI returned no parsed example_output response.");
  });
});
