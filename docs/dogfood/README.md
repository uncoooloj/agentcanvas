# AgentCanvas Dogfood Evidence

AgentCanvas should only claim an agent or workspace works when there is proof, not vibes.

There are two evidence files:

- `proof-manifest.schema.json` describes one replayable run: workspace, pending request, clarification transcript, verification command, and recorded proof.
- `matrix-manifest.schema.json` describes the release grid: which agents we publicly claim, which workspaces gate release, and which proof runs cover each pair.

See `release-runbook.md` for the full release checklist and
`release-matrix.template.json` for a public matrix starter that does not include
private recordings or circle-user notes.

Validate one proof manifest:

```bash
python3.9 scripts/verify_dogfood_proof.py tests/fixtures/dogfood-proof/manifest.valid.json
```

Generate and validate one local proof attempt:

```bash
python3.9 scripts/run_dogfood_attempt.py /path/to/workspace --proof-dir /path/to/private/proof-folder
```

Generate a token-safe task for a real external agent run:

```bash
python3.9 scripts/render_external_dogfood_task.py \
  --agent-id claude-code \
  --agent-name "Claude Code" \
  --workspace-id fastapi-service \
  --attempt 1 \
  --workspace /path/to/workspace \
  --session-id claude-code-fastapi-1 \
  --journey-id route:post--signup-app-main.py \
  --target-node-id route:post--signup-app-main.py:1:do \
  --proof-dir /path/to/private/proof-folder \
  --private-note-path /path/to/private-note.md
```

The rendered task references `$AGENTCANVAS_BASE_URL` and
`$AGENTCANVAS_TOKEN` instead of embedding live server tokens in prompts.

Validate matrix shape without claiming release readiness:

```bash
python3.9 scripts/verify_dogfood_matrix.py tests/fixtures/dogfood-matrix/matrix.partial.json
```

Print every missing release-gate pair while a matrix is still incomplete:

```bash
python3.9 scripts/verify_dogfood_matrix.py --details path/to/release-matrix.json
```

For dashboards, handoffs, or release notes, emit the same result as JSON:

```bash
python3.9 scripts/verify_dogfood_matrix.py --json path/to/release-matrix.json
```

Run the release gate:

```bash
python3.9 scripts/verify_release.py --dogfood-matrix path/to/release-matrix.json --require-dogfood-gate
```

The gate requires every `public_claim=true` agent to have two consecutive clean `full_loop` runs on every `gate=true` workspace. Interim narrow-loop runs are useful for early feedback, but they do not satisfy the release gate. The checked-in partial fixture is intentionally incomplete so CI can test the validator without pretending the dogfood matrix is finished.
