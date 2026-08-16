# Reviewer rubric: Operations

Judge whether the target provides a coherent source-to-runtime operational model.

Look specifically for:

1. Build/package path
- Is it clear how source becomes an executable/deployable/publishable artifact?

2. Runtime prerequisites and configuration
- Are important runtime prerequisites, environment configuration, and operational commands understandable?

3. Environment model
- Are meaningful environment distinctions described where present?

4. Delivery
Where present, are:
- CI/CD;
- release/versioning;
- package publishing;
- deployment;
explained coherently?

5. Runtime topology
- Are deployed processes/services/topology described where represented by the repository?

6. Operational configuration and secrets
- Is runtime injection/configuration explained where relevant?

7. Observability
Where present, are:
- health checks;
- metrics;
- logging pipelines;
- tracing;
- alerting;
covered appropriately?

8. Lifecycle
Where present, are:
- migrations;
- rollout;
- rollback;
- scaling;
- scheduled operational jobs;
- recovery;
covered?

9. Operations vs Architecture
Architecture owns in-process runtime composition.
Operations owns getting/configuring/deploying/observing/keeping it running.

10. Operations vs Interfaces
Operational providers should not be confused with product-facing external integrations.

11. Operations vs Data & State
Infrastructure/environment state belongs here.
Application/domain state does not.

12. Repository grounding
Flag invented deployment practices or operational assumptions not represented by the artifact.

Acceptance question:

"Could a future engineer understand how the repository becomes a running or released system and where operational configuration, deployment, observability, and recovery responsibilities live?"