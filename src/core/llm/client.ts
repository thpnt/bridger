import "dotenv/config";

import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import { z } from "zod";

const DEFAULT_MODEL = "gpt-5.5-thinking";

let cachedClient: OpenAI | null = null;

function getModel(): string {
  return process.env.AGENT_READY_MODEL || DEFAULT_MODEL;
}

function getOpenAIClient(): OpenAI {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    throw new Error(
      "Missing OPENAI_API_KEY. Add it to your .env file or environment.",
    );
  }

  cachedClient ??= new OpenAI({ apiKey });
  return cachedClient;
}

export async function generateText(input: {
  system: string;
  prompt: string;
}): Promise<string> {
  const client = getOpenAIClient();
  let response;

  try {
    response = await client.responses.create({
      model: getModel(),
      instructions: input.system,
      input: input.prompt,
    });
  } catch (error) {
    throw new Error(
      `OpenAI text generation failed: ${formatUnknownError(error)}`,
    );
  }

  const text = response.output_text;

  if (!text || text.trim().length === 0) {
    throw new Error("OpenAI returned an empty text response.");
  }

  return text;
}

export async function generateJson<T>(input: {
  system: string;
  prompt: string;
  schemaName: string;
  schema: z.ZodSchema<T>;
}): Promise<T> {
  const client = getOpenAIClient();
  const schemaName = normalizeSchemaName(input.schemaName);
  let response;

  try {
    response = await client.responses.parse({
      model: getModel(),
      input: [
        { role: "system", content: input.system },
        { role: "user", content: input.prompt },
      ],
      text: {
        format: zodTextFormat(input.schema, schemaName),
      },
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new Error(
        `Structured output validation failed for ${schemaName}: ${error.message}`,
      );
    }

    throw new Error(
      `OpenAI structured generation failed for ${schemaName}: ${formatUnknownError(
        error,
      )}`,
    );
  }

  if (!response.output_parsed) {
    throw new Error(`OpenAI returned no parsed ${schemaName} response.`);
  }

  try {
    return input.schema.parse(response.output_parsed);
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new Error(
        `Structured output validation failed for ${schemaName}: ${error.message}`,
      );
    }

    throw new Error(
      `OpenAI structured generation failed for ${schemaName}: ${formatUnknownError(
        error,
      )}`,
    );
  }
}

function normalizeSchemaName(schemaName: string): string {
  const normalized = schemaName
    .replace(/[^a-zA-Z0-9_-]/g, "_")
    .slice(0, 64);

  return normalized || "structured_response";
}

function formatUnknownError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}
