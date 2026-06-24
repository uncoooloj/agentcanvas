# AgentCanvas

[![PyPI](https://img.shields.io/pypi/v/use-agentcanvas.svg)](https://pypi.org/project/use-agentcanvas/)
[![Python](https://img.shields.io/pypi/pyversions/use-agentcanvas.svg)](https://pypi.org/project/use-agentcanvas/)

AgentCanvas is a local visual workspace for giving coding agents a better map
of the work.

It looks at a repo, keeps the raw evidence in one file, and lets the invoking
agent turn the important app behavior into a plain-language canvas. You can then
edit the canvas as the shared plan, or explicitly ask for source-code changes
when implementation is the goal.

The point is simple: stop handing agents vague chat messages and hoping they
guess correctly. AgentCanvas makes the work visible, copyable, and trackable.

## What It Does

AgentCanvas helps with the messy part between "this flow is wrong" and "make
this exact code change."

- It indexes your repo into `.agentcanvas/workflow.ir.json`.
- It lets the invoking agent turn that evidence into readable flows in
  `.agentcanvas/canvas.ir.json`.
- It shows the display canvas from `.agentcanvas/canvas.ir.json`.
- It lets you add, remove, rename, or re-route canvas steps without changing
  source code.
- It creates implementation requests only when you explicitly ask for source
  changes.
- A coding agent can read an implementation request, change code, verify it,
  update status, and re-index to refresh evidence.

AgentCanvas is not trying to replace Codex, Claude Code, Cursor, Antigravity, or
any other coding agent. It is the layer that makes the task clear before an
agent starts editing.

## Screenshots

Landing mode:

![AgentCanvas landing page](https://raw.githubusercontent.com/uncoooloj/agentcanvas/main/docs/assets/agentcanvas-landing.png)

Demo mode:

![AgentCanvas demo flows](https://raw.githubusercontent.com/uncoooloj/agentcanvas/main/docs/assets/agentcanvas-demo-flows.png)

## How It Works

The core loop is intentionally small:

1. Point AgentCanvas at a workspace.
2. It writes the raw evidence index to `.agentcanvas/workflow.ir.json`.
3. The invoking agent translates repo behavior into readable flows and writes
   `.agentcanvas/canvas.ir.json`.
4. The browser shows `.agentcanvas/canvas.ir.json` as the display canvas.
5. Canvas-only edits update `.agentcanvas/canvas.ir.json` progressively.
6. If you ask for source-code changes, AgentCanvas creates a Markdown brief and
   a JSON brief in `.agentcanvas/pending/`.
7. A coding agent picks up that implementation request, verifies the change, and
   marks it `in_progress`, `needs_input`, `blocked`, or `done`.
8. The agent re-indexes after source-code implementation to refresh evidence.

Canvas edits are plan edits unless you explicitly ask to change source code.
Re-indexing refreshes evidence; it is not required after canvas-only edits.

## Install

Install AgentCanvas from PyPI:

```bash
python3 -m pip install --upgrade use-agentcanvas
```

Then check the CLI:

```bash
agentcanvas --help
```

The package name is `use-agentcanvas`, but the command is `agentcanvas`.

The public package page is
[pypi.org/project/use-agentcanvas](https://pypi.org/project/use-agentcanvas/).

For development, install from the source repo:

```bash
gh repo clone uncoooloj/agentcanvas
cd agentcanvas
python3 -m pip install -e .
```

You can also install directly from GitHub:

```bash
python3 -m pip install "use-agentcanvas @ git+https://github.com/uncoooloj/agentcanvas.git"
```

When working from a source checkout, prefer the module form for local checks so
you do not accidentally run an older globally installed `agentcanvas` command:

```bash
python3 -m agentcanvas --help
```

## Run It

Start with the landing page when you do not have a workspace selected yet:

```bash
agentcanvas start --port 8765
```

Try the bundled demo project:

```bash
agentcanvas start --demo --port 8765
```

Use a real workspace:

```bash
agentcanvas index --workspace /path/to/your/project
agentcanvas start --workspace /path/to/your/project --port 8765
```

Open the printed URL, usually:

```text
http://127.0.0.1:8765
```

If an agent is launching AgentCanvas, it can pass its name and session id:

```bash
agentcanvas start --workspace /path/to/your/project --agent codex --session-id <session-id>
```

## What Happens When It Starts

AgentCanvas has three startup states. The difference is where the project facts
come from and where AgentCanvas writes its local files.

- **No workspace yet**: `agentcanvas start` opens a landing page. It has not
  read your repo and it should not pretend it has. Pick a real workspace or try
  the demo.
- **Demo mode**: `agentcanvas start --demo` opens a bundled sample project. It
  uses the real indexer, server, pending-request files, and status loop, but the
  files belong to the sample project. The UI should keep saying `Demo mode` so
  nobody mistakes it for their own repo.
- **Workspace mode**: `agentcanvas start --workspace /path/to/project` works
  inside that project. AgentCanvas writes its state under
  `<workspace>/.agentcanvas/`, reads repo evidence from there, and shows the
  canvas for that workspace.

Starting or indexing a workspace does not change source code. It creates or
refreshes AgentCanvas files. Source-code changes only happen later, when the
user explicitly asks for implementation and an agent works from a pending
request.

See [docs/demo-mode.md](docs/demo-mode.md) for the product rules.

## Workspace Mode

Workspace mode is the real use case. It means "map this project, keep the map
beside the project, and let agents use that map before they edit code."

AgentCanvas writes all local state under the selected repo:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/canvas.ir.json
<workspace>/.agentcanvas/pending/*.md
<workspace>/.agentcanvas/pending/*.json
```

`workflow.ir.json` is the raw index and evidence grounding file.
`canvas.ir.json` is the browser display canvas source of truth. Pending
Markdown and JSON files are for implementation requests, not normal canvas-only
edits.

The invoking agent authors the display canvas. In plain English:

1. AgentCanvas indexes the repo into `workflow.ir.json`.
2. The agent reads that evidence and asks questions if the intended journey,
   actor, outcome, or source evidence is unclear.
3. The agent writes or updates `canvas.ir.json` with human-readable flows.
4. The browser reads `canvas.ir.json`.
5. Canvas-only edits keep updating `canvas.ir.json`.
6. Explicit implementation requests create pending Markdown and JSON files.

Preserve evidence links where possible, and use plain language over file
inventory language. A person should see what the project does, not just which
files exist.

## Send Changes To A Coding Agent

Use this loop only when the user explicitly wants source-code implementation.
Canvas edits like "add this step", "remove that branch", or "re-route this flow"
should update `.agentcanvas/canvas.ir.json` instead.

An agent can list pending requests:

```bash
agentcanvas pending --workspace /path/to/your/project
```

When it starts:

```bash
agentcanvas status --workspace /path/to/your/project <pending-id> --status in_progress
```

When it needs the user before it can safely continue:

```bash
agentcanvas status --workspace /path/to/your/project <pending-id> --status needs_input --note "Should this apply only to checkout, or to every order flow?"
```

When it is blocked:

```bash
agentcanvas status --workspace /path/to/your/project <pending-id> --status blocked --note "I need access to the missing service config before continuing."
```

When it has implemented and verified the change:

```bash
agentcanvas index --workspace /path/to/your/project
agentcanvas status --workspace /path/to/your/project <pending-id> --status done --note "Implemented and verified."
```

`agentcanvas index` refreshes `.agentcanvas/workflow.ir.json` after code changes.
It should not be treated as the way to save canvas-only edits.

The important part is that status comes from the agent or CLI. The browser
should not pretend work happened.

## The Clarification Loop

Agents should not guess when the request is unclear.

Before execution, the agent should read the pending Markdown and JSON, check the
current workspace state, and decide whether the request is specific enough. If
not, it should mark the request `needs_input` with one clear question. That
question flows back to the user instead of becoming a random code change.

That loop matters because the product is not just "send work to an agent." It is
"send clear work, let the agent ask before it edits, then track what actually
happened."

## Copy-Prompt Fallback

Copy mode is a core feature, not a backup plan.

If no live agent or adapter is connected, AgentCanvas still creates the pending
files for implementation requests and shows a clean prompt the user can paste
into any coding agent. The prompt includes the workspace, pending file paths,
acceptance details, status commands, and the reminder to test and re-index after
code changes.

This keeps AgentCanvas useful before deeper integrations exist. The copy prompt
should also remind the receiving agent to inspect the current workspace and ask
one clear question before editing if the requested change, affected flow,
acceptance criteria, or verification path is unclear.

## Agent-Agnostic By Design

AgentCanvas should work with any coding agent.

Current and planned integration paths:

- **Skill**: install `skill/agentcanvas/` into an agent that supports skills.
- **Local API**: the browser/server path uses `/api/context`, `/api/graph`,
  `/api/pending`, `/api/changes`, `/api/status`, and `/api/reindex`.
- **MCP**: planned tool path for agents that prefer structured tools over shell
  commands.
- **Webhooks**: planned callback path for outside tools to report status,
  questions, or completion.
- **Copy prompt**: always available, even with no adapter installed.

The file contract stays the same across all of them: `workflow.ir.json` grounds
the repo evidence, `canvas.ir.json` is the display canvas, and pending files are
for explicit implementation requests.

See [docs/adapters.md](docs/adapters.md) for adapter notes and prompt snippets.

## Language And Monorepo Support

AgentCanvas treats LLM- or agent-authored maps as the primary experience.
Parsers and indexers are helpers: they collect grounded facts, file paths, and
evidence so an agent can write a better plain-English canvas.

That posture is intentional. A parser can find routes, branches, functions, and
files. It should not be expected to perfectly understand the whole product by
itself. The agent-authored canvas is where the project becomes readable.

Built-in MVP language modules:

- JavaScript and TypeScript
- Python
- Go
- PHP/Laravel
- Ruby/Rails
- Dart/Flutter
- Swift
- Kotlin

The goal is not to perfectly compile every language on day one. The goal is to
collect honest facts with paths and evidence, then let the projection layer or
invoking agent turn those facts into a canvas a person can read. Stronger
parsers are welcome when they improve grounding, speed, or evidence quality, but
they are optimizations around the same agent-authored workflow.

For monorepos, AgentCanvas keeps app surfaces separate instead of flattening
everything into one generic graph. A repo with `apps/customer-web`,
`apps/admin`, and `services/api` should keep those surfaces visible.

See [docs/language-support.md](docs/language-support.md) for the language module
contract.

## Projection

AgentCanvas can use an LLM or coding agent to turn source facts into a cleaner
human canvas, but the package does not call a model by itself.

The intended flow is:

1. Read `.agentcanvas/workflow.ir.json`, especially `source_facts`, the
   projection contract, and any `app_surfaces`.
2. Ask concise clarifying questions if the intended journey, actor, outcome, or
   evidence is unclear.
3. Generate a human-readable `agentcanvas.canvas_query.v1` using AgentCanvas
   journey language: `When`, `Do`, `If`, `ElseIf`, and `Else`.
4. Cite `fact_ids` on every operation and keep files/tests/services as
   provenance or supporting details, not top-level journeys.
5. Validate, then apply the result to `.agentcanvas/canvas.ir.json`.

If no live model adapter is available, the same prompt can be copied into a
manual agent/model flow. Progressive partial mapping is acceptable when only
some flows are grounded.

Validate a projected canvas first:

```bash
agentcanvas apply-query --workspace /path/to/your/project --query canvas-query.json --dry-run
```

Write only after validation passes:

```bash
agentcanvas apply-query --workspace /path/to/your/project --query canvas-query.json
```

`apply-query` writes the display canvas. It does not overwrite
`.agentcanvas/workflow.ir.json` or replace repo facts.

See [docs/projection.md](docs/projection.md).

## Safety Rules

- Canvas-only edits update `.agentcanvas/canvas.ir.json`.
- AgentCanvas creates requests before source code changes.
- Agents should read the request before editing.
- Agents should ask with `needs_input` when the request is unclear.
- Agents should run the closest relevant test or smoke check.
- Agents should re-index after implementation to refresh evidence.
- Agents should not mark a request `done` until the work is verified.
- Migrations, seeds, deploys, and destructive commands still need explicit user
  permission.

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

## Package And Release Checks

The PyPI package is `use-agentcanvas`. PyPI already has a `0.1.0` release, so a
new publish needs a later version.

Build and validate locally before publishing:

```bash
python3 -m build
python3 -m twine check dist/*.tar.gz dist/*.whl
```

Publish only after the build artifacts pass `twine check` and the GitHub release
state is final:

```bash
python3 -m twine upload dist/*.tar.gz dist/*.whl
```

Publishing requires PyPI credentials for `use-agentcanvas`. This repository does
not store those credentials.
