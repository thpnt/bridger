# Designing a State-of-the-Art Agentic Repository Discovery Harness

The strongest lesson from the current coding-agent landscape is that “the model” is only part of the system. The highest-performing public harnesses now combine selective repository context, strong search and navigation tools, explicit planning or subagent separation, and bounded execution environments. That matters for your use case because repository discovery is not the same task as issue resolution: it is closer to the “information gathering” slice of modern software-agent evaluation than to patch generation alone. Mid-2026 public benchmarks reflect this shift. The official SWE-bench leaderboard still concentrates on issue resolution, while the OpenHands Index expands evaluation across issue resolution, greenfield development, frontend work, testing, and information gathering. citeturn1search3turn10view0turn10view1

The core design implication is straightforward: your discovery harness should not be a thin wrapper around “read some files and summarise”. It should behave like a senior engineer entering an unfamiliar codebase: form an initial map, identify architectural areas, use symbolic navigation and targeted reading to deepen understanding, maintain hypotheses and evidence, and emit a structured knowledge graph plus reading plan for downstream memory compilers. The most useful public patterns for that today come from Aider, Claude Code, Codex CLI, OpenHands, SWE-agent and mini-SWE-agent, and the research-oriented AutoCodeRover. citeturn8view0turn8view5turn8view6turn9view0turn9view9turn15view1turn8view9

## What the strongest harnesses are teaching us

Across the leading public systems, four patterns recur. First, exploration is increasingly separated from editing. Claude Code ships built-in read-only Explore and Plan subagents; OpenHands documents a two-phase workflow with a read-only planning agent followed by an execution agent; Aider distinguishes planning-style interaction from code-editing via its `ask` and `architect` modes. This separation is highly relevant to your discovery step, because discovery should be predominantly read-only and should not pay the cognitive or safety cost of edit-capable loops until later phases. citeturn8view5turn8view8turn8view1

Secondly, the best harnesses avoid dumping the whole repo into context. Aider’s repository map gives the model a compact whole-repo view of files, key symbols, and signatures; Codex skills use progressive disclosure so only short skill descriptions are loaded initially and full instructions are loaded only when selected; OpenHands recommends skills in the AgentSkills format partly to avoid permanently bloating prompt context, and it includes a condenser to summarise older history once a threshold is crossed. In other words, SOTA harnesses increasingly treat context as a retrieval problem, not as a bulk-upload problem. citeturn8view0turn11view0turn8view4turn8view7turn9view8

Thirdly, tooling is converging on a fairly stable core: file read/search, symbol-aware navigation, shell execution, and external tool connectivity through MCP or equivalent extensibility. Claude Code’s built-in categories span file operations, search, execution, web, and code intelligence; Codex supports MCP server integration, AGENTS.md, skills, hooks, and sandboxed command execution; OpenHands exposes tools, contexts, condensers, delegation, and serialisable agent settings as composable parts of one agent runtime. For harness design, that means bespoke one-off tools are usually less valuable than a clean, strongly typed tool contract around a narrow set of high-leverage capabilities. citeturn9view1turn14view3turn14view4turn5search0turn9view6

Finally, the most mature harnesses now treat safety and autonomy as co-designed concerns. Codex combines sandbox boundaries with approval policies; Claude Code exposes permission modes and path-based allow/ask/deny rules; OpenHands bakes security analysis into the reasoning-action loop and supports isolated workspaces through its agent server and Docker workspace patterns. For your discovery harness, this particularly supports a default posture of read-only autonomy, with controlled escalation to tests or build commands only when needed to verify architecture or conventions. citeturn14view0turn14view1turn12view4turn9view3turn8view6turn5search3

## What each harness contributes to a repository-discovery design

**Aider** is the clearest public example of whole-repo structural context done cheaply. Its repo map gives the model a repository-wide index of important classes, functions, definitions, and signatures, and Aider’s own usage guidance repeatedly warns against adding too many files directly to the working context. Instead, the repo map acts as a global orienting layer, while specific files are pulled in selectively as needed. For your use case, this argues strongly for a first-class “repo map” artefact rather than raw tree dumps or naive chunk retrieval. citeturn8view0turn18view0turn18view1

