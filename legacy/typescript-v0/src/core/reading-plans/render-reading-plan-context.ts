import type { ReadReadingPlanFilesResult } from "./read-reading-plan-files";

export interface RenderReadingPlanContextOptions {
  result: ReadReadingPlanFilesResult;
  includeDiagnostics?: boolean;
}

export function renderReadingPlanContext(
  options: RenderReadingPlanContextOptions,
): string {
  const lines: string[] = [
    `# Reading Plan Context: ${options.result.planKind}`,
    `Title: ${options.result.title}`,
    `Target memory file: ${options.result.targetMemoryFile}`,
    `Purpose: ${options.result.purpose}`,
    `Plan budget: maxFiles=${options.result.budget.maxFiles}, estimatedBytes=${options.result.budget.estimatedBytes}, truncated=${options.result.budget.truncated ? "yes" : "no"}`,
    `Agent focus: ${options.result.inputStrategy.agentFocus}`,
  ];

  if (options.result.inputStrategy.shouldAnswer.length > 0) {
    lines.push("Should answer:");
    for (const item of options.result.inputStrategy.shouldAnswer) {
      lines.push(`- ${item}`);
    }
  }

  if (options.result.inputStrategy.shouldAvoid.length > 0) {
    lines.push("Should avoid:");
    for (const item of options.result.inputStrategy.shouldAvoid) {
      lines.push(`- ${item}`);
    }
  }

  if (options.result.warnings.length > 0) {
    lines.push("Plan warnings:");
    for (const warning of options.result.warnings) {
      lines.push(
        `- [${warning.severity}] ${warning.code}: ${warning.message}`,
      );
    }
  }

  if (options.includeDiagnostics && options.result.diagnostics.length > 0) {
    lines.push("## Diagnostics");
    for (const diagnostic of options.result.diagnostics) {
      lines.push(renderDiagnostic(diagnostic));
    }
  }

  for (const batch of options.result.batches) {
    lines.push(`## Batch ${batch.order}: ${batch.title}`);
    lines.push(`Batch ID: ${batch.id}`);
    lines.push(`Purpose: ${batch.purpose}`);
    lines.push(`Selection rule: ${batch.selectionRule}`);
    lines.push(
      `Budget: maxFiles=${batch.budget.maxFiles}, estimatedBytes=${batch.budget.estimatedBytes}, truncated=${batch.budget.truncated ? "yes" : "no"}`,
    );

    for (const file of batch.files) {
      lines.push(`### File: ${file.path}`);
      lines.push(`Role in batch: ${file.roleInBatch}`);
      lines.push(`Reason: ${file.reason}`);
      lines.push(`Confidence: ${file.confidence}`);
      lines.push(`Estimated bytes: ${file.estimatedBytes}`);
      lines.push(`Bytes read: ${file.bytesRead}`);
      lines.push(`Truncated: ${file.truncated ? "yes" : "no"}`);
      lines.push("Evidence:");

      for (const evidence of file.evidence) {
        lines.push(`- ${evidence.source}: ${evidence.detail}`);
      }

      lines.push("Content:");
      lines.push(`<<<FILE_CONTENT_START ${file.path}>>>`);
      lines.push(file.content);
      lines.push(`<<<FILE_CONTENT_END ${file.path}>>>`);
      lines.push(`End of file: ${file.path}`);
    }
  }

  return `${lines.join("\n")}\n`;
}

function renderDiagnostic(
  diagnostic: ReadReadingPlanFilesResult["diagnostics"][number],
): string {
  const parts = [`- [${diagnostic.severity}] ${diagnostic.code}: ${diagnostic.message}`];

  if (diagnostic.batchId) {
    parts.push(`batch=${diagnostic.batchId}`);
  }

  if (diagnostic.path) {
    parts.push(`path=${diagnostic.path}`);
  }

  return parts.join(" | ");
}
