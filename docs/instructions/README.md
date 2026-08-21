# Bridger Memory Agent Fleet instruction audit

This is a discovery/extraction audit of the current Memory Agent Fleet instruction surface. Static prompts, YAML contracts, and relevant source excerpts are reproduced verbatim in the linked volumes.

- [01 — shared worker prompt and catalog](./01-shared-worker-and-catalog.md)
- [02 — per-target worker packs and complete TargetDefinitions](./02-target-worker-packs-and-definitions.md)
- [03 — WorkerContext, provider request, profiles, permissions, and tools](./03-worker-context-provider-and-tools.md)
- [04 — shared reviewer prompt, rubrics, and target-review request](./04-reviewer-prompts-and-target-review.md)
- [05 — fleet reconciliation and locked catalog comparison](./05-fleet-reconciliation-and-locked-catalog.md)

Relevant runtime source inventory: `src/repository_brain/harness.py`; `src/memory/default-targets/`; `src/prompts/`; `src/models/memory.py`; `src/models/hydration.py`; `src/memory/hydration.py`; `src/memory/worker_cycle.py`; `src/memory/worker_tools.py`; `src/navigation/tools.py`; `src/models/review.py`; `src/memory/review.py`; `src/models/fleet_review.py`; `src/memory/fleet_review.py`.

Locked documentation inspected: `docs/bridger/product-system-design/bridger_memory_agent_design.md`; `docs/bridger/product-system-design/bridger_memory_target_catalog.md`; `docs/bridger/agentic-contracts/hydrating.md`; `docs/bridger/agentic-contracts/worker-cycle.md`; `docs/bridger/agentic-contracts/review.md`; `docs/bridger/agentic-contracts/fleet_conciliation_acceptance.md`.

