# Target: Repository

## Objective

Build the canonical shallow orientation layer for this repository.

Answer:

"What is this repository, what major things does it contain, and where should someone go for deeper understanding?"

Your job is to give a new engineer or coding agent the terrain of the repository without duplicating the deeper specialist memory targets.

## Abstraction level

Stay deliberately shallow.

Focus on:
- what exists;
- where it is;
- what its broad responsibility is;
- where deeper understanding should be sought.

Do not deeply explain how systems work.

## Investigate

Resolve the following where applicable:

- repository purpose and identity;
- major languages, frameworks, and toolchains;
- repository shape and top-level organization;
- major applications, services, packages, libraries, or workspaces;
- high-level responsibility of each major area;
- principal entry surfaces;
- important source, configuration, documentation, generated, and vendored regions;
- major monorepo/workspace boundaries;
- major generated-code/client regions;
- important developer-facing commands useful for orientation;
- unusual repository organization that a new contributor must understand.

## Do not own

Do not deeply document:
- runtime architecture;
- business/domain rules;
- state and persistence;
- API/integration contracts;
- testing strategy;
- coding conventions;
- deployment/operations;
- UI/design decisions.

Those may be briefly mentioned to orient the reader.

## Investigation guidance

Begin with deterministic inventory, manifests, workspace/package declarations, top-level documentation, graph structure, and major entry surfaces.

Use deeper source inspection only when needed to correctly identify the responsibility of an important repository area.

Do not turn this target into a file-tree dump.

## Completion obligations

You must meaningfully resolve:

- repository purpose/orientation;
- major languages/frameworks/toolchain;
- major applications/packages/workspaces;
- top-level source organization;
- principal entry surfaces;
- important generated/vendor/special regions where present;
- orientation toward deeper specialist knowledge.

The result should let a new engineer quickly answer:

"What is this repo, what are its major pieces, where should I start, and where should I look next?"