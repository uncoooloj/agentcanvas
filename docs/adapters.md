# Agent Adapters

Adapters are optional. The base product is just local files, a small CLI, and a
local API.

The stable file contract is:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/canvas.ir.json
<workspace>/.agentcanvas/pending/*.md
<workspace>/.agentcanvas/pending/*.json
```

`workflow.ir.json` is raw repo evidence. `canvas.ir.json` is the browser display
canvas. Pending files are for explicit source-code implementation requests.

An adapter should do two small jobs:

- For canvas edits, help the agent update `.agentcanvas/canvas.ir.json`.
- For implementation requests, help the agent clarify, implement, verify,
  update status, and re-index to refresh evidence.

## Four Paths

### 1. Skill

Use this when an agent supports skills.

Install:

```text
skill/agentcanvas/
```

into that agent's skill directory.

The skill tells the agent to:

1. run `agentcanvas --help`
2. index or start the workspace
3. treat `.agentcanvas/workflow.ir.json` as evidence
4. treat `.agentcanvas/canvas.ir.json` as the display canvas source of truth
5. update `.agentcanvas/canvas.ir.json` for canvas-only edits
6. read `.agentcanvas/pending/*.md` and matching `.json` only for implementation
   requests
7. inspect the current workspace context before source-code editing
8. ask concise clarifying questions if the request is ambiguous, risky, or
   incomplete
9. update status with `agentcanvas status`
10. run the relevant tests
11. re-index with `agentcanvas index` after code changes

This is the best first integration because it stays portable and does not need a
server-to-agent bridge.

### 2. Local API

Use this when the browser or a local tool is already talking to the AgentCanvas
server.

Current endpoints:

- `GET /api/context`
- `GET /api/graph`
- `GET /api/pending`
- `POST /api/changes`
- `POST /api/status`
- `POST /api/reindex`

The API is local and token-protected. It should mirror the same state in
`.agentcanvas/`; it should not become a separate source of truth. Re-indexing
refreshes `workflow.ir.json`; it should not be required for canvas-only edits.

### 3. MCP

Use this when an agent prefers tools instead of shell commands or raw HTTP.

MCP is a planned path. It should expose the same simple actions:

- get context
- read or update the display canvas
- list pending requests
- create a request
- update request status
- re-index the workspace

Do not make MCP smarter than the product contract. It is a nicer handle for the
same local state.

### 4. Webhooks

Use this when an outside system needs to report back.

Webhooks are a planned path. They should handle events like:

- agent started
- agent needs input
- agent blocked
- agent finished
- CI passed or failed
- reply/note added

Webhook events should update pending records or display-canvas state. They
should not patch source code.

## Copy Fallback

Copy mode is always valid.

If no adapter is installed and no live session is connected, AgentCanvas should
still keep canvas-only edits in `.agentcanvas/canvas.ir.json`. For source-code
implementation, it should create the pending request and show a prompt the user
can paste into any coding agent.

The implementation prompt should include:

- workspace path
- selected pending `.md`
- matching `.json`
- current `.agentcanvas/canvas.ir.json` when the canvas context matters
- acceptance criteria
- reminder to inspect workspace context before editing
- instruction to clarify before execution unless the requested change, affected
  flow or step, acceptance criteria, and verification path are clear
- status commands
- reminder to test and re-index after code changes

## Prompt Snippets

Use these snippets when the user wants to hand a request to a specific agent.
They should work in any AI coding agent that can read files and run commands.

### Canvas Edit Handoff

```text
Use AgentCanvas for this workspace. Read .agentcanvas/workflow.ir.json for evidence and .agentcanvas/canvas.ir.json for the current display canvas.

Apply the requested canvas edit to .agentcanvas/canvas.ir.json only. Keep the flow human-readable, preserve evidence links where possible, and do not change source code unless the user explicitly asks for implementation. Do not re-index for a canvas-only edit.
```

### Portable Handoff

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md, and read the matching .json for structured context. Before editing, inspect the current workspace context and confirm four things are clear: the requested change, the affected flow or step, the acceptance criteria, and the verification path.

If any of those are ambiguous, risky, incomplete, or contradicted by the current workspace, do not enter execution mode yet. Ask the fewest useful clarifying questions in plain language, and update the request with needs_input plus the question.

Once the request is clear, mark it in_progress, make the smallest change that satisfies the acceptance criteria, run the agreed test or smoke check, re-index with agentcanvas index --workspace . to refresh evidence, update the request status, and summarize what changed and how it was verified.
```

### Short Handoff

```text
Work from .agentcanvas/pending only for explicit source-code implementation. Read the Markdown request and matching JSON, inspect the current workspace context, and clarify before editing unless the requested change, affected flow or step, acceptance criteria, and verification path are all clear. If clarification is needed, set status to needs_input with concise plain-language questions. Once clear, mark in_progress, implement the smallest focused change, verify it, re-index to refresh evidence, and update status.
```

### Needs-Input Status Note

```text
I need one decision before editing: <short plain-language question about the requested behavior, affected flow or step, acceptance criteria, verification path, or safety permission>.
```

### Status Commands

```bash
agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: <question>"
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified: <test or smoke check>."
```

## Adapter Rules

- Keep adapters optional.
- Keep files and CLI commands usable without adapters.
- Prefer the Markdown request as the readable source for implementation work.
- Use JSON for ids, files, node references, and acceptance criteria.
- Update `.agentcanvas/canvas.ir.json` for canvas-only edits.
- Do not require `agentcanvas index` after canvas-only edits.
- Require a clarification pass before source-code execution. The requested
  change, affected flow or step, acceptance criteria, and verification path must
  be clear before implementation starts.
- Do not require a specific agent vendor.
- Do not bypass project safety rules.
- Do not mark work done until implementation and verification happened.
