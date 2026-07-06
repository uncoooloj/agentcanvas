Use AgentCanvas for this workspace:
$workspace

Calling agent: $agent_label.

AgentCanvas is agent-agnostic. Use it as the local workflow canvas and evidence
handoff for this project; do not assume a specific coding-agent vendor or UI.

If the CLI is not available, install the Python package named `use-agentcanvas`:

```bash
pip install use-agentcanvas
```

Start with read-only context:

```bash
python -m agentcanvas health --workspace $workspace_shell
python -m agentcanvas pending --workspace $workspace_shell
```

Read `$workflow_relative_path` for workspace evidence when it exists. Read
`$canvas_relative_path` for the stored canvas when it exists. The canvas file is
stored at:

$canvas_path

If workflow evidence is missing and the user asked you to initialize or refresh
AgentCanvas, run:

```bash
python -m agentcanvas index --workspace $workspace_shell
```

For canvas-only authoring or repair, do not hand-edit
`$canvas_relative_path`. Read the current revision, create a canvas v2 operation
batch, then apply it through:

```bash
python -m agentcanvas canvas apply --workspace $workspace_shell --base-revision <revision> --input <ops.json>
```

For source-code implementation requests, work from `.agentcanvas/pending`.
Inspect the Markdown request and matching JSON, clarify anything ambiguous,
make the smallest focused code change, verify it, then re-index so workflow
evidence matches the implementation.

Keep visible canvas text in plain English for non-technical readers. Preserve
evidence refs where possible, keep file paths and framework jargon out of
visible titles, and ask clarifying questions before executing edits when scope,
expected behavior, acceptance criteria, verification, or safety permissions are
unclear.
