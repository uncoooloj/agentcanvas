# Agent Prompt Snippets

Use these only when a user wants to hand an AgentCanvas request to a specific coding agent. The base workflow does not depend on any adapter.

## Codex

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md and matching .json, implement the request, run the relevant tests, then run agentcanvas index --workspace . before summarizing what changed.
```

## Claude Code

```text
Work from the AgentCanvas request in .agentcanvas/pending. Read the Markdown brief first, use the JSON for structured context, make the smallest code change that satisfies the request, run the closest relevant tests, and re-index with agentcanvas index --workspace ..
```

## Cursor

```text
Implement .agentcanvas/pending/<request>.md. Use the matching JSON for affected files, workflow node IDs, and acceptance criteria. Keep the edit focused, verify it, and run agentcanvas index --workspace . after implementation.
```

## Antigravity

```text
Use .agentcanvas/pending/<request>.md as the task brief and .agentcanvas/pending/<request>.json as structured context. Apply the request, run a relevant test or smoke check, then refresh AgentCanvas with agentcanvas index --workspace ..
```

## Generic Terminal Agent

```text
List .agentcanvas/pending, read the selected .md and matching .json, implement the acceptance criteria, run the relevant tests, and re-run agentcanvas index --workspace . before reporting the result.
```
