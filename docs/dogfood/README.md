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
