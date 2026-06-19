# Agent Adapters

Adapters are optional. The base product is just local files, a small CLI, and a
local API.

The stable file contract is:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/pending/*.md
<workspace>/.agentcanvas/pending/*.json
```

An adapter should do one job: help an agent pick up a pending request, implement
it, verify it, update status, and re-index.

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
3. read `.agentcanvas/pending/*.md`
4. use `.json` for structured context
5. update status with `agentcanvas status`
6. run the relevant tests
7. re-index with `agentcanvas index`

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
`.agentcanvas/`; it should not become a separate source of truth.

### 3. MCP

Use this when an agent prefers tools instead of shell commands or raw HTTP.

MCP is a planned path. It should expose the same simple actions:

- get context
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

Webhook events should update pending records. They should not patch source code.

## Copy Fallback

Copy mode is always valid.

If no adapter is installed and no live session is connected, AgentCanvas should
create the pending request and show a prompt the user can paste into any coding
agent.

The prompt should include:

- workspace path
- selected pending `.md`
- matching `.json`
- acceptance criteria
- status commands
- reminder to test and re-index

## Prompt Snippets

Use these snippets when the user wants to hand a request to a specific agent.

### Codex

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md and matching .json, implement the request, run the relevant tests, update the request status, then run agentcanvas index --workspace . before summarizing what changed.
```

### Claude Code

```text
Work from the AgentCanvas request in .agentcanvas/pending. Read the Markdown brief first, use the JSON for structured context, make the smallest code change that satisfies the request, run the closest relevant tests, update status, and re-index with agentcanvas index --workspace ..
```

### Cursor

```text
Implement .agentcanvas/pending/<request>.md. Use the matching JSON for affected files, workflow node IDs, and acceptance criteria. Keep the edit focused, verify it, update status, and run agentcanvas index --workspace . after implementation.
```

### Antigravity

```text
Use .agentcanvas/pending/<request>.md as the task brief and .agentcanvas/pending/<request>.json as structured context. Apply the request, run a relevant test or smoke check, update status, then refresh AgentCanvas with agentcanvas index --workspace ..
```

### Generic Terminal Agent

```text
List .agentcanvas/pending, read the selected .md and matching .json, implement the acceptance criteria, run the relevant tests, update status, and re-run agentcanvas index --workspace . before reporting the result.
```

## Adapter Rules

- Keep adapters optional.
- Keep files and CLI commands usable without adapters.
- Prefer the Markdown request as the readable source.
- Use JSON for ids, files, node references, and acceptance criteria.
- Do not require a specific agent vendor.
- Do not bypass project safety rules.
- Do not mark work done until implementation and verification happened.