Aider also contributes a useful division of labour. In `architect` mode, one model proposes changes and a different editor model translates those into concrete edits. Even though your discovery phase is not editing-focused, the underlying pattern is still valuable: separate broad reasoning about “what area matters and how should I investigate it?” from narrower operational work such as symbol expansion, reading concrete files, or extracting conventions. That split can reduce context contamination and make discovery traces easier to audit. citeturn8view1

**Claude Code** contributes the most mature public design for exploration subagents. Its built-in Explore subagent is a fast, read-only agent specifically optimised for file discovery, code search, and codebase exploration, while its Plan subagent is used during plan mode to gather repository context before synthesis. Claude Code also exposes strong code-intelligence affordances through LSP integration, including definitions, references, symbol search, implementations, and call hierarchies. For a discovery harness, that combination is extremely instructive: a cheap, bounded exploration worker backed by language-server semantics is closer to senior-engineer discovery behaviour than relying on raw grep alone. citeturn8view5turn19view0

Claude Code’s memory model is the other major lesson. `CLAUDE.md` files and auto memory provide persistent, scoped instructions and accumulated learnings across sessions; `/init` can even generate a starting project memory file from repo analysis. For your harness, this suggests that discovery should produce two kinds of outputs: durable project instructions and conventions that future coding agents should load at start-up, and richer evidence-backed discovery artefacts that memory compilers can transform later. Those are related, but they should not be conflated. citeturn12view0

**Codex CLI** contributes the cleanest public contract for project guidance and extensibility. It reads `AGENTS.md` files before doing any work, discovers them hierarchically from global scope down to project and subdirectory scopes, and supports skills with progressive disclosure so the initial skills list stays small. It also supports hooks that can log, validate, summarise, or create persistent memories during the agent lifecycle, and it can run as an MCP server so larger deterministic multi-agent workflows can orchestrate it externally. For your harness, the main takeaways are hierarchical guidance, optional workflow skills, and lifecycle hooks that can turn an exploratory run into a structured output pipeline. citeturn8view3turn8view4turn14view4turn14view5

Codex’s sandbox and approval model is also a useful reference. By default it runs without network access, with workspace-bounded writes and approval prompts for leaving the sandbox or using the network. That is a strong fit for discovery: allow read/search/symbol navigation freely, allow local non-destructive commands in the workspace, require explicit policy or approval for anything riskier. citeturn14view0turn14view1

**OpenHands** contributes the strongest public architecture for building your own harness rather than merely using one. Its SDK is stateless and event-driven, with conversation state as the single mutable source of truth. Agent configuration is serialisable as data, not just imperative code; sub-agents can be spawned with independent contexts and run in parallel; and history can be condensed when sessions grow long. OpenHands also explicitly documents a read-only planning-agent workflow. For your use case, this is almost a blueprint for implementation: a custom discovery agent should be a serialisable configuration plus a replayable event log, not an opaque session transcript. citeturn8view6turn9view5turn9view6turn9view7turn9view8turn8view8

OpenHands’ benchmark work matters too. The OpenHands Index was designed because issue-only benchmarks were too narrow; it includes information gathering as a first-class category and argues that software engineering involves more than single-repo bug fixing. That aligns closely with your objective. A discovery harness should therefore optimise for structured understanding, navigability, and evidence quality, not just for “can it produce a patch”. citeturn10view0turn10view1

**SWE-agent** remains important because it made the “agent-computer interface” idea explicit. Its paper argues that software agents need interfaces designed for their operating style, and identifies search/navigation, file viewing, file editing, and context management as key ACI components. That framing is still useful in 2026: your harness is best seen as an ACI for repository understanding, not just as a prompt template. citeturn16search0turn16search1

**mini-SWE-agent** is the counterweight. Its maintainers explicitly argue that modern LMs often need less scaffold than earlier systems, and its public design is radically simple: bash-only, linear message history, and subprocess-isolated command execution, while still reporting over 74% on SWE-bench Verified. The lesson is not “use bash only for everything”; it is that you should be suspicious of unnecessary orchestration. If a complex harness feature does not obviously improve discovery quality, evidence traceability, or safety, it probably should not exist. citeturn15view1

**AutoCodeRover** adds one research pattern that is especially relevant for repository understanding: it treats a project as structured program entities rather than merely a bag of files. It uses AST-level program representation and iterative code search, and it sharpens context further with test-based fault localisation when tests are available. Even though your problem is broader than bug fixing, the key design implication generalises well: discovery should reason over symbols, interfaces, and structural relations, not just files and chunks. citeturn8view9

