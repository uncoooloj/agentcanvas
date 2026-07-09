{header}

{shared_core}

## Codex Notes

- Prefer MCP tools when the user launched AgentCanvas with MCP support.
- If MCP tools are not available, offer MCP enablement before falling back to
  copy/paste. Tell the user Codex can be connected by running
  `agentcanvas setup --agent codex --workspace . --write-codex-config`, explain
  that it writes the global `~/.codex/config.toml`, and ask before doing it.
- After Codex MCP config is written, start a fresh Codex session so the MCP
  server is loaded.
- Otherwise use `agentcanvas pending`, `agentcanvas reply`, `agentcanvas status`,
  `agentcanvas index`, and `agentcanvas canvas apply`.
- Keep this section scoped to AgentCanvas; obey the rest of `AGENTS.md` too.
