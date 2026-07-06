# AgentCanvas

AgentCanvas is the shared local workflow canvas for this workspace. Use it to
turn source-code behavior into plain-English journeys, keep the canvas editable,
and create implementation requests only when source-code work is explicitly
needed.

## Start Here

1. Run `agentcanvas --help` to confirm the CLI is available.
2. Call `uvx --from 'use-agentcanvas[mcp]' agentcanvas mcp` tools when your agent supports MCP.
3. If MCP is not available, use the CLI and files under `.agentcanvas/`.
4. Start each turn by checking workspace status and unanswered questions.

Preferred MCP order:

1. `agentcanvas_workspace_status`
2. `agentcanvas_get_answers`
3. `agentcanvas_get_canvas`
4. `agentcanvas_get_evidence`
5. `agentcanvas_record_progress`

CLI fallback:

```bash
agentcanvas health --workspace <workspace>
agentcanvas pending --workspace <workspace>
```

## Local Files

- `.agentcanvas/workflow.ir.json` is raw repo evidence.
- `.agentcanvas/canvas.ir.json` is the stored revisioned canvas.
- `.agentcanvas/pending/*.md` is the readable implementation brief.
- `.agentcanvas/pending/*.json` is structured implementation context.
- `.agentcanvas/pending/*.conversation.jsonl` stores questions, answers, and notes.

## Canvas Rules

- Update canvas-only changes through `agentcanvas canvas apply`.
- Do not edit source code just because a canvas node changed.
- Preserve stable flow, node, and edge ids for unchanged behavior.
- Preserve evidence refs whenever possible.
- Run `record_sync` in the same turn as code changes that alter behavior.
- Use plain-English titles for visible canvas text.
- Keep file paths, API names, framework terms, and schema jargon out of visible titles.

Node kinds:

- `When`: the user, system, time, webhook, job, or event that starts behavior.
- `Do`: something the app does.
- `Decision`: a user-visible or business-rule branch.
- `Loop`: repeated behavior with body and exit paths.
- `Parallel`: independent work that can happen side-by-side.
- `Join`: where parallel paths come back together.
- `Wait`: waiting for time, user input, an external event, or another system.
- `SubFlow`: handoff to another flow.
- `End`: where the flow stops.

## Pending Request Loop

Pending requests are for explicit source-code implementation work.

Before execution mode, confirm:

- the requested change is specific
- the affected flow, step, route, or behavior is identified
- the acceptance criteria are clear
- the verification path is clear

If anything is ambiguous, ask first:

```bash
agentcanvas reply --workspace <workspace> <pending-id> --question "Short plain-language question?"
```

Then wait for an answer. Do not mark unclear work `in_progress`.

When the request is clear:

```bash
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
```

After implementation, verify the change, refresh evidence, and update status:

```bash
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status implemented --note "Implemented."
agentcanvas status --workspace <workspace> <pending-id> --status verified --note "Verified." --evidence-check "<command or smoke test>" --evidence-result "passed" --evidence-actor "<agent name>"
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Done."
```

`verified` always requires evidence. Never mark a request `done` unless the
implementation has actually been verified.

## Safety

- Do not run migrations, seeds, deploys, destructive commands, or production
  mutations without explicit user permission.
- If the workspace contradicts a pending request, ask before editing.
- If no live session is connected, use copy fallback instead of pretending a
  request was sent.
