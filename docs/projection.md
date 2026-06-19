# Projection Contract

Projection is how AgentCanvas turns code facts into a canvas a person can read.

AgentCanvas does not need to be the model provider. It should prepare grounded
facts, ask a caller model or agent for a canvas query, validate the answer, and
only then write it.

## Plain Version

The safe flow is:

1. Index the repo.
2. Collect facts with file paths and evidence.
3. Ask an LLM or agent to propose a canvas.
4. Validate the JSON it returns.
5. Materialize the canvas only if validation passes.
6. Fall back to a simple grounded view if no LLM is available.

## Modes

- `llm-assisted`: preferred path. A caller sends grounded facts and a response
  schema to its chosen model or agent.
- `heuristic`: fallback path. AgentCanvas keeps grounded facts and simple
  nodes without inferring a richer story.

## Contracts

The package exposes these from `agentcanvas.projection`:

- `SOURCE_FACTS_JSON_SCHEMA`
- `PROJECTION_CONTRACT_JSON_SCHEMA`
- `CANVAS_QUERY_JSON_SCHEMA`
- `build_projection_prompt(source, repo_summary=None)`
- `heuristic_project(source, repo_summary=None)`
- `validate_canvas_query(query, source_facts=None)`
- `materialize_canvas_model(query, repo_summary=None, source_facts=None)`

There is no model SDK, API key, or provider-specific adapter in this layer.

## CLI Path

Validate first:

```bash
agentcanvas apply-query --workspace <workspace> --query canvas-query.json --dry-run
```

Write only after validation passes:

```bash
agentcanvas apply-query --workspace <workspace> --query canvas-query.json
```

## What Facts Should Look Like

Facts should be grounded and cite evidence:

```json
{
  "schema": "agentcanvas.source_facts.v1",
  "facts": [
    {
      "id": "fact:file:src/routes/checkout.js",
      "kind": "file_chunk",
      "subject": "src/routes/checkout.js",
      "summary": "Checkout route exposes /checkout.",
      "evidence": [{"path": "src/routes/checkout.js"}],
      "confidence": 0.95
    }
  ],
  "warnings": []
}
```

The model or agent returns `agentcanvas.canvas_query.v1` operations. Those
operations must reference known fact ids when they make claims about the repo.

## Integration Paths

- **Skill**: the AgentCanvas skill tells an agent how to validate and apply a
  canvas query instead of writing untrusted JSON straight into the workspace.
- **Local API**: later, the server can expose projection status and materialized
  canvas files, but validation should stay the gate.
- **MCP**: planned tools can call "build projection prompt", "validate query",
  and "apply query".
- **Webhooks**: planned webhooks can report projection success/failure or attach
  external analysis notes.

## Next Product Contract

Store the raw and projected views separately:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/canvas.query.json
<workspace>/.agentcanvas/canvas.ir.json
```

Track projection status:

- `not_projected`
- `projecting`
- `projected`
- `projection_failed`

The UI should prefer `canvas.ir.json` when present, but it should always be able
to fall back to the indexed workflow IR.
