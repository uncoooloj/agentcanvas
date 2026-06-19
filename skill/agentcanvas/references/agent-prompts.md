# Agent Prompt Snippets

Use these only when a user wants to copy an AgentCanvas request into a specific
coding agent. The base workflow does not depend on any adapter.

Always keep the status loop in the prompt: read request, implement, verify,
re-index, update status.

## Codex

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md and matching .json, implement the request, run the relevant tests, update the request status, then run agentcanvas index --workspace . before summarizing what changed.
```

## Claude Code

```text
Work from the AgentCanvas request in .agentcanvas/pending. Read the Markdown brief first, use the JSON for structured context, make the smallest code change that satisfies the request, run the closest relevant tests, update status, and re-index with agentcanvas index --workspace ..
```

## Cursor

```text
Implement .agentcanvas/pending/<request>.md. Use the matching JSON for affected files, workflow node IDs, and acceptance criteria. Keep the edit focused, verify it, update status, and run agentcanvas index --workspace . after implementation.
```

## Antigravity

```text
Use .agentcanvas/pending/<request>.md as the task brief and .agentcanvas/pending/<request>.json as structured context. Apply the request, run a relevant test or smoke check, update status, then refresh AgentCanvas with agentcanvas index --workspace ..
```

## Generic Terminal Agent

```text
List .agentcanvas/pending, read the selected .md and matching .json, implement the acceptance criteria, run the relevant tests, update status, and re-run agentcanvas index --workspace . before reporting the result.
```

## Copy Fallback Template

```text
Use AgentCanvas for this workspace:
<workspace>

Implement this pending request:
<pending-md>

Use this structured context if useful:
<pending-json>

Read the request, inspect the current repo state, make the smallest change that satisfies the acceptance criteria, run the relevant test or smoke check, re-index with agentcanvas index --workspace <workspace>, then mark the request done with agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified."
```
