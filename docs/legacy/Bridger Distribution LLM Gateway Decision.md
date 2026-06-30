# Bridger — Distribution and Sponsored LLM Gateway Decision

## Status

Accepted for Bridger v0 / hackathon distribution.

This document locks the distribution and LLM API strategy for the hackathon version of Bridger.

The goal is to make Bridger easy for hackathon users to try with a simple `npx` command while avoiding the security and cost risks of distributing raw OpenAI API keys.

---

# 1. Decision summary

For Bridger v0, the distribution and LLM strategy is:

```txt
Hackathon users run Bridger through npx.
Bridger sponsors LLM usage for hackathon participants.
The CLI calls a lightweight Bridger Gateway.
The Gateway holds the OpenAI API key.
Users authenticate with a Bridger hackathon access token.
The Gateway enforces rate limits, quotas, model allowlists, and a kill switch.
```

Bridger v0 will support **one LLM provider only**:

```txt
OpenAI
```

Bridger v0 will not support Anthropic, BYOK, local models, OpenRouter, or multi-provider routing yet.

However, the internal CLI code should still isolate LLM calls behind a small provider interface so future BYOK and multi-provider support can be added later without rewriting memory agents or prompt generation.

---

# 2. Why this decision

## 2.1 Hackathon UX matters more than BYOK purity

For the hackathon, the product must work with minimal setup.

The expected user experience is:

```bash
npx bridger@latest init --fresh
```

Or, if the package name is scoped:

```bash
npx @bridger/cli@latest init --fresh
```

The user should not need to:

- create an OpenAI account;
- add billing details;
- understand model pricing;
- configure multiple provider options;
- debug API-key setup before seeing value.

The hackathon goal is adoption and product proof, not infrastructure purity.

## 2.2 Raw shared OpenAI keys are unacceptable

Bridger should not distribute a raw OpenAI API key in any of these forms:

```txt
npm package
README
.env example with real key
shared Discord / Slack message
embedded CLI default
frontend bundle
GitHub repo secret
```

Directly sharing a raw provider key creates avoidable risks:

- key leakage;
- unlimited use outside the hackathon;
- no per-user quota;
- no per-user revocation;
- no abuse control;
- no reliable kill switch;
- possible unexpected billing.

Therefore, sponsored mode must use a gateway.

## 2.3 The deterministic layer should still work without LLM access

Bridger should not hard-fail immediately when no LLM token is available.

The following commands or parts of commands should remain usable without sponsored access:

```bash
bridger inspect
bridger inspect --graph
bridger init --fresh --no-llm
```

And deterministic artifacts should remain API-key-free:

```txt
scan-result.json
repo-graph.json
graph-summary.json
codebase-map.json
reading-plans.json
```

This keeps Bridger useful and debuggable even if the sponsored gateway is unavailable.

---

# 3. Distribution strategy

## 3.1 Primary v0 distribution path

The primary distribution path is npm + npx:

```bash
npx bridger@latest init
npx bridger@latest init --fresh
npx bridger@latest prompt "Add feature X"
npx bridger@latest update
```

If the npm package is scoped, use:

```bash
npx @bridger/cli@latest init
npx @bridger/cli@latest init --fresh
npx @bridger/cli@latest prompt "Add feature X"
npx @bridger/cli@latest update
```

The exact npm package name should be finalized before publishing.

## 3.2 Important note on wording

The correct usage is not:

```bash
npx install bridger
```

The correct patterns are:

```bash
npx bridger@latest <command>
```

or local installation:

```bash
npm install -D bridger
npx bridger <command>
```

or global installation if desired:

```bash
npm install -g bridger
bridger <command>
```

For hackathon users, prefer the first option:

```bash
npx bridger@latest init --fresh
```

## 3.3 Package requirements

The npm package should provide a CLI binary named:

```txt
bridger
```

Package requirements:

- works through `npx` without global install;
- supports Node.js LTS;
- avoids native dependencies where possible;
- avoids postinstall scripts unless absolutely necessary;
- works on macOS, Linux, and Windows where feasible;
- ships compiled JavaScript, not raw TypeScript requiring local build;
- has a clear `bin` entry in `package.json`;
- exits cleanly with actionable errors;
- does not require a local OpenAI API key for hackathon sponsored mode.

Recommended package behavior:

