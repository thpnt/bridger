# LLMClient

`bridger.llm` defines Bridger's provider-independent boundary for one model turn.
It is intentionally smaller than an agent loop: callers prepare messages and tool
definitions, call `LLMClient.generate(...)`, and receive exactly one normalized
text response, structured output, tool-call list, refusal, or Bridger LLM error.

The client does not execute repository tools, decide when an agent loop stops,
validate Context Plans as application artifacts, persist traces, or generate
workflow retries.

## Configuration

The first production provider is OpenAI through the official asynchronous
Responses API client.

Required environment variables:

- `OPENAI_API_KEY`: OpenAI API credential. Never store this in
  `.bridger/config.json`.
- `BRIDGER_OPENAI_MODEL`: model ID used by the `balanced` profile.

Optional environment variables:

- `BRIDGER_OPENAI_MAX_OUTPUT_TOKENS`
- `BRIDGER_OPENAI_TIMEOUT_SECONDS`

`.bridger/config.json` may contain non-secret LLM settings only:

```json
{
  "llm": {
    "default_profile": "balanced"
  }
}
```

Existing config files without `llm` remain valid.

## Text Example

```python
from bridger.llm import LLMMessage, LLMOperation, LLMRequest, create_llm_client

llm_client = create_llm_client()

response = await llm_client.generate(
    LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        profile="balanced",
        messages=[
            LLMMessage.system("Investigate the repository."),
            LLMMessage.user("Find the runtime entrypoints."),
        ],
    )
)

print(response.text)
```

## Tool-Call Example

The client sends provider-neutral tool definitions and returns tool calls. It
does not execute tools.

```python
from bridger.llm import LLMToolDefinition

tools = [
    LLMToolDefinition(
        name="read_file_excerpt",
        description="Read a bounded excerpt from a safe indexed file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        strict=True,
    )
]

response = await llm_client.generate(
    LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[
            LLMMessage.system("Use tools when needed."),
            LLMMessage.user("Inspect the package entrypoint."),
        ],
        tools=tools,
    )
)

for call in response.tool_calls:
    print(call.id, call.name, call.arguments)
```

Tool results should be replayed as tool messages, not user text:

```python
LLMMessage.tool_result_message(
    tool_call_id="call_123",
    tool_name="read_file_excerpt",
    result={"ok": True, "lines": ["..."]},
)
```

Layer 6 binds its explicit navigation surface to an already constructed
`RepositoryNavigator`:

```python
from bridger.navigation import build_navigation_tools

tool_executor = build_navigation_tools(navigator)
request = LLMRequest(
    operation=LLMOperation.REPO_DISCOVERY,
    messages=[LLMMessage.user("Locate the repository entrypoints.")],
    tools=tool_executor.definitions,
)

response = await llm_client.generate(request)
results = [await tool_executor.execute(call) for call in response.tool_calls]
```

Each result preserves the provider call ID, tool name, structured JSON output,
or an ordinary tool error. The executor validates Pydantic arguments before it
invokes the bound navigator. It does not call the model or continue a task loop.

## Structured Output Example

```python
from pydantic import BaseModel


class EntrypointSummary(BaseModel):
    paths: list[str]
    notes: str


response = await llm_client.generate(
    LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[LLMMessage.user("Return discovered entrypoints.")],
    ),
    output_type=EntrypointSummary,
)

summary = response.structured_output
```

The OpenAI adapter requests strict JSON schema output where supported by the
Responses API, then validates the returned JSON locally with Pydantic. Invalid
JSON, schema validation failures, refusals, empty structured outputs, and
incomplete structured outputs raise normalized Bridger errors.

## Dummy Client

Use `DummyLLMClient` for deterministic tests and future orchestration loops:

```python
from bridger.llm.testing import DummyLLMClient

client = DummyLLMClient(
    outcomes=[
        LLMResponse(text="first", provider="dummy", model="scripted"),
        LLMResponse(tool_calls=[tool_call], provider="dummy", model="scripted"),
        LLMResponse(
            structured_output=EntrypointSummary(paths=["src/app.py"], notes="CLI"),
            provider="dummy",
            model="scripted",
        ),
    ]
)
```

Outcomes are consumed in order and requests are recorded on `client.requests`.
Exhaustion raises `DummyLLMExhaustedError`.

## Privacy And Logging

The OpenAI adapter honors the generic request's `store` value. It defaults to
`False`; the Stage 4 memory-worker path enables it only for its active
within-cycle continuation chain. Disabling response storage is not a
zero-retention guarantee.

Default logs include safe operational metadata: operation, provider, model,
profile, latency, token usage, retry count, structured schema name, and tool-call
count. Logs do not include prompts, source contents, tool results, API keys, raw
provider request bodies, or raw provider response bodies.

Only `workflow_id` and `run_id` request metadata keys are forwarded to OpenAI.
Arbitrary internal metadata is kept local.

## Current Limitations

- OpenAI is the only production provider.
- Streaming is not implemented.
- Provider fallback, billing, cost calculation, and semantic caching are out of
  scope. OpenAI prefix caching is implemented only when a request carries
  explicit provider-neutral cache intent, currently the Stage 4 memory-worker
  path.
- The adapter returns tool calls but never executes tools.
- Workflow-level repair retries for invalid structured output are not implemented.
