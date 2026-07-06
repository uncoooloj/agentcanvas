{header}

# AgentCanvas File Contract

AgentCanvas works without a vendor-specific agent. Use these local files:

- `.agentcanvas/workflow.ir.json`
- `.agentcanvas/canvas.ir.json`
- `.agentcanvas/pending/*.md`
- `.agentcanvas/pending/*.json`
- `.agentcanvas/pending/*.conversation.jsonl`

Canvas-only edits update `.agentcanvas/canvas.ir.json` through:

```bash
agentcanvas canvas apply --workspace <workspace> --base-revision <revision> --input <ops.json>
```

Implementation requests live under `.agentcanvas/pending/`. Read the Markdown
brief first, then the JSON. Clarify before editing when the requested change,
affected flow or step, acceptance criteria, or verification path is unclear.

Useful commands:

```bash
agentcanvas health --workspace <workspace>
agentcanvas pending --workspace <workspace>
agentcanvas reply --workspace <workspace> <pending-id> --question "Short question?"
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
```
