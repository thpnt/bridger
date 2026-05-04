import { z } from "zod";

export const DependencyExtractorLanguageSchema = z.enum([
  "typescript-javascript",
  "python",
]);

export const DependencyExtractorSourceSchema = z.enum([
  "typescript-js-imports",
  "python-imports",
]);

export const ExtractedImportKindSchema = z.enum([
  "static",
  "dynamic",
  "require",
  "reexport",
]);

export const DependencyExtractionInputSchema = z.object({
  filePath: z.string().min(1),
  content: z.string(),
});

export const ExtractedImportSchema = z.object({
  specifier: z.string().min(1),
  kind: ExtractedImportKindSchema,
  source: DependencyExtractorSourceSchema,
  line: z.number().int().positive().optional(),
});

export type DependencyExtractorLanguage = z.infer<
  typeof DependencyExtractorLanguageSchema
>;

export type DependencyExtractorSource = z.infer<
  typeof DependencyExtractorSourceSchema
>;

export type ExtractedImportKind = z.infer<typeof ExtractedImportKindSchema>;

export type DependencyExtractionInput = z.infer<
  typeof DependencyExtractionInputSchema
>;

export type ExtractedImport = z.infer<typeof ExtractedImportSchema>;

export type DependencyExtractor = {
  language: DependencyExtractorLanguage;
  extensions: readonly string[];
  source: DependencyExtractorSource;
  extractImports(input: DependencyExtractionInput): ExtractedImport[];
};
