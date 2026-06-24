---
name: agentcanvas
description: Launch and use AgentCanvas, a local workflow canvas for AI coding agents. Use when a user wants to map a workspace, inspect or edit workflow logic, generate implementation requests, consume `.agentcanvas/pending` requests, update request status, use demo/no-workspace mode, or hand work between AgentCanvas and any AI coding agent, MCP tools, APIs, webhooks, or a generic terminal agent.
---

# AgentCanvas

Use AgentCanvas to turn a workspace into a local workflow canvas, keep that
canvas editable, and create implementation requests only when source-code work
is explicitly needed.

Keep the workflow simple: index evidence, translate behavior into the display
canvas, edit the canvas, and use pending requests only for code implementation.

## Core Rules

- Treat `.agentcanvas/` as the shared contract.
- Treat `.agentcanvas/workflow.ir.json` as the raw index and evidence grounding
  file.
- Treat `.agentcanvas/canvas.ir.json` as the browser display canvas source of
  truth.
- Treat `.agentcanvas/pending/*.md` as the human-readable implementation brief.
- Treat `.agentcanvas/pending/*.json` as structured implementation context for
  tools.
- The invoking agent should translate repo behavior into plain-English,
  non-technical flows and write/update `.agentcanvas/canvas.ir.json`
  progressively.
- Canvas edits, adds, removes, renames, and re-routes should update
  `.agentcanvas/canvas.ir.json`.
- Do not edit source code just because a canvas node changed. Implement source
  code only when the user explicitly asks or when there is an explicit pending
  implementation request.
- Re-indexing refreshes `.agentcanvas/workflow.ir.json`; it is not required
  after canvas-only edits.
- Before executing a pending request, inspect the request and current workspace
  context.
- Start implementation only when the requested change, affected flow or step,
  acceptance criteria, and verification path are clear.
- If anything is ambiguous, risky, incomplete, or contradicted by the current
  workspace, ask concise plain-language clarifying questions and wait.
- Do not execute unclear changes blindly. Clarify first, then apply only the
  clear request or validated projection.
- Do not mark a request done until the implementation was verified.
- Do not run migrations, seeds, deploys, or destructive commands without
  explicit user permission.
- If no live agent/session is connected, use copy fallback.

## Plain-English Map Authoring

The default map audience is a non-technical project owner. Author the visible
canvas as a plain-English map of what people can do, what the project does next,
and what changes when a branch happens. This applies whether the invoking agent
is Codex, Claude Code, Cursor, Antigravity, or any other coding agent.

Visible map text means journey titles, step titles, branch labels, lane names,
short summaries, and any text a person reads in the canvas. For visible text:

- Use short 2-5 word titles, such as "Choose a plan" or "Send the receipt".
- Prefer everyday verbs: choose, send, approve, review, pay, invite, upload,
  fix, start, finish, remind, publish.
- Avoid file paths, package names, model names, tool names, framework names, API
  routes, schema terms, and implementation jargon.
- Put technical provenance only in refs, details, evidence ids, or supporting
  data. Source paths and tool names can help audit the map, but they should not
  be the label a user sees first.
- Match the workspace type. Use "project" as the safe default when the product
  type is unclear; use "site", "store", "game", "lesson", "workflow",
  "automation", "library", or another everyday noun only when the evidence
  supports it.
- Describe outcomes and user-visible behavior instead of internals. Prefer
  "Check the booking" over "Validate reservation DTO".
- Keep technical acronyms out of visible text unless they are part of the
  product language the intended reader already uses.

If a requested map change is ambiguous, would change what the map claims the
workspace does, or could be interpreted in more than one user-visible way, ask a
short plain-language question before writing or executing anything. Do not
silently convert an unclear map change into source-code work.

## Check The CLI

Start by checking the installed command:

```bash
agentcanvas --help
```

If `agentcanvas` is not installed and this is the AgentCanvas source repo,
install it locally:

```bash
python3 -m pip install -e .
```

## Real Workspace

Index the workspace:

```bash
agentcanvas index --workspace <workspace>
```

This writes or refreshes `.agentcanvas/workflow.ir.json`, the raw evidence file.

Start the local canvas:

```bash
agentcanvas start --workspace <workspace> --port 8765
```

If the calling agent has a stable session id, pass it through:

```bash
agentcanvas start --workspace <workspace> --port 8765 --session-id <session-id>
```

Open the printed URL when your environment can open browsers. Otherwise give
the URL to the user.

After indexing, make sure `.agentcanvas/canvas.ir.json` exists or is updated
from the grounded evidence. Keep the display canvas human-readable: use journeys,
steps, branches, lanes, and provenance instead of a raw file inventory. Follow
the plain-English map authoring rules for all visible titles and labels.

## No Workspace And Demo

Use the no-workspace landing when no project is selected:

```bash
agentcanvas start --port 8765
```

Use explicit demo mode for the bundled sample project:

```bash
agentcanvas start --demo --port 8765
```

In demo mode, keep saying that it is demo mode. Do not imply the demo is the
user's own repo.

## Pending Request Loop

Use this loop only for explicit source-code implementation work. For canvas-only
requests like adding a step, removing a branch, renaming a journey, or re-routing
a flow, update `.agentcanvas/canvas.ir.json` and do not re-index.

List pending requests:

```bash
agentcanvas pending --workspace <workspace>
```

Read the selected `.md` first. Read the matching `.json` for structured ids,
affected files, flow or step references, and acceptance criteria. Inspect the
current workspace context before editing so you know whether the request still
matches the code.

