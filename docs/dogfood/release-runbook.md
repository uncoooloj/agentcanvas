# Dogfood Release Runbook

This is the public checklist for proving AgentCanvas before a release. It says
what evidence must exist; it does not contain private recordings, tokens,
workspace paths, or circle-user notes.

## Gate Workspaces

The default public launch claim requires clean full-loop runs on:

1. AgentCanvas itself.
2. A vibe-coded Next.js app.
3. A FastAPI service.

Laravel and small monorepo runs are useful launch confidence, but they are not
gate workspaces until the release matrix marks them with `gate: true`.

## Public Agent Claims

Every agent with `public_claim: true` in the release matrix must pass the gate
for every gate workspace. If an agent cannot pass, either fix the issue or
remove the public claim before release.

## Full-Loop Checklist

Each clean full-loop attempt must cover this path:

1. Paste the AgentCanvas bootstrap prompt into the agent.
2. Open AgentCanvas against the real workspace.
3. Confirm the map shows a loop, a multi-way branch, and a subflow when the
   workspace has those behaviors.
4. Describe a canvas change in plain English.
5. Let AgentCanvas create the pending request.
6. The agent reads the pending request and asks one clarifying question if the
   request is ambiguous.
7. Record the answer.
8. The agent implements the smallest focused change.
9. The agent runs a relevant verification command.
10. The agent marks the request `verified` or `done` with evidence.
11. Re-index and confirm the map updates or explain why no source-map change was
    expected.

## What To Record

For each attempt, record:

- agent id
- workspace id
- attempt number
- `loop: full_loop`
- runbook id
- permission prompt count
- triage class: `none`, `a`, `b`, or `c`
- proof manifest path when a replayable proof exists
- recording metadata for raw or public cuts
- issue URL for any failed, blocked, launch-note, or post-launch outcome

Raw recordings and circle-user notes should stay in private storage. Public docs
may link only to redacted/polished cuts.

## Commands

Run one local full-loop proof attempt and write a replayable proof manifest:

```bash
python3.9 scripts/run_dogfood_attempt.py /path/to/workspace \
  --proof-dir /path/to/private/proof-folder \
  --session-id codex-agentcanvas-attempt-3 \
  --change-id codex-agentcanvas-attempt-3
```

The runner starts AgentCanvas against the workspace, creates a pending request,
uses the clarification loop, answers the question, marks the request verified
with evidence, re-indexes, writes `proof.json` plus `verification.txt`, and then
validates the proof manifest. Store the generated proof folder outside the
public repo or under an ignored private path.

For a real external-agent run, render a token-safe handoff task instead of
pasting a live launch URL into the prompt:

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
  --private-note-path /path/to/private-note.md \
  --output /path/to/private-task.md
```

The task uses `$AGENTCANVAS_BASE_URL` and `$AGENTCANVAS_TOKEN`. Pass those as
local environment variables to the external agent process and instruct the
agent to use the `X-AgentCanvas-Token` header, not a tokenized URL.

Validate the public template shape:

```bash
python3.9 scripts/verify_dogfood_matrix.py docs/dogfood/release-matrix.template.json
```

While filling the real release matrix, use the detailed view to see the exact
agent/workspace pairs still missing two consecutive clean full-loop runs:

```bash
python3.9 scripts/verify_dogfood_matrix.py --details path/to/release-matrix.json
```

Use JSON output when another tool or release dashboard needs the same status:

```bash
python3.9 scripts/verify_dogfood_matrix.py --json path/to/release-matrix.json
```

Validate the real release matrix:

```bash
python3.9 scripts/verify_release.py --dogfood-matrix path/to/release-matrix.json --require-dogfood-gate
```

The checked-in partial fixture and template are intentionally incomplete. They
prove the validator shape; they do not prove release readiness.
