# Agent Adapters

AgentCanvas adapters are optional. The stable contract is the local file set:

```text
<workspace>/.agentcanvas/workflow.ir.json
<workspace>/.agentcanvas/pending/*.md
<workspace>/.agentcanvas/pending/*.json
```

An adapter only needs to help an agent read one pending request, implement it, run tests, and re-index the workspace.

## Codex

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, choose the request I name, read both the .md and matching .json if present, implement the requested change, run the relevant tests, then run agentcanvas index --workspace . so the canvas is current again. Do not assume AgentCanvas requests are already verified; treat them like implementation specs.
```

## Claude Code

```text
Please work from the AgentCanvas pending request in .agentcanvas/pending. Read the Markdown request first, use the JSON file for structured context, make the smallest code change that satisfies the request, run the project tests that cover it, and re-run agentcanvas index --workspace . when finished.
```

## Cursor

```text
Implement the AgentCanvas request in .agentcanvas/pending/<request>.md. Use the matching JSON file for node IDs, affected files, and acceptance criteria. Keep the change focused, run the relevant tests, and re-index with agentcanvas index --workspace . after the code is updated.
```

## Antigravity

```text
Use .agentcanvas/pending/<request>.md as the task brief and .agentcanvas/pending/<request>.json as structured context. Apply the request in this repo, verify it with the closest available test or smoke check, then refresh AgentCanvas with agentcanvas index --workspace ..
```

## Generic Terminal Agent

```text
You are implementing one AgentCanvas request. List .agentcanvas/pending, read the selected .md file and matching .json file, edit the repo to satisfy the acceptance criteria, run the relevant tests, and run agentcanvas index --workspace . before summarizing the result.
```

## Adapter Guidelines

- Keep adapters optional.
- Prefer the Markdown request as the human-readable source.
- Use JSON for structured metadata, affected nodes, and acceptance criteria.
- Do not require a specific agent vendor.
- Do not let adapters bypass project safety rules.
- Re-index after implementation so the canvas catches up with the code.
