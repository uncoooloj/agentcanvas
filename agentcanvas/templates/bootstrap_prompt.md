Use AgentCanvas for this workspace:
$workspace

Calling agent: $agent_label.

AgentCanvas is agent-agnostic. Use it as the local workflow canvas and evidence
handoff for this project; do not assume a specific coding-agent vendor or UI.

Use the smallest setup path that works in your environment:

```bash
uvx --from use-agentcanvas agentcanvas setup --agent $agent_setup_arg --workspace $workspace_shell
uvx --from use-agentcanvas agentcanvas up --workspace $workspace_shell --agent $agent_setup_arg --json
```

If you want a persistent local install instead, use:

```bash
uv tool install use-agentcanvas
agentcanvas setup --agent $agent_setup_arg --workspace $workspace_shell
agentcanvas up --workspace $workspace_shell --agent $agent_setup_arg --json
```

If `uv` is unavailable and your harness allows Python package installs, install
the package named `use-agentcanvas`:

```bash
pip install use-agentcanvas
agentcanvas setup --agent $agent_setup_arg --workspace $workspace_shell
agentcanvas up --workspace $workspace_shell --agent $agent_setup_arg --json
```

These commands write only inside `.agentcanvas/` and agent-specific instruction
files; the web server binds to localhost only. Do not bypass your harness's
permission prompts. Explain each install/run request before asking the user to
approve it.

After launch, relay the JSON `url` to the user so they can open the canvas. Then
start with read-only context:

```bash
agentcanvas health --workspace $workspace_shell
agentcanvas pending --workspace $workspace_shell
```

Read `$workflow_relative_path` for workspace evidence when it exists. Read
`$canvas_relative_path` for the stored canvas when it exists. The canvas file is
stored at:

$canvas_path

While you are indexing or mapping flows, keep the UI honest by recording durable
progress:

```bash
agentcanvas progress --workspace $workspace_shell --stage surveying --message "Reviewing entry points"
```

If you are using MCP, call `agentcanvas_record_progress` with the same stage,
message, and optional current/total counts.

If workflow evidence is missing and the user asked you to initialize or refresh
AgentCanvas, run:

```bash
agentcanvas index --workspace $workspace_shell
```

For canvas-only authoring or repair, do not hand-edit
`$canvas_relative_path`. Read the current revision, create a canvas v2 operation
batch, then apply it through:

```bash
agentcanvas canvas apply --workspace $workspace_shell --base-revision <revision> --input <ops.json>
```

For source-code implementation requests, work from `.agentcanvas/pending`.
Inspect the Markdown request and matching JSON, clarify anything ambiguous,
make the smallest focused code change, verify it, then re-index so workflow
evidence matches the implementation.

If launch fails, use the structured error:

- `uv_missing`: install uv, or use the pip fallback above.
- `install_failed`: retry with the package named `use-agentcanvas` and inspect
  the package-manager error.
- `port_busy`: rerun `agentcanvas up` with a wider `--port-end`.
- `token_invalid` or HTTP 401: rerun `agentcanvas up --json` and use the fresh
  URL it returns.
- `server_not_running`: run `agentcanvas up --json` for this workspace.
- `agent_stalled`: check `.agentcanvas/progress.json` and resume from the latest
  progress stage.
- `workspace_unindexed`: run `agentcanvas index --workspace
  $workspace_shell`.
- `canvas_invalid`: validate the canvas and repair it through
  `agentcanvas canvas apply`.
- `NON_LOOPBACK_HOST`: use the default localhost host.
- `READY_TIMEOUT`: read `.agentcanvas/server.log`, fix the startup issue, then
  rerun `agentcanvas up`.

Keep visible canvas text in plain English for non-technical readers. Preserve
evidence refs where possible, keep file paths and framework jargon out of
visible titles, and ask clarifying questions before executing edits when scope,
expected behavior, acceptance criteria, verification, or safety permissions are
unclear.
