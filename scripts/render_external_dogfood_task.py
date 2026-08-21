#!/usr/bin/env python3
"""Render a token-safe external-agent dogfood task."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence


DEFAULT_QUESTION = "Should this change update public files?"
DEFAULT_ANSWER = "No. Keep the evidence in ignored private proof files."


def render_task(args: argparse.Namespace) -> str:
    return f"""# {args.agent_name} {args.workspace_id} Dogfood Task

You are {args.agent_name}. Run one real AgentCanvas full-loop dogfood attempt.

Release matrix fields:

- agent id: `{args.agent_id}`
- matrix workspace id: `{args.workspace_id}`
- attempt: `{args.attempt}`
- workspace: `{args.workspace}`
- AgentCanvas base URL: `$AGENTCANVAS_BASE_URL`
- token header: `X-AgentCanvas-Token: $AGENTCANVAS_TOKEN`
- session id: `{args.session_id}`

Security rules:

- Do not print, save, or summarize `$AGENTCANVAS_TOKEN`.
- Do not put the token in a URL query string. Use the `X-AgentCanvas-Token` header.
- Do not edit public AgentCanvas source files unless this task explicitly says so.
- Do not edit target workspace behavior.

Allowed write areas:

- `{args.private_docs_dir}`
- `{args.proof_dir}`
- `{args.workspace}/.agentcanvas/`

Required full loop:

1. Check `/api/context` and `/api/canvas` for the session. Confirm non-demo workspace mode and real flows.
2. Create a pending request with `POST /api/changes?sessionId={args.session_id}`.
   Use journey `{args.journey_id}` and node `{args.target_node_id}`.
3. Use `python3.9 -m agentcanvas reply` to ask one clarifying question: `{args.question}`
4. Use `python3.9 -m agentcanvas reply` to record this user answer exactly:
   `{args.answer}`
5. Run the verification command: `{args.workspace_verification_command}`
6. Mark the pending request `implemented`.
7. Reindex through `POST /api/reindex?sessionId={args.session_id}`.
8. Mark the pending request `verified` with evidence.
9. Mark it `done`.
10. Fetch `/api/pending/<id>?sessionId={args.session_id}` and confirm status `done`.
11. Add a private note at `{args.private_note_path}`.
12. Append a run row to `{args.matrix_path}`.
13. Create proof files under `{args.proof_dir}` using schema `agentcanvas.dogfood_proof.v1`.

Before finishing, run:

```bash
python3.9 scripts/verify_dogfood_proof.py {args.proof_dir}/proof.json
python3.9 scripts/verify_dogfood_matrix.py --details {args.matrix_path}
```

Return:

- pending id
- files changed
- verification commands and results
- any blocker
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a token-safe external-agent dogfood task.")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--journey-id", required=True)
    parser.add_argument("--target-node-id", required=True)
    parser.add_argument("--proof-dir", required=True)
    parser.add_argument("--private-docs-dir", default="docs/private")
    parser.add_argument("--private-note-path", required=True)
    parser.add_argument("--matrix-path", default="docs/private/release-matrix.local.json")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--answer", default=DEFAULT_ANSWER)
    parser.add_argument("--workspace-verification-command", default="python3.9 -m compileall .")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    text = render_task(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