## Defining the repository-discovery use case properly

Your use case is not “solve a specific issue in a repo”. It is “build a reliable, navigable understanding of a codebase so later specialist agents can compile durable memory by topic”. That changes what success looks like. A successful discovery run should recover architectural areas, entry points, key execution paths, interfaces between areas, conventions and invariants, and the unresolved questions a senior engineer would still want checked before coding. It should also preserve evidence for each conclusion, because downstream memory compilers and humans need to trust where the knowledge came from. This framing is consistent with the way current harnesses split planning from execution and with the broader task families in the OpenHands Index. citeturn8view5turn8view8turn10view0

I would therefore define the discovery harness as a **read-mostly, evidence-producing, graph-building exploration runtime**. “Read-mostly” means its default tools are non-destructive. “Evidence-producing” means every conclusion carries source references to files, symbols, commands, or docs. “Graph-building” means the primary unit is not the individual file but the **codebase area**: a coherent cluster such as an application surface, domain module, shared library, service boundary, data-access slice, platform layer, or build-and-release subsystem. That emphasis follows from Aider’s repo-map abstraction, Claude’s symbol-aware LSP tools, and AutoCodeRover’s program-structure-first approach. citeturn8view0turn19view0turn8view9

A second implication is that the output should not be a deterministic file-by-file batch order unless you need that for one specific downstream compiler. Current harness patterns point in the opposite direction. They favour compact global views, selective drill-down, independent subagent contexts, and symbol-level navigation. I therefore think you should treat batch ordering as a derived view, not as the canonical output. The canonical output should be a navigable graph of codebase areas, annotated with files, symbols, evidence, confidence, dependencies, and suggested reading sequences. That is an inference, but it is strongly supported by the public direction of Aider, Claude Code, OpenHands, and AutoCodeRover. citeturn8view0turn8view5turn9view7turn8view9

A third implication is model allocation. Claude’s Explore subagent uses a cheaper, faster model for read-only search; OpenHands explicitly notes the value of switching models across planning, execution, and review; Codex and Claude both support structured guidance and subagents rather than a single undifferentiated loop. For discovery, that suggests a tiered setup: a cheap exploration model for wide scans, a stronger synthesis model for area summaries and architecture hypotheses, and possibly a third verifier step for convention extraction or uncertainty resolution. citeturn8view5turn10view0

## The context contract the harness should provide

The harness should start every run with a **layered context contract**, not a raw text blob. The first layer is a repository substrate: root tree, package manifests, lockfiles, build files, CI pipelines, deployment/config directories, top-level docs, ADRs if present, and any `AGENTS.md`, `CLAUDE.md`, or equivalent project instruction files. Codex treats `AGENTS.md` as pre-work guidance and resolves it hierarchically; Claude does the same with `CLAUDE.md` and path-scoped rules; OpenHands documents AGENTS content and skills as prompt-level repo context. Those mechanisms show that project guidance should be part of the harness contract, not something the model is expected to discover by luck. citeturn8view3turn12view0turn8view7turn10view2

The second layer should be a **structural index substrate**. At minimum, that means a repo map of files and key symbols; ideally, it also includes definitions, references, imports/exports, call hierarchies, implementations, and coarse dependency relations. Aider shows the value of a compact repo map; Claude’s LSP integration shows the value of definition/reference/call-hierarchy tooling; AutoCodeRover demonstrates that treating the repo as program structure materially improves search and localisation quality. For a modern discovery harness, this layer is not optional. citeturn8view0turn19view0turn8view9

The third layer should be a **task brief substrate**. Every discovery run should know its objective, scope, budget, and output schema up front: whether it is onboarding a whole monorepo, focusing on one service, or refreshing knowledge after a release; how much time and token budget it is allowed; whether command execution is allowed; and what downstream memory compilers expect. OpenHands’ serialisable agent settings are a good reference point here: the harness should treat configuration as explicit data, not hidden prompt text. citeturn9view6

The fourth layer should be **progressive disclosure rules**. The starting context should include the map and guidance, but not the contents of dozens of files. Aider’s guidance is explicit that too many files confuse the model; Codex’s skill system limits initial skill context; OpenHands warns that certain skill formats permanently increase token usage across turns. So the context contract should encode what can be loaded eagerly, what should be loaded lazily, and what evidence must be retained after compaction. citeturn18view0turn18view1turn8view4turn8view7turn9view8

