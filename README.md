# AgentCanvas

AgentCanvas is a small local canvas for working with coding agents.

It looks at a repo, draws the important workflow pieces, lets you mark what
should change, then turns that into a clear request an agent can implement.

The product direction is simple: do not make the user guess what the agent is
doing. Every request should be visible, copyable, and trackable from "not sent"
to "done".

## The Story

Coding agents are good at editing code once the task is clear. The hard part is
often getting from "this flow feels wrong" to "change these files and prove it."

AgentCanvas sits in that gap.

1. Point it at a workspace.
2. It indexes the code into `.agentcanvas/workflow.ir.json`.
3. The browser canvas shows the flow in plain language.
4. You ask for a change from the canvas.
5. AgentCanvas writes a pending request under `.agentcanvas/pending/`.
6. Codex, Claude Code, Cursor, Antigravity, or another agent implements it.
7. The agent updates the request status so the canvas shows the truth.

The Agentation-inspired part is the loop: work is not a vague chat message that
disappears. It becomes an item with a status, files, notes, and a copy fallback.

## Install

From this repo:

```bash
python3 -m pip install -e .
```

Check the CLI:

```bash
agentcanvas --help
```

## Start With A Real Workspace

Index a project:

```bash
agentcanvas index --workspace /path/to/your/project
```

Start the local canvas:

```bash
agentcanvas start --workspace /path/to/your/project --port 8765
```

Open the printed URL, usually:

```text
http://127.0.0.1:8765
```

After you edit the canvas, requests appear here:

```text
/path/to/your/project/.agentcanvas/pending/
```

Each request has:

- a `.md` file an agent or human can read
- a `.json` file tools can read
- a status such as `pending`, `in_progress`, `needs_input`, `blocked`, or `done`

## Start With No Workspace

If you do not have a project selected yet, start AgentCanvas without a
workspace:

```bash
agentcanvas start --port 8765
```

That should show the no-workspace landing first. From there the product should
offer three plain choices:

- open a local workspace by running the exact command to use
- paste or clone a GitHub repo once that path is wired
- enter demo mode

Use the demo directly when you want the bundled sample project:

```bash
agentcanvas start --demo --port 8765
```

Demo mode must be obvious in the UI. The user should never think the demo is
their repo or that a live agent is connected when it is not.

## Give Work To An Agent

An agent can poll for new requests:

```bash
agentcanvas pending --workspace /path/to/your/project
```

When it starts work:

```bash
agentcanvas status --workspace /path/to/your/project <pending-id> --status in_progress
```

When it needs the user:

```bash
agentcanvas status --workspace /path/to/your/project <pending-id> --status needs_input --note "I need one decision before editing."
```

When it has implemented and verified the change:

```bash
agentcanvas index --workspace /path/to/your/project
agentcanvas status --workspace /path/to/your/project <pending-id> --status done --note "Implemented and verified."
```

The important part is that the status comes from the agent or CLI, not from a
browser timer pretending work happened.

## Copy Fallback

Copy mode is a core feature.

If no live agent/session is connected, AgentCanvas should still create the
pending files and show a clean prompt the user can paste into any coding agent.
That prompt should name the request, workspace, files, acceptance criteria, and
the status commands above.

This keeps the product useful before deeper integrations exist.

## Integration Paths

AgentCanvas should stay agent-agnostic. There are four paths:

- **Skill**: install `skill/agentcanvas/` into an agent that supports skills.
  This gives the agent the workflow for indexing, reading requests, updating
  status, testing, and re-indexing.
- **Local API**: the browser uses token-protected local endpoints such as
  `/api/context`, `/api/graph`, `/api/pending`, `/api/changes`, `/api/status`,
  and `/api/reindex`.
- **MCP**: planned path for agents that prefer tools over shell commands. It
  should expose the same small actions: get context, list pending, create
  request, update status, and re-index.
- **Webhooks**: planned path for outside tools to report back. A webhook should
  be able to update request status, attach a note, or send a reply without
  pretending to be the browser.

See [docs/adapters.md](docs/adapters.md) for the adapter map and prompt
snippets.

## Projection

AgentCanvas can use an LLM or coding agent to translate grounded code facts into
a cleaner human canvas. The package does not call a model by itself.

The safe path is:

```bash
agentcanvas apply-query --workspace /path/to/your/project --query canvas-query.json --dry-run
agentcanvas apply-query --workspace /path/to/your/project --query canvas-query.json
```

Validate first, then write.

See [docs/projection.md](docs/projection.md).

## Safety

AgentCanvas is local-first and file-based.

- It writes state under `.agentcanvas/`.
- It creates requests instead of directly editing application code.
- It keeps the canvas separate from the agent that edits code.
- It makes every request inspectable before work starts.
- It should never show "done" unless the request status says `done`.

Good practice:

- Commit or stash important work before asking an agent to edit.
- Review pending requests before implementation.
- Ask before migrations, seeds, deploys, or destructive commands.
- Run the closest relevant test or smoke check.
- Re-index after implementation.

## Development

Run tests:

```bash
python3 -m unittest discover
```

Useful local loop:

```bash
python3 -m pip install -e .
agentcanvas index --workspace examples/sample-js-app
agentcanvas start --workspace examples/sample-js-app --port 8765
python3 -m unittest discover
```

Keep generated workspace state out of source commits unless it is an intentional
fixture:

```text
.agentcanvas/
```

## Skill Wrapper

The repo includes a standalone skill wrapper at:

```text
skill/agentcanvas/
```

Install that folder into your agent's skill directory if the agent supports
skills. The skill is intentionally self-contained: it explains how to launch
AgentCanvas, inspect pending requests, implement one request, update status,
test, re-index, and use copy fallback.
