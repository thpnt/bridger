export function assertMarkdownSections(input: {
  markdown: string;
  requiredSections: readonly string[];
  documentName: string;
}): void {
  const missingSections = input.requiredSections.filter(
    (section) => !input.markdown.includes(section),
  );

  if (missingSections.length > 0) {
    throw new Error(
      `${input.documentName} is missing required sections: ${missingSections.join(", ")}`,
    );
  }
}