Before entering execution mode, confirm these four things:

- the requested change is specific enough to implement
- the affected flow, journey, step, route, or behavior is identified
- the acceptance criteria say what a good result looks like
- the verification path is clear, such as a test, smoke check, or manual path

If any item is missing, ambiguous, risky, incomplete, or contradicted by the
current workspace, do not guess and do not mark the request `in_progress`. Ask
the fewest useful clarifying questions in plain language:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: should this change apply to checkout only, or to every order flow?"
```

Keep questions short enough for a non-technical user to answer. Ask about the
user-visible behavior, affected flow or step, acceptance criteria, verification
expectation, or safety permission that is blocking work.

Only after the request is clear, mark work in progress:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
```

After implementation, run the relevant test or smoke check, then re-index to
refresh evidence:

```bash
agentcanvas index --workspace <workspace>
```

Mark done only after verification:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified."
```

Use `blocked` when progress cannot continue without an external change.

## Canvas Edit Loop

For a canvas-only request:

1. Read `.agentcanvas/workflow.ir.json` for evidence.
2. Read `.agentcanvas/canvas.ir.json` for the current display canvas.
3. Apply the edit to `.agentcanvas/canvas.ir.json`.
4. Preserve evidence ids, source paths, or provenance where possible.
5. Do not change source code.
6. Do not run `agentcanvas index` unless the user asks to refresh evidence.

If a requested canvas edit would make a repo behavior claim that is not grounded
by the current evidence, ask a concise question or mark it as a planned canvas
change rather than pretending the source already does it.

If a requested canvas edit is ambiguous, ask before applying it. Clarify the
user-visible outcome, affected journey or step, and whether the user wants a map
change only or a separate implementation request.

## Copy Fallback

When no adapter or live session is available, provide a copyable prompt instead
of pretending to send work. Copy/manual mode is a supported fallback, not an
error state.

For canvas-only edits, the prompt should tell the agent to update
`.agentcanvas/canvas.ir.json` and stop. For implementation requests, include the
pending-request context and status loop.

Implementation prompts should include:

- workspace path
- pending Markdown path
- pending JSON path
- acceptance criteria
- reminder to inspect the workspace context before editing
- instruction to ask concise clarifying questions before execution if the
  requested change, affected flow or step, acceptance criteria, or verification
  path is unclear
- exact status commands
- reminder to test and re-index after source-code changes

For portable prompt snippets, read `references/agent-prompts.md`.

## Integration Paths

- **Skill**: this skill is the portable first path.
- **Local API**: the browser/server path uses `/api/context`, `/api/graph`,
  `/api/pending`, `/api/changes`, `/api/status`, and `/api/reindex`.
- **MCP**: if MCP tools exist, use them only as wrappers around the same actions:
  get context, read/update the display canvas, list pending, create request,
  update status, and re-index.
- **Webhooks**: if webhook support exists, use it for status/reply events, not
  direct source edits.

Keep every path aligned with the same file contract: `workflow.ir.json` grounds
evidence, `canvas.ir.json` displays the canvas, and pending files carry explicit
implementation requests.

## LLM Projection

LLM-assisted projection is the intended path for turning source facts into the
human-readable display canvas. AgentCanvas prepares facts and a provider-neutral
contract; the invoking agent or model reads them, asks for clarification if
needed, generates an `agentcanvas.canvas_query.v1`, validates it, then applies
it to `.agentcanvas/canvas.ir.json`.

Before generating or applying a projection, read:

- `.agentcanvas/workflow.ir.json`
- `.agentcanvas/canvas.ir.json` when it already exists
- `source_facts`
- `projection_contract`
- `source_facts.repo.app_surfaces` when present

Generate journeys in AgentCanvas language:

- `When`: what starts the journey
- `Do`: what the app does
- `If`, `ElseIf`, `Else`: branches and outcomes

Keep the canvas human-readable and non-technical by default. Use `app_surfaces`
as lanes, participants, or drilldowns inside a journey. Cite provenance with
`fact_ids` on every operation and include useful evidence in node or edge data
when it helps a person audit the result. Do not create top-level journeys from a
raw file inventory; files, tests, services, packages, tools, routes, and schemas
belong as supporting details, refs, or provenance, not visible map titles.

For generated visible text, use 2-5 word titles, everyday verbs, and
workspace-type-sensitive nouns. Use "project" when the workspace type is unclear
and choose terms like "site", "store", "game", "lesson", "workflow", or
"automation" only when the evidence supports them.

If the intended journey, actor, outcome, affected surface, or evidence is
unclear, ask concise clarifying questions before applying the result. Progressive
mapping is fine: return the flows that are grounded and leave warnings for the
rest.

Validate before writing:

```bash
agentcanvas apply-query --workspace <workspace> --query <canvas-query.json> --dry-run
```

Apply only after validation passes and the user wants the display canvas written:

```bash
agentcanvas apply-query --workspace <workspace> --query <canvas-query.json>
```

`apply-query` writes the display canvas. It does not overwrite
`.agentcanvas/workflow.ir.json` or replace the raw facts.

If no live model or adapter is available, use copy/manual mode: give the
projection prompt, response schema, source facts, dry-run command, and apply
command for the user or another agent to run.

## Adding Languages

When adding or reviewing language support, read
`references/language-support.md`.

Language modules should emit grounded facts with provenance. The projection
layer can turn those facts into human-readable canvas flows.
