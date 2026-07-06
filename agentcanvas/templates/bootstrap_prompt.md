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

- `PORT_BUSY`: rerun `agentcanvas up` with a wider `--port-end`.
- `NON_LOOPBACK_HOST`: use the default localhost host.
- `READY_TIMEOUT`: read `.agentcanvas/server.log`, fix the startup issue, then
  rerun `agentcanvas up`.
- `TOKEN_INVALID` or HTTP 401: rerun `agentcanvas up --json` and use the fresh
  URL it returns.
- Missing workspace evidence: run `agentcanvas index --workspace
  $workspace_shell`.

Keep visible canvas text in plain English for non-technical readers. Preserve
evidence refs where possible, keep file paths and framework jargon out of
visible titles, and ask clarifying questions before executing edits when scope,
expected behavior, acceptance criteria, verification, or safety permissions are
unclear.
