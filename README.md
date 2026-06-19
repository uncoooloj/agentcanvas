# AgentCanvas

AgentCanvas is an agent-agnostic local workflow canvas for AI coding agents.

It indexes a workspace into `.agentcanvas/workflow.ir.json`, serves a local editable canvas, and turns canvas edits into `.agentcanvas/pending/*.md` and `.json` change requests that Codex, Claude Code, Cursor, Antigravity, or a generic terminal agent can consume.

AgentCanvas is not another coding agent. It is the local coordination layer between a repo, a visual workflow map, and whichever agent you trust to implement the next change.

## Why This Exists

Most coding agents work well when the request is precise. Real products are rarely precise at first: logic is spread across routes, services, UI states, tests, scripts, and docs. AgentCanvas gives that workflow shape before an agent starts editing.

Use it to:

- map a workspace into a reviewable workflow graph
- inspect app logic, user journeys, integrations, automations, and test coverage
- edit the workflow locally in a browser
- turn canvas edits into concrete implementation requests
- hand those requests to any coding agent without locking into one vendor

## Quick Start

From this repository:

```bash
python3 -m pip install -e .
```

Index a workspace:

```bash
agentcanvas index --workspace /path/to/your/project
```

Start the local canvas:

```bash
agentcanvas start --workspace /path/to/your/project --port 8765
```

Open the printed local URL, usually:

```text
http://127.0.0.1:8765
```

After editing the canvas, review the generated requests:

```bash
ls /path/to/your/project/.agentcanvas/pending
```

Give one pending request to your coding agent, let it implement the change, run the relevant tests, then re-index:

```bash
agentcanvas index --workspace /path/to/your/project
```

## MVP Command Contract

The MVP centers on two commands:

```bash
agentcanvas index --workspace <workspace>
agentcanvas start --workspace <workspace> --port <port>
```

`index` scans the workspace and writes:

```text
<workspace>/.agentcanvas/workflow.ir.json
```

`start` serves the local browser UI for that workspace and writes canvas-generated change requests under:

```text
<workspace>/.agentcanvas/pending/
```

Each pending request should have:

- a Markdown file for humans and coding agents
- a JSON file for tools that want structured fields

The file contract matters more than the agent. If an agent can read Markdown, inspect JSON, edit code, and run tests, it can use AgentCanvas.

## Architecture

```text
workspace
  |
  | agentcanvas index
  v
.agentcanvas/workflow.ir.json
  |
  | agentcanvas start
  v
local browser canvas
  |
  | user edits workflow
  v
.agentcanvas/pending/<request>.md
.agentcanvas/pending/<request>.json
  |
  | Codex / Claude Code / Cursor / Antigravity / terminal agent
  v
implemented code change + tests + re-index
```

The main pieces are:

- **Indexer**: reads a workspace and emits a typed workflow IR.
- **Workflow IR**: the local JSON contract used by the server, canvas, and adapters.
- **Local server**: serves the browser UI against one explicit workspace.
- **Canvas UI**: lets a human inspect and edit the workflow.
- **Pending requests**: durable Markdown and JSON change requests generated from canvas edits.
- **Adapters**: optional prompt or tool wrappers that hand pending requests to different agents.

## Agent-Agnostic Adapter Model

AgentCanvas does not require a Codex account, Claude account, Cursor install, or Antigravity install. Those tools are optional consumers of the same local request files.

An adapter can be as small as this:

1. Find `.agentcanvas/pending/*.md`.
2. Ask the agent to implement one request.
3. Point the agent at the matching `.json` file when structured context is useful.
4. Run the project tests.
5. Re-run `agentcanvas index --workspace <workspace>`.

That is the whole model. Deeper integrations can add IDE buttons, terminal commands, or agent-specific prompt templates, but the base workflow stays portable.

See [docs/adapters.md](docs/adapters.md) for small prompt snippets for Codex, Claude Code, Cursor, Antigravity, and generic terminal agents.

## Safety Model

AgentCanvas is local-first and file-based.

- It writes workflow state under `.agentcanvas/`.
- It creates pending requests instead of directly modifying source files.
- It serves a local URL for the selected workspace.
- It keeps agent execution separate from canvas editing.
- It makes implementation requests inspectable before any coding agent acts.

Recommended practice:

- Commit or stash important work before running any agent.
- Review pending requests before implementation.
- Ask before running migrations, seeds, deploys, or other mutating commands.
- Run the smallest relevant test command after each implemented request.
- Re-index after implementation so the canvas reflects the new code.

## Current Limitations

AgentCanvas is early.

- The workflow IR is an approximation, not a complete proof of runtime behavior.
- Large monorepos may need scoped indexing before full-repo indexing is practical.
- Generated requests still need human or agent review.
- Agent adapters are intentionally lightweight prompt/file workflows today.
- The local server is designed for local development, not hosted multi-user collaboration.
- Canvas edits produce requests; they do not automatically patch application code.

## Roadmap

Planned directions:

- richer language and framework indexers
- first-class route, test, job, workflow, and integration nodes
- request status tracking from pending to implemented
- diff previews before handing work to an agent
- adapter packages for popular coding agents and IDEs
- CI/test result overlays on the canvas
- import/export for sharing workflow maps without sharing private code
- stronger schema validation for `workflow.ir.json` and pending request JSON

## Development

Run the current test suite:

```bash
python3 -m unittest discover
```

Useful local loop:

```bash
python3 -m pip install -e .
agentcanvas index --workspace examples/sample-js-app
agentcanvas start --workspace examples/sample-js-app --port 8765
python3 -m unittest discover
python3 scripts/smoke_mvp.py
```

Keep generated workspace state out of source commits unless a fixture is intentional:

```text
.agentcanvas/
```

## Skill Wrapper

The repository includes a standalone skill wrapper at:

```text
skill/agentcanvas/SKILL.md
```

Install or copy that skill into your agent's skill directory if your agent supports skills. The skill tells the agent how to launch AgentCanvas, inspect pending requests, implement a request, run tests, and re-index without assuming Codex-only behavior.
