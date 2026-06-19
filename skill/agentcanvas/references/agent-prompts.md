# Agent Prompt Snippets

Use these only when a user wants to copy an AgentCanvas request into a specific
coding agent. The base workflow does not depend on any adapter or vendor.

Always keep the status loop in the prompt: inspect request, inspect workspace
context, clarify if needed, implement only after the request is clear, verify,
re-index, update status.

## Portable Handoff Prompt

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md, and read the matching .json for structured context. Before editing, inspect the current workspace context and confirm four things are clear: the requested change, the affected flow or step, the acceptance criteria, and the verification path.

If any of those are ambiguous, risky, incomplete, or contradicted by the current workspace, do not enter execution mode yet. Ask the fewest useful clarifying questions in plain language, and update the request with needs_input plus the question.

Once the request is clear, mark it in_progress, make the smallest change that satisfies the acceptance criteria, run the agreed test or smoke check, re-index with agentcanvas index --workspace ., update the request status, and summarize what changed and how it was verified.
```

## Short Handoff Prompt

```text
Work from .agentcanvas/pending. Read the Markdown request and matching JSON, inspect the current workspace context, and clarify before editing unless the requested change, affected flow or step, acceptance criteria, and verification path are all clear. If clarification is needed, set status to needs_input with concise plain-language questions. Once clear, mark in_progress, implement the smallest focused change, verify it, re-index, and update status.
```

## Needs-Input Status Note

```text
I need one decision before editing: <short plain-language question about the requested behavior, affected flow or step, acceptance criteria, verification path, or safety permission>.
```

## Status Commands

```bash
agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: <question>"
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified: <test or smoke check>."
```

## Copy Fallback Template

```text
Use AgentCanvas for this workspace:
<workspace>

Implement this pending request:
<pending-md>

Use this structured context if useful:
<pending-json>

Before editing, inspect the request and current workspace context. Only start implementation once these are clear:

- requested change
- affected flow or step
- acceptance criteria
- verification path

If anything is unclear, risky, incomplete, or contradicted by the workspace, ask concise plain-language questions and mark the request needs_input:

agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: <question>"

Once clear, mark the request in_progress, make the smallest change that satisfies the acceptance criteria, run the relevant test or smoke check, re-index with agentcanvas index --workspace <workspace>, then mark the request done:

agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified: <test or smoke check>."
```