```txt
npx bridger@latest init --fresh
  → downloads package
  → runs CLI
  → detects project
  → asks minimal questions
  → asks for hackathon token if LLM features are needed
  → writes .bridger files and AGENTS.md
```

## 3.4 First-run requirements

The first run should support four possible states.

### State A — User has no `.bridger` and has a hackathon token

Expected flow:

```txt
1. User runs npx bridger@latest init --fresh.
2. CLI asks for or validates hackathon token.
3. CLI creates .bridger.
4. CLI uses Gateway for LLM-assisted generation.
5. CLI writes starter memory, selected skills, and AGENTS.md.
```

### State B — User has no `.bridger` and no token

Expected flow:

```txt
1. CLI offers to continue in no-LLM mode.
2. CLI still creates config, deterministic artifacts, selected skills, and starter files.
3. CLI explains how to add hackathon access later.
```

### State C — User has existing `.bridger` and valid token

Expected flow:

```txt
1. CLI loads project state.
2. CLI uses Gateway for prompt/update/memory operations.
3. CLI refreshes artifacts and outputs.
```

### State D — User has existing `.bridger` and expired token

Expected flow:

```txt
1. CLI fails LLM operations clearly.
2. CLI does not corrupt .bridger state.
3. CLI still allows deterministic inspect commands.
```

---

# 4. CLI authentication model

## 4.1 Token type

Use opaque Bridger hackathon access tokens.

Example format:

```txt
brdg_hk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The token is not an OpenAI key.

It is only a Bridger access token that authorizes the CLI to call the Bridger Gateway.

## 4.2 Token storage

The token should be stored outside the repository.

Recommended location:

```txt
~/.config/bridger/auth.json
```

On Windows, use the appropriate user config directory equivalent.

The token should not be stored in:

```txt
.bridger/config.json
.env
AGENTS.md
Git-tracked files
```

`.bridger/config.json` may store non-secret provider configuration:

```json
{
  "llm": {
    "provider": "bridger-sponsored",
    "modelProfile": "balanced"
  }
}
```

But it must not store the secret token.

## 4.3 Auth command

Add a simple command:

```bash
bridger auth
```

Expected behavior:

```txt
1. Ask user to paste their Bridger hackathon token.
2. Call Gateway validation endpoint.
3. Store token locally if valid.
4. Print success or actionable failure.
```

Optional convenience:

```bash
bridger auth --token brdg_hk_xxx
```

Use this only if it does not leak tokens in logs or shell history during demos.

## 4.4 Auth during init

During `init` or `init --fresh`, if an LLM call is required and no token exists, show:

```txt
Bridger hackathon sponsored mode requires an access token.

Choose:
1. Enter Bridger hackathon token
2. Continue without LLM assistance
3. Exit
```

Default recommendation for hackathon users should be option 1.

---

# 5. Lightweight Gateway architecture

## 5.1 High-level architecture

```txt
Bridger CLI
  ↓ HTTPS
Bridger Gateway
  ↓ HTTPS
