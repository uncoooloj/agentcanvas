---
name: agentcanvas
description: Launch and use AgentCanvas, a local workflow canvas for AI coding agents. Use when a user wants to map a workspace, inspect or edit workflow logic, generate implementation requests, consume `.agentcanvas/pending` requests, update request status, use demo/no-workspace mode, or hand work between AgentCanvas and Codex, Claude Code, Cursor, Antigravity, MCP tools, APIs, webhooks, or a generic terminal agent.
---

# AgentCanvas

Use AgentCanvas to turn a workspace into a local workflow canvas and then into
agent-ready implementation requests.

Keep the workflow simple: index, inspect, create/request, implement, verify,
update status, re-index.

## Core Rules

- Treat `.agentcanvas/` as the shared contract.
- Treat `.agentcanvas/pending/*.md` as the human-readable task brief.
- Treat `.agentcanvas/pending/*.json` as structured context for tools.
- Do not edit source code just because a canvas node changed; implement only an
  explicit pending request.
- Do not mark a request done until the implementation was verified.
- Do not run migrations, seeds, deploys, or destructive commands without
  explicit user permission.
- If no live agent/session is connected, use copy fallback.

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

List pending requests:

```bash
agentcanvas pending --workspace <workspace>
```

Read the selected `.md` first. Read the matching `.json` when structured ids,
affected files, or acceptance criteria are useful.

Mark work in progress:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
```

Ask for input:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "Question for the user..."
```

After implementation, run the relevant test or smoke check, then re-index:

```bash
agentcanvas index --workspace <workspace>
```

Mark done only after verification:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified."
```

Use `blocked` when progress cannot continue without an external change.

## Copy Fallback

When no adapter or live session is available, provide a copyable prompt instead
of pretending to send work.

Include:

- workspace path
- pending Markdown path
- pending JSON path
- acceptance criteria
- exact status commands
- reminder to test and re-index

For agent-specific prompt snippets, read `references/agent-prompts.md`.

## Integration Paths

- **Skill**: this skill is the portable first path.
- **Local API**: the browser/server path uses `/api/context`, `/api/graph`,
  `/api/pending`, `/api/changes`, `/api/status`, and `/api/reindex`.
- **MCP**: if MCP tools exist, use them only as wrappers around the same actions:
  get context, list pending, create request, update status, and re-index.
- **Webhooks**: if webhook support exists, use it for status/reply events, not
  direct source edits.

Keep every path aligned with the same pending request lifecycle.

## LLM Projection

If a caller LLM generates `agentcanvas.canvas_query.v1` JSON from the projection
contract, validate before writing:

```bash
agentcanvas apply-query --workspace <workspace> --query <canvas-query.json> --dry-run
```

Apply only after validation passes and the user wants it:

```bash
agentcanvas apply-query --workspace <workspace> --query <canvas-query.json>
```

## Adding Languages

When adding or reviewing language support, read
`references/language-support.md`.

Language modules should emit grounded facts with provenance. The projection
layer can turn those facts into human-readable canvas flows.
