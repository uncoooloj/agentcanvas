---
name: agentcanvas
description: Launch and use AgentCanvas, a local workflow canvas for AI coding agents. Use when a user wants to map a workspace, inspect or edit workflow logic, generate implementation requests, consume `.agentcanvas/pending` requests, update request status, use demo/no-workspace mode, or hand work between AgentCanvas and any AI coding agent, MCP tools, APIs, webhooks, or a generic terminal agent.
---

{shared_core}

## Launching The Browser

For a real workspace:

```bash
agentcanvas index --workspace <workspace>
agentcanvas up <workspace> --port 8765
```

For no workspace, the lower-level server command
`agentcanvas start --port 8765` opens the landing page only.

For the bundled sample, the lower-level server command
`agentcanvas start --demo --port 8765` opens demo mode.
Keep saying it is demo mode when the sample project is shown.

## Applying Canvas Edits

Read `.agentcanvas/canvas.ir.json`, get its current `revision`, then apply an
operation batch:

```bash
agentcanvas canvas apply --workspace <workspace> --base-revision <revision> --input <ops.json>
```

Use `allow_rewrite.reason` only for intentional large rewrites. Smaller edits
should preserve ids and provenance.

## Copy Fallback

If MCP or a live adapter is not available, offer agent-specific MCP enablement
before giving the user a copyable prompt. For Codex, say that AgentCanvas can
write the global `~/.codex/config.toml` only after opt-in:

```bash
agentcanvas setup --agent codex --workspace <workspace> --write-codex-config
```

If the user does not opt in, give a copyable prompt that names the workspace,
pending request files, acceptance criteria, status commands, and the
verification expectation.
