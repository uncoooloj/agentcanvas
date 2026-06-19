# Projection Contract

AgentCanvas projection is provider and agent agnostic. It does not call a model
itself. It prepares grounded source facts, a prompt contract, a JSON response
schema, deterministic fallback behavior, and validators.

The core path is LLM-assisted repo understanding. AgentCanvas is usually invoked
by an LLM or coding agent that can translate code facts into human-readable flow
language. Language modules should therefore act as grounding, chunking, and
provenance providers. They improve precision, but they are not a required
perfect-parser barrier.

## Modes

- `llm-assisted`: primary path. A caller sends `source_facts`, repository
  summary, prompt messages, and the canvas-query JSON schema to any model or
  agent. The caller validates the returned JSON before materializing it.
- `heuristic`: offline fallback. It only preserves already-grounded canvas nodes
  and edges from facts, without inferring new flow language.

## Contracts

The package exposes these constants and helpers from `agentcanvas.projection`:

- `SOURCE_FACTS_JSON_SCHEMA`: input facts from language modules or the existing
  workflow IR.
- `PROJECTION_CONTRACT_JSON_SCHEMA`: prompt contract shape for callers.
- `CANVAS_QUERY_JSON_SCHEMA`: response schema the LLM-assisted caller must fill.
- `build_projection_prompt(source, repo_summary=None)`: returns provider-neutral
  chat messages, response schema, and source facts.
- `heuristic_project(source, repo_summary=None)`: deterministic no-LLM fallback.
- `validate_canvas_query(query, source_facts=None)`: checks schema, fact IDs,
  node references, and operation shape.
- `materialize_canvas_model(query, repo_summary=None, source_facts=None)`: turns
  validated canvas query operations into AgentCanvas workflow IR shape.

The projection layer intentionally has no model SDK, API key, or agent-specific
adapter.

## Tiny Sample

Facts are grounded chunks with provenance:

```json
{
  "schema": "agentcanvas.source_facts.v1",
  "version": "0.1.0",
  "repo": {"name": "sample-js-app"},
  "facts": [
    {
      "id": "fact:file:src/routes/checkout.js",
      "kind": "file_chunk",
      "subject": "src/routes/checkout.js",
      "summary": "Checkout route exposes /checkout and imports checkout orchestration.",
      "attributes": {"path": "src/routes/checkout.js", "routes": [{"path": "/checkout"}]},
      "evidence": [{"path": "src/routes/checkout.js"}],
      "confidence": 0.95
    }
  ],
  "warnings": []
}
```

`build_projection_prompt(...)` turns those facts into:

```json
{
  "schema": "agentcanvas.llm_projection_prompt.v1",
  "primary_mode": "llm-assisted",
  "fallback_mode": "heuristic",
  "messages": [
    {"role": "system", "content": "You project grounded repository facts..."},
    {"role": "user", "content": "Project these grounded facts..."}
  ],
  "response_schema": {"$id": "https://agentcanvas.local/schemas/canvas-query-v1.json"}
}
```

The calling LLM or agent fills the canvas query:

```json
{
  "schema": "agentcanvas.canvas_query.v1",
  "version": "0.1.0",
  "mode": "llm-assisted",
  "operations": [
    {
      "op": "upsert_node",
      "node": {
        "id": "route:/checkout",
        "type": "route",
        "label": "Checkout route",
        "path": "src/routes/checkout.js"
      },
      "fact_ids": ["fact:file:src/routes/checkout.js"],
      "confidence": 0.95,
      "rationale": "The route fact identifies /checkout."
    }
  ],
  "warnings": []
}
```

After `validate_canvas_query(...)`, `materialize_canvas_model(...)` returns the
current AgentCanvas workflow IR shape:

```json
{
  "schema": "agentcanvas.workflow.v1",
  "nodes": [
    {
      "id": "route:/checkout",
      "type": "route",
      "label": "Checkout route",
      "path": "src/routes/checkout.js"
    }
  ],
  "edges": [],
  "projection": {
    "source_schema": "agentcanvas.canvas_query.v1",
    "mode": "llm-assisted"
  }
}
```

For a runnable in-repo sample, see `agentcanvas/projection/sample.py`.

## How Callers Use It

1. Gather facts from language modules, `workflow.ir.json`, or another reliable
   repo summary source.
2. Call `build_projection_prompt(...)`.
3. Send `messages` and `response_schema` to the caller's chosen LLM/provider.
4. Parse the model's JSON response.
5. Run `validate_canvas_query(response, source_facts=prompt["source_facts"])`.
6. Run `materialize_canvas_model(...)`.
7. Hand the materialized model to the existing canvas/server path when that
   integration exists.

## Integration Points

- Language modules: emit `source_facts.v1` facts with chunk IDs, paths, symbols,
  summaries, confidence, and evidence.
- Indexer: can optionally expose facts from existing workflow IR using
  `facts_from_workflow_ir(...)`.
- Agent adapters: can call `build_projection_prompt(...)`, use their own model,
  then validate and materialize the response.
- Server/UI: can later accept a materialized workflow IR or canvas query output.
- CLI: can later add a projection command, but the contract is usable without one.
