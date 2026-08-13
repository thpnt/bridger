# Reviewer rubric: Repository

Judge whether the target succeeds as the Repository Brain's shallow orientation layer.

The artifact should make it easy to understand:
- what the repository is;
- its major applications/packages/workspaces;
- its major languages/frameworks/toolchain;
- its top-level organization;
- important entry surfaces;
- important generated/vendor/special regions;
- where deeper knowledge should be sought.

Look specifically for:

1. Orientation quality
- Does the reader quickly understand the repository's purpose and terrain?
- Are the major areas differentiated by broad responsibility?

2. Appropriate shallowness
- Does the target remain one abstraction level above specialist knowledge?
- Flag deep runtime, business, persistence, integration, testing, operations, or design explanations that duplicate specialist ownership.

3. Navigability
- Is it clear where important categories of code live?
- Does the artifact help a new engineer decide where to investigate next?

4. Synthesis over inventory
- Flag raw tree/file/package listings that are not synthesized into an understandable repository map.

5. Terminology
- Is high-level terminology coherent and suitable to serve as the fleet's orientation vocabulary?

Acceptance question:

"Could a new engineer or coding agent use this target to understand what the repository contains and where to go next without mistaking it for the detailed architecture documentation?"