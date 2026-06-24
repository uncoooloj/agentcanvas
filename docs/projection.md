# Projection Contract

Projection is how AgentCanvas turns repo evidence into a canvas a person can
read.

AgentCanvas does not need to be the model provider. It prepares grounded facts;
the invoking agent or caller model turns those facts into human-readable flows,
validates the result, and writes the display canvas.

The caller may be any coding agent, model wrapper, MCP tool, local API client, or
manual copy/paste flow. The contract is the same in each path.

## File Contract

The current contract separates raw evidence from the browser canvas:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/canvas.ir.json
```

`workflow.ir.json` is the raw index and evidence grounding file. Re-indexing
refreshes this file from the repo.

`canvas.ir.json` is the browser display canvas source of truth. The invoking
agent should translate repo behavior into readable AgentCanvas flows and update
this file progressively as the user edits the canvas.

Canvas-only edits, such as adding a step, removing a branch, renaming a journey,
or re-routing a flow, should update `canvas.ir.json`. They should not require
re-indexing, because no repo evidence changed.

`agentcanvas.canvas_query.v1` and `agentcanvas apply-query` are still useful as a
validation and materialization path. Applying a query writes the display canvas.
It does not overwrite `workflow.ir.json` or rewrite repo facts.

## Source-Truth States

When the browser opens a canvas, it should describe the source plainly:

- **Assistant map**: `.agentcanvas/canvas.ir.json` was authored or reviewed by
  an agent or model from grounded repo evidence. This is the main product
  experience and the browser display source of truth.
- **Starter view**: no assistant map exists yet, so AgentCanvas builds a simple
  first view from indexed evidence. Use it to get oriented, then ask an agent or
  model to turn it into a cleaner assistant map.
- **Demo/example**: the canvas belongs to the bundled sample project. It can
  teach the loop, but it is not evidence from the user's repo.
- **No map yet**: AgentCanvas has indexed the workspace but there is no readable
  display canvas yet. The next step is to create `.agentcanvas/canvas.ir.json`
  from `.agentcanvas/workflow.ir.json`.
- **Stale saved map**: an assistant-authored map exists, but
  `.agentcanvas/workflow.ir.json` is newer. Keep the saved map visible, label it
  stale, and ask the agent or model to refresh it from the latest evidence.

Plain version: if the app says there is no readable map yet, the repo facts are
not enough by themselves. Ask the agent or model to read the evidence file and
write the human map. This is like asking someone to turn notes into a clean
diagram before you use it to plan changes.

## Agent-Authored Canvas Workflow

The readable canvas is authored by an agent or LLM using grounded evidence. The
indexer helps by collecting facts; it is not the final map.

The expected workflow is:

1. Index the workspace into `.agentcanvas/workflow.ir.json`.
2. Read the raw evidence, especially `source_facts`, `projection_contract`, and
   any `app_surfaces`.
3. If the journey, actor, outcome, affected surface, or evidence is unclear, ask
   a short plain-English question before writing the canvas.
4. Generate or edit `agentcanvas.canvas_query.v1` operations using `When`, `Do`,
   `If`, `ElseIf`, and `Else`.
5. Cite `fact_ids` for repo claims.
6. Validate with `agentcanvas apply-query --dry-run`.
7. Apply only after validation passes, writing `.agentcanvas/canvas.ir.json`.

Canvas-only edits continue from the same file. The agent reads
`.agentcanvas/canvas.ir.json`, applies the map change, preserves evidence where
possible, and does not touch source code unless the user explicitly asks for
implementation.

If no live model adapter exists, this same workflow can happen in copy/manual
mode: copy the prompt and source facts into another agent, validate the returned
query, then apply it through the CLI.

## Plain Version

The safe flow is:

1. Index the repo.
2. Read `.agentcanvas/workflow.ir.json`, especially `source_facts`, the
   projection contract, and any `app_surfaces`.
3. Ask clarifying questions if the actor, outcome, affected flow, or evidence is
   unclear.
4. Ask an LLM or agent to propose human-readable canvas changes.
5. Validate the JSON it returns.
6. Write `.agentcanvas/canvas.ir.json` only if validation passes.
7. Fall back to a simple grounded view or copy/manual mode if no live adapter is
   available.

## Modes

- `llm-assisted`: preferred path. A caller sends grounded facts and a response
  schema to its chosen model or agent.
- `heuristic`: fallback path. AgentCanvas keeps grounded facts and simple
  nodes without inferring a richer story.
- `copy/manual`: fallback handoff when no adapter or live session is available.
  The user or invoking agent copies the prompt, validates the response, then
  applies it with the same CLI gate.

Progressive mapping is expected. A projection can cover the flows it can prove
and leave warnings for the rest. It should not pretend the whole app is mapped
when the facts only support one journey.

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

This command materializes the display canvas. It should preserve the raw
grounding file and should not be described as overwriting workflow facts.

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

The model or agent can return `agentcanvas.canvas_query.v1` operations. Those
operations must reference known fact ids when they make claims about the repo.
They are instructions for the display canvas, not a replacement for the raw
index.

## What The Model Should Generate

Generate human-readable AgentCanvas journeys, not a top-level file inventory.
Use this vocabulary where the facts support it:

- `When`: the user, system, job, event, route, screen, webhook, or schedule that
  starts the journey
- `Do`: work the app performs
- `If`, `ElseIf`, `Else`: business or system branches

Use `app_surfaces` as lanes, participants, or drilldowns inside a journey. For
example, signup across mobile, web, and backend is usually one journey with
multiple surfaces unless the actor, outcome, or business rules differ.

Every operation should cite `fact_ids`. When useful, include human-auditable
provenance in node or edge `data`, such as the source fact ids, source paths, or
short evidence text. Files, tests, services, packages, and modules can appear as
supporting details, but they should not become top-level journeys just because
they were indexed.

If the model cannot tell what journey a set of facts belongs to, it should omit
that relationship and add a warning. If applying the result would be misleading,
the invoking agent should ask concise clarifying questions before applying.

## Integration Paths

- **Skill**: the AgentCanvas skill tells an agent how to validate and apply a
  canvas query into `canvas.ir.json` instead of writing untrusted JSON straight
  into the workspace.
- **Local API**: later, the server can expose projection status and materialized
  canvas files, but validation should stay the gate. Canvas-only edits should
  update the display canvas, not force a re-index.
- **MCP**: planned tools can call "build projection prompt", "validate query",
  and "apply query" for display-canvas writes.
- **Webhooks**: planned webhooks can report projection success/failure or attach
  external analysis notes.
- **Manual copy**: the same prompt and schema can be copied into any model or
  coding agent, then applied only after `--dry-run` succeeds.

## Projection Status

An implementation may track projection status:

- `not_projected`
- `projecting`
- `projected`
- `projection_failed`

The UI should prefer `canvas.ir.json` when present, but it should always be able
to fall back to the indexed workflow IR.
