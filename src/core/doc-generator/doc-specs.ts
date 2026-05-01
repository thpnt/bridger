import { GENERATED_DOC_FILENAMES } from "./doc-filenames";
import type { KnowledgeDocKey, KnowledgeDocSpec } from "./doc-types";

const REPO_ANALYSIS_REQUIRED_SECTIONS = [
  "## Project overview",
  "## Detected stack",
  "## File and folder evidence",
  "## Important files",
  "## Observed structure",
  "## Observed domains",
  "## Assumptions",
  "## Unknowns",
] as const;

const ARCHITECTURE_REQUIRED_SECTIONS = [
  "## Project overview",
  "## Detected stack",
  "## App structure",
  "## Core domains",
  "## Important folders",
  "## Data flow assumptions",
  "## Commands",
  "## Risky areas",
  "## Unknowns",
] as const;

const BUSINESS_LOGIC_REQUIRED_SECTIONS = [
  "## Product/domain overview",
  "## Observed domain concepts",
  "## Observed entities and models",
  "## Observed business rules",
  "## Observed workflows",
  "## Data ownership and persistence",
  "## External integrations",
  "## Assumptions",
  "## Unknowns",
  "## Evidence map",
] as const;

const CONVENTIONS_REQUIRED_SECTIONS = [
  "## TypeScript conventions",
  "## Component conventions",
  "## Server/client boundary conventions",
  "## Validation conventions",
  "## Styling conventions",
  "## Data access conventions",
  "## Testing conventions",
  "## Naming conventions",
  "## Observed conventions",
  "## Recommended conventions",
  "## Things agents should avoid",
  "## Unknowns",
] as const;

const TESTING_REQUIRED_SECTIONS = [
  "## Testing philosophy",
  "## Test types and when to use them",
  "## Unit testing conventions",
  "## Integration testing conventions",
  "## Regression testing conventions",
  "## Component and UI testing conventions",
  "## Manual QA expectations",
  "## Existing test evidence",
  "## Testing gaps and unknowns",
  "## Things agents should avoid",
] as const;

const AGENT_RULES_REQUIRED_SECTIONS = [
  "## Project overview",
  "## Commands",
  "## Rules for agents",
  "## Coding conventions",
  "## Business logic boundaries",
  "## Testing expectations",
  "## Risky areas",
  "## Task scoping rules",
  "## Files/folders to avoid unless explicitly requested",
  "## Unknowns",
] as const;

export const KNOWLEDGE_DOC_SPECS = {
  repoAnalysis: {
    key: "repoAnalysis",
    filename: GENERATED_DOC_FILENAMES.repoAnalysis,
    displayName: "Repo analysis",
    requiredSections: REPO_ANALYSIS_REQUIRED_SECTIONS,
  },
  architecture: {
    key: "architecture",
    filename: GENERATED_DOC_FILENAMES.architecture,
    displayName: "Architecture",
    requiredSections: ARCHITECTURE_REQUIRED_SECTIONS,
  },
  businessLogic: {
    key: "businessLogic",
    filename: GENERATED_DOC_FILENAMES.businessLogic,
    displayName: "Business logic",
    requiredSections: BUSINESS_LOGIC_REQUIRED_SECTIONS,
  },
  conventions: {
    key: "conventions",
    filename: GENERATED_DOC_FILENAMES.conventions,
    displayName: "Conventions",
    requiredSections: CONVENTIONS_REQUIRED_SECTIONS,
  },
  testing: {
    key: "testing",
    filename: GENERATED_DOC_FILENAMES.testing,
    displayName: "Testing",
    requiredSections: TESTING_REQUIRED_SECTIONS,
  },
  agentRules: {
    key: "agentRules",
    filename: GENERATED_DOC_FILENAMES.agentRules,
    displayName: "Agent rules",
    requiredSections: AGENT_RULES_REQUIRED_SECTIONS,
  },
} as const satisfies Record<KnowledgeDocKey, KnowledgeDocSpec>;

export const KNOWLEDGE_DOC_KEYS = [
  "repoAnalysis",
  "architecture",
  "businessLogic",
  "conventions",
  "testing",
  "agentRules",
] as const satisfies readonly KnowledgeDocKey[];

export type KnowledgeDocSpecs = typeof KNOWLEDGE_DOC_SPECS;