## The tools and runtime the harness should provide

The tool contract should be narrow, strong, and explicitly biased towards discovery. I would provide five tool families.

The first family is **repository read/search tools**: directory listing, glob match, content grep with file/line results, file read with paging, and a way to mark file snippets as evidence. Claude Code’s Read, Glob, and Grep design is an excellent reference because it is explicit about paging, `.gitignore` behaviour, truncation, and what each tool returns. These details matter if you want reproducible discovery traces rather than loose shell output. citeturn17view0turn17view2turn17view3

The second family is **symbol-aware navigation tools**: definition lookup, reference search, workspace symbol search, call hierarchy, and implementation lookup. Claude’s LSP tool is the best public example here. If this layer is missing, the agent starts behaving like a fast intern with grep; with it, it behaves more like a senior engineer jumping through symbols and interface boundaries. AutoCodeRover’s AST-first design supports the same conclusion from the research side. citeturn19view0turn8view9

The third family is **bounded command execution**. You still want shell access, because build files, generators, tests, and scripts make large parts of a repo legible. But discovery should default to safe local commands: listing, dependency introspection, test enumeration, static analysis, type checks, and perhaps selected test runs. Codex and Claude both show how to combine autonomy with sandboxing and permission policy; OpenHands shows how to isolate execution when needed. A read-only or workspace-bounded execution posture is the right default. citeturn14view0turn14view1turn12view4turn12view3turn5search3

The fourth family is **delegation and synthesis tools**. The harness should be able to spawn read-only subagents to investigate independent codebase areas in parallel, then merge their findings. Claude’s Explore and Plan subagents, and OpenHands’ sub-agent delegation, both support this design. Each exploration subagent should have its own local context and return a compact result rather than polluting the parent thread with every intermediate step. citeturn8view5turn9view7turn17view4

The fifth family is **lifecycle hooks and external context tools**. Codex hooks can log, validate, summarise, or persist session artefacts during the lifecycle, and MCP support lets an agent reach issue trackers, design tools, docs, or internal knowledge systems when the repo alone is insufficient. For your discovery harness, hooks are particularly valuable for enforcing output schema and saving evidence-backed memories after each area exploration. MCP should be available, but it should generally remain opt-in for discovery so the repo remains the primary source of truth unless external context is specifically required. citeturn14view4turn14view3turn14view2

One design choice is worth stating plainly. I would **not** make the harness bash-only, even though mini-SWE-agent demonstrates how far a simple shell-driven loop can go. Bash-only is compelling for benchmarking and for lightweight execution harnesses, but your discovery task needs structured evidence capture, symbol navigation, and reliable downstream compilation. The right compromise is a structured default toolset with bash as a fallback, not bash as the only interface. That is an inference, supported by the contrast between mini-SWE-agent’s simplicity and the richer navigation interfaces exposed by Claude Code, Codex, OpenHands, and Aider. citeturn15view1turn19view0turn14view3turn8view6turn8view0

## The output contract the discovery run should emit

The discovery run’s output should be a **navigable repository knowledge graph with evidence**, plus a derived reading plan. The graph should be the canonical output; linear file orderings should be generated from it when needed. The reason is simple: all the strongest harnesses now think in terms of repository maps, symbols, subagent results, and scoped context, not in terms of one giant ordered transcript. citeturn8view0turn17view4turn9view7turn8view9

A sound output schema would look conceptually like this:

```json
{
  "run_meta": {
    "repo": "...",
    "commit": "...",
    "timestamp": "...",
    "objective": "repo discovery",
    "budgets": {"tokens": "...", "time": "..."},
    "tool_profile": "read-only-plus-verify"
  },
  "areas": [
    {
      "id": "area.auth-service",
      "name": "Authentication and session handling",
      "kind": "service-area",
      "summary": "...",
      "key_files": ["src/auth/..."],
      "key_symbols": ["AuthService", "SessionStore", "validateToken"],
      "entrypoints": ["HTTP middleware", "CLI command"],
      "dependencies": ["area.http-stack", "area.persistence"],
      "conventions": ["JWT claims mapping", "middleware ordering"],
      "invariants": ["all routes require tenant context before authz"],
      "evidence": [{"file": "...", "lines": "..."}, {"command": "..."}],
      "confidence": 0.86,
      "unknowns": ["refresh-token revocation path not confirmed"]
    }
  ],
  "edges": [
    {"from": "area.auth-service", "to": "area.persistence", "type": "depends-on"},
    {"from": "area.auth-service", "to": "area.http-stack", "type": "entrypoint-via"}
  ],
  "conventions_register": [],
  "hotspots": [],
  "open_questions": [],
  "reading_plan": [],
  "memory_compiler_handoffs": []
}
```