OpenAI API
```

The CLI never calls OpenAI directly in sponsored mode.

The Gateway owns:

- OpenAI API key;
- token validation;
- model selection;
- request validation;
- rate limiting;
- quota enforcement;
- usage logging;
- kill switch.

## 5.2 Most lightweight recommended stack

Recommended v0 implementation:

```txt
Runtime: Node.js / TypeScript
HTTP framework: Hono or Fastify
Hosting: Vercel, Render, Fly.io, or Railway
Rate limit store: Upstash Redis
Provider: OpenAI
```

The most lightweight practical setup is:

```txt
Hono or Fastify API
+ Upstash Redis
+ OpenAI SDK or direct fetch
+ Vercel or Render deployment
```

## 5.3 Why not a full backend platform

The v0 Gateway should not become a SaaS backend.

Avoid for v0:

- user accounts;
- OAuth;
- billing;
- organization management;
- dashboard;
- admin UI;
- complex analytics;
- multi-provider routing;
- persistent prompt storage;
- GitHub integration.

The Gateway exists only to safely sponsor OpenAI usage.

---

# 6. Gateway endpoints

## 6.1 Required endpoints

Minimum endpoints:

```txt
POST /v1/auth/validate
POST /v1/llm/generate
GET  /v1/usage
GET  /health
```

Optional endpoint:

```txt
POST /v1/auth/redeem
```

Only add `/v1/auth/redeem` if we want users to redeem short event codes into long opaque tokens.

## 6.2 `POST /v1/auth/validate`

Purpose:

Validate a hackathon token before storing it locally.

Input:

```txt
Authorization: Bearer brdg_hk_xxx
```

Output:

```json
{
  "ok": true,
  "plan": "hackathon",
  "expiresAt": "2026-07-01T00:00:00.000Z",
  "limits": {
    "requestsPerDay": 50,
    "requestsPerMinute": 10
  }
}
```

Failure cases:

```txt
401 invalid token
403 revoked token
410 expired token
429 validation rate limit exceeded
```

## 6.3 `POST /v1/llm/generate`

Purpose:

Generate text through OpenAI with quota enforcement.

Request metadata should include:

```txt
operation
modelProfile
bridgerVersion
repoHash
commandName
```

Allowed operations:

```txt
fresh_init
memory_agent
agents_export
prompt_generation
update
```

Allowed model profiles:

```txt
cheap
balanced
quality
```

For hackathon v0, `quality` can be disabled or mapped to the same model as `balanced` to control cost.

The Gateway should choose the actual OpenAI model. The CLI should not be able to request arbitrary model names.

## 6.4 `GET /v1/usage`

Purpose:

Let the CLI show remaining quota.

Output should include:

```txt
requests used today
request limit per day
estimated or actual tokens used today
token limit per day
expiration date
```

This can be simple for v0.

## 6.5 `GET /health`

Purpose:

Deployment and CLI health check.

Output:

```json
{
  "ok": true
}
```

---

# 7. Gateway token and quota model

## 7.1 Token records

For v0, tokens can be generated manually and stored in a small database or Redis.

Recommended token record fields:

```txt
token_id
token_hash
status: active | revoked
plan: hackathon
created_at
expires_at
requests_per_minute
requests_per_day
input_tokens_per_day
output_tokens_per_day
max_concurrent_requests
notes
```

Store token hashes, not raw tokens.

## 7.2 Rate limiting

Recommended per-token limits for v0:

```txt
requests_per_minute: 10
requests_per_day: 50
max_concurrent_requests: 1 or 2
```

Recommended token budgets:

```txt
input_tokens_per_day: 500k to 1M
output_tokens_per_day: 100k to 250k
```

Exact numbers should be adjusted after testing memory generation cost on representative repos.

## 7.3 Global limits

The Gateway should also enforce global limits:

```txt
global_requests_per_minute
global_tokens_per_day
global_kill_switch
```

These protect the sponsor budget even if individual limits fail.

## 7.4 Redis key examples

Possible Upstash Redis keys:

```txt
rl:{token_id}:rpm:{minute}
rl:{token_id}:rpd:{date}
usage:{token_id}:input_tokens:{date}
usage:{token_id}:output_tokens:{date}
concurrent:{token_id}
global:rpm:{minute}
global:tokens:{date}
kill_switch
```

For the lightest v0, some of these can be combined.

The minimum required counters are:

```txt
per-token requests per minute
per-token requests per day
per-token daily token usage
global daily token usage
kill switch
```

---

# 8. OpenAI model policy

## 8.1 Model profiles

Do not expose arbitrary OpenAI model choice in the hackathon CLI.

Expose simple profiles:

```txt
cheap
balanced
quality
```

The Gateway maps profiles to actual OpenAI models.

For v0:

```txt
cheap
  used for small transformations, fresh init refinements, simple prompt generation

balanced
  default for memory agents, AGENTS.md generation, update, and prompt generation

quality
  optional; can be disabled or mapped to balanced for cost control
```

## 8.2 Max output tokens

Each operation should have a maximum output budget.

Example policy:

```txt
fresh_init: lower max output
memory_agent: medium max output
agents_export: medium max output
prompt_generation: medium max output
update: medium max output
```

The CLI should not be able to request unlimited output.

## 8.3 Request size controls

The Gateway should reject very large inputs before calling OpenAI.

Enforce:

```txt
max request body size
max rendered prompt characters
max files per agent context
max batches per request
max output tokens
```

The CLI should also perform client-side checks, but the Gateway is the source of truth.

---

# 9. Privacy and data handling

## 9.1 Important disclosure

Sponsored mode sends selected Bridger prompts and repository context to the Bridger Gateway, which forwards them to OpenAI.

This should be disclosed in the README and CLI.

Suggested wording:

```txt
Hackathon sponsored mode routes selected Bridger prompts and repository context through the Bridger Gateway so we can sponsor OpenAI usage. Do not use sponsored mode for private or sensitive repositories. Future BYOK/local modes will allow direct provider usage without routing through Bridger infrastructure.
```

## 9.2 Logging policy

By default, the Gateway should not persist full prompts, full source snippets, or generated memory content.

Log only operational metadata:

```txt
token_id
operation
model
status
latency
input token count
output token count
created_at
bridger version
repo hash
error code
```

This is enough for cost control and debugging.

## 9.3 Sensitive repo warning

The CLI should warn users:

```txt
Do not use sponsored hackathon mode with private, proprietary, regulated, or sensitive repositories.
```

For hackathon demos, this is acceptable.

---

# 10. CLI LLM provider interface

Even though v0 supports only sponsored OpenAI through the Gateway, Bridger should avoid hardcoding gateway calls throughout the codebase.

Use a small internal abstraction:

```txt
LLMClient.generateText(request) → response
```

The v0 implementation can be:

```txt
SponsoredOpenAIGatewayClient
```

Future implementations can be:

```txt
OpenAIByokClient
AnthropicByokClient
LocalModelClient
```

The memory agents, AGENTS.md exporter, and prompt generator should depend on the interface, not on direct Gateway HTTP calls.

---

# 11. Error behavior

The CLI should provide clear errors.

## Invalid token

```txt
Invalid Bridger hackathon token.
Run `bridger auth` with a valid token or continue with `--no-llm`.
```

## Expired token

```txt
Your Bridger hackathon token has expired.
Deterministic commands still work, but LLM-assisted generation is disabled.
```

## Rate limit reached

```txt
Hackathon usage limit reached for this token.
Try again later or continue with deterministic-only mode.
```

## Gateway unavailable

```txt
Bridger Gateway is temporarily unavailable.
No repository files were changed. You can still run `bridger inspect --graph`.
```

## Context too large

```txt
The selected repository context is too large for sponsored mode.
Try running `bridger inspect --graph` to inspect selected context, or reduce files included in the operation.
```

---

# 12. Deployment strategy

## 12.1 Minimal deployment

Recommended v0 deployment:

```txt
One small API service
One Redis instance
One OpenAI API key stored as deployment secret
One environment variable for kill switch
```

Suggested environment variables:

```txt
OPENAI_API_KEY
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
BRIDGER_GATEWAY_ADMIN_SECRET
BRIDGER_GATEWAY_KILL_SWITCH
BRIDGER_ALLOWED_ORIGINS
BRIDGER_DEFAULT_MODEL_CHEAP
BRIDGER_DEFAULT_MODEL_BALANCED
BRIDGER_DEFAULT_MODEL_QUALITY
```

## 12.2 Hosting option A — Vercel

Pros:

- very fast to deploy;
- easy TypeScript serverless functions;
- simple environment variables;
- good enough for hackathon traffic.

Cons:

- serverless timeouts may matter for large generations;
- streaming can be slightly more complex;
- not ideal for long-running requests.

Good choice if operations are short and bounded.

## 12.3 Hosting option B — Render

Pros:

- simple long-running Node server;
- easier request handling;
- predictable deployment;
- matches prior project experience.

Cons:

- slightly slower cold starts depending on plan;
- needs service management.

Good choice if memory-agent calls may run longer.

## 12.4 Recommended v0 choice

For the most lightweight reliable implementation, use:

```txt
Render Web Service
+ Hono/Fastify Node server
+ Upstash Redis
```

This avoids serverless timeout surprises and keeps the backend simple.

If speed of deployment matters more than long-running request reliability, Vercel is also acceptable.

---

# 13. Security requirements

Minimum v0 security requirements:

- never expose raw OpenAI API key to the CLI;
- never ship provider key in npm package;
- require HTTPS;
- validate all request bodies;
- enforce operation allowlist;
- enforce model profile allowlist;
- enforce max request size;
- enforce per-token quotas;
- enforce global quota;
- support kill switch;
- store token hashes, not raw tokens;
- do not log full repo content by default;
- make tokens expire shortly after hackathon;
- allow token revocation.

---

# 14. Implementation phases

## Phase 1 — CLI distribution readiness

Build:

- npm package binary;
- `npx bridger@latest` command behavior;
- first-run output;
- `.bridger` layout;
- basic `bridger auth` command;
- local token storage;
- sponsored LLM client interface.

Definition of done:

- a user can run the CLI from `npx`;
- the CLI can store and validate a hackathon token;
- deterministic commands work without token.

## Phase 2 — Minimal Gateway

Build:

- Gateway service;
- OpenAI call wrapper;
- `/v1/auth/validate`;
- `/v1/llm/generate`;
- `/health`;
- manual token list;
- token hashing;
- basic rate limiting;
- basic usage logging.

Definition of done:

- CLI can call Gateway;
- Gateway calls OpenAI;
- invalid/expired tokens are rejected;
- per-token request limits work;
- raw OpenAI key never leaves server.

## Phase 3 — Quotas and safety

Build:

- daily request quotas;
- daily token quotas;
- global token budget;
- kill switch;
- context-size rejection;
- clean 401/403/429/413/503 errors.

Definition of done:

- Gateway has real cost controls;
- one bad token cannot consume all budget;
- the team can shut down sponsored usage immediately.

## Phase 4 — Hackathon polish

Build:

- README distribution instructions;
- token handout process;
- demo tokens;
- usage command;
- clean CLI copy;
- troubleshooting section.

Definition of done:

- participants can run Bridger without asking for setup help;
- common errors are self-explanatory;
- sponsored usage works reliably during the event.

---

# 15. Token handout process

For hackathon v0, use pre-generated tokens.

Recommended process:

```txt
1. Generate 50–200 opaque tokens.
2. Store hashed tokens in Gateway token store.
3. Print or distribute tokens through event channel.
4. Set expiration shortly after the hackathon.
5. Monitor aggregate usage.
6. Revoke tokens if needed.
```

Possible token allocation:

```txt
1 token per participant
or
1 token per team
```

Recommended:

```txt
1 token per team
```

This reduces token management overhead and aligns usage with actual hackathon projects.

---

# 16. README requirements

The README should include a short hackathon quickstart.

Minimum content:

```txt
1. Install/run through npx.
2. Authenticate with Bridger hackathon token.
3. Run init --fresh.
4. Generate AGENTS.md.
5. Run bridger prompt.
6. Run bridger update after coding.
7. Explain privacy note for sponsored mode.
8. Explain deterministic no-LLM fallback.
```

Example quickstart:

```bash
npx bridger@latest auth
npx bridger@latest init --fresh
npx bridger@latest prompt "Build the first feature"
npx bridger@latest update
```

---

# 17. Non-goals for v0

The following are explicitly out of scope for the hackathon version:

- Anthropic support;
- OpenAI BYOK mode;
- local model support;
- OpenRouter support;
- billing;
- user accounts;
- SaaS dashboard;
- GitHub login;
- OAuth;
- advanced admin panel;
- persistent prompt storage;
- storing full repo contents;
- marketplace for skills;
- enterprise self-hosting;
- multi-provider model router;
- complex cost analytics.

These can be added later if the CLI proves useful.

---

# 18. Definition of done

This distribution and gateway decision is implemented when:

- Bridger can be run through `npx` from a clean repo;
- users can authenticate with a Bridger hackathon token;
- no raw OpenAI key is distributed to users;
- the CLI can call the Gateway for LLM-assisted operations;
- the Gateway validates tokens;
- the Gateway enforces per-token and global limits;
- the Gateway calls OpenAI using a server-side key;
- deterministic commands work without LLM access;
- sponsored mode has clear privacy disclosure;
- README explains the hackathon flow;
- tokens can expire and be revoked;
- the team has a kill switch;
- the v0 hackathon demo can run without users creating OpenAI accounts.

---

# 19. Final locked decision

For Bridger v0, the hackathon distribution strategy is:

```txt
npx-first CLI distribution
+ sponsored OpenAI usage
+ Bridger hackathon access tokens
+ lightweight Bridger Gateway
+ strict rate limits and quotas
+ no raw API key distribution
+ deterministic no-LLM fallback
```

This keeps the hackathon onboarding simple while preserving a safe path toward the future open-source model:

```txt
v0 hackathon:
  sponsored OpenAI Gateway

post-hackathon:
  BYOK OpenAI
  Anthropic
  local models
  optional hosted/team gateway
```

The v0 priority is not provider flexibility.

The v0 priority is:

```txt
A participant can run Bridger with npx, receive useful context and prompts, and see better coding-agent output without setting up their own LLM account.
```
