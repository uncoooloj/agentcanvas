---
name: agentcanvas
description: Launch and use AgentCanvas, a local workflow canvas for AI coding agents. Use when a user wants to map a workspace, inspect or edit workflow logic, generate implementation requests, or consume `.agentcanvas/pending` requests with Codex, Claude Code, Cursor, Antigravity, or a generic terminal agent.
---

# AgentCanvas

Use AgentCanvas to turn a local workspace into an editable workflow canvas and then into agent-ready implementation requests.

AgentCanvas is agent-agnostic. Do not assume Codex-only behavior. The shared contract is the workspace's `.agentcanvas/` directory.

## Basic Workflow

1. Confirm the workspace root with the user or infer it from the current repo.
2. Check the available CLI:

```bash
agentcanvas --help
```

If `agentcanvas` is not installed and this is the AgentCanvas source repo, install it locally:

```bash
python3 -m pip install -e .
```

3. Index the target workspace:

```bash
agentcanvas index --workspace <workspace>
```

4. Start the local canvas:

```bash
agentcanvas start --workspace <workspace> --port 8765
```

5. Open the printed local URL when your environment can open browsers. If you cannot open it, give the URL to the user.
6. After the user edits the canvas, inspect pending requests:

```bash
ls <workspace>/.agentcanvas/pending
```

7. For the selected request, read the `.md` first and the matching `.json` when present.
8. Implement the request in the workspace, keeping the change focused.
9. Run the smallest relevant test or smoke check for the change.
10. Re-index so AgentCanvas reflects the new code:

```bash
agentcanvas index --workspace <workspace>
```

## Pending Request Rules

- Treat `.agentcanvas/workflow.ir.json` as generated canvas state.
- Treat `.agentcanvas/pending/*.md` as implementation briefs.
- Treat `.agentcanvas/pending/*.json` as structured context for tools.
- Do not edit source code just because a canvas node changed; implement only explicit pending requests.
- Do not run migrations, seeds, deploys, or destructive commands without explicit user permission.
- If a request is ambiguous, ask one short question before editing.

## Agent Handoff

Any coding agent can consume a pending request if it can read files, edit code, and run tests. For copy-paste prompt snippets for Codex, Claude Code, Cursor, Antigravity, and generic terminal agents, read `references/agent-prompts.md`.

Keep the base workflow usable even when no other skills, plugins, or adapters are installed.