The key design choice is that **areas** are first-class objects. Each area should represent a stable slice of the codebase, not merely a directory. Area formation should be inferred from file structure, manifests, symbol graphs, imports, call hierarchies, config ownership, and co-located tests. This is a designed inference, but it follows directly from Aider’s repo-map abstraction, Claude’s symbol tooling, and AutoCodeRover’s structure-first programme representation. citeturn8view0turn19view0turn8view9

The **reading plan** should be a derived view over the graph, not the graph itself. It should rank the next best areas or files to inspect for a given purpose: onboarding, implementing a feature, debugging a subsystem, or compiling a topic memory. Because current harnesses increasingly separate exploration contexts and then return compact results, a graph-plus-derivations model will stay more reusable than a single one-off plan. citeturn8view5turn9view7turn14view2

The output should also include an **evidence ledger** and **confidence scores**. Discovery without provenance quickly becomes untrustworthy. OpenHands’ event-driven architecture and serialisable settings, plus Codex hooks and Claude’s explicit tool boundaries, all point towards replayability and traceability as first-class properties. Downstream memory compilers should be able to ask not only “what do we think is true?” but also “which file, symbol, or command result established it?”. citeturn8view6turn9view6turn14view4turn17view0

## A reference architecture for your harness

I would implement the harness as a staged, read-mostly pipeline.

The **bootstrap stage** builds repository guidance and structural priors: parse manifests, discover instruction files, build the repo map, initialise symbol indexes, and identify likely architectural seams. This stage should emit an initial area hypothesis graph, even if coarse. That mirrors the “compact whole-repo map first” idea from Aider and the “instructions before work” pattern in Codex and Claude Code. citeturn8view0turn8view3turn12view0

The **exploration stage** fans out read-only subagents across candidate areas. Each subagent gets the area hypothesis, the relevant sub-tree and symbols, and a tightly scoped prompt: determine purpose, entry points, boundaries, conventions, dependencies, tests, and unresolved questions. Claude’s Explore pattern and OpenHands’ independent subagent contexts are the clearest public precedents. citeturn8view5turn9view7

The **verification stage** runs only where needed. If an area hypothesis depends on execution facts, the agent may run targeted commands: enumerate tests, inspect package graphs, run type checks, render routes, trace build tasks, or execute small probes inside the repo boundary. This mirrors the bounded shell usage patterns documented by Claude, Codex, and OpenHands. citeturn12view3turn14view0turn14view1turn5search3

The **synthesis stage** merges area findings into the canonical graph, resolves duplication, promotes repeated conventions into a conventions register, and computes one or more derived reading plans. This stage is where a stronger model may be worth the cost. OpenHands’ serialisable settings and condensers, Codex hooks, and Claude’s memory files all suggest that synthesis should be explicit and durable, not lost inside a transient chat thread. citeturn9view6turn9view8turn14view4turn12view0

The **handoff stage** writes outputs for two audiences. One audience is human: a concise codebase area map, conventions register, hotspots, and open questions. The other is machine: JSON or protobuf artefacts for topic-specific memory compilers, with stable IDs, evidence references, and confidence metadata. This split follows naturally from the distinction, seen in Claude and Codex, between persistent project guidance and richer workflow artefacts. citeturn12view0turn8view3turn14view2

If I reduce the entire research to one bottom-line recommendation, it is this: **build the discovery harness as a read-only, symbol-aware, subagent-capable graph builder with strong evidence capture and strict context discipline**. That is the closest public approximation today to “an agent that behaves like a senior engineer discovering a codebase”, and it is the best substrate for the memory-compilation phase you want to build next. citeturn8view5turn8view0turn19view0turn9view7turn8view9turn14view4