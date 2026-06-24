# Product Contract Audit

AgentCanvas should feel quiet and trustworthy.

The user marks work on a canvas. AgentCanvas turns that into a real request.
The agent sees the request, does the work, and reports status back. If no live
agent is connected, the user can copy the request and paste it anywhere.

This document tracks the product contracts behind that story.

## Product Rule

Do not fake agent progress.

If the UI says a request is working, blocked, needs input, or done, that state
must come from one of these contracts:

- a pending request file under `.agentcanvas/pending/`
- a CLI command such as `agentcanvas status`
- a local API call such as `POST /api/status`
- a future MCP tool with the same meaning
- a future webhook with the same meaning

Timers can make the UI feel responsive. They cannot be the source of truth.

## Canvas Source Truth

The browser should say where its readable map came from. Use these product
states consistently:

- **Assistant map**: the map is `.agentcanvas/canvas.ir.json`, written or
  reviewed by an agent or model from repo evidence. Prefer this state.
- **Starter view**: AgentCanvas made a first readable view from indexed evidence
  because no assistant map exists yet.
- **Demo/example**: the map belongs to the bundled sample project, not the
  user's repo.
- **No map yet**: no readable map exists for this workspace yet. Tell the user
  to ask their agent to create the map from `.agentcanvas/workflow.ir.json`.
- **Stale saved map**: the saved assistant map is older than the latest indexed
  evidence. Keep showing it, mark it stale, and ask the agent to refresh it.

Layman copy for the empty state:

> AgentCanvas has read the project, but it has not made the plain-English map
> yet. Ask your coding agent to turn the project notes into the map, then come
> back here.

## P0: No-Workspace Landing

Goal: opening AgentCanvas without a workspace should not drop the user into a
confusing fake project.

Current contract:

- `agentcanvas start` can serve a landing mode.
- `/api/context` can report `mode: "landing"`.
- `agentcanvas start --demo` is the explicit demo path.

Needed user experience:

- Explain that AgentCanvas needs a repo before it can map real work.
- Show the exact command to open a local folder:

```bash
agentcanvas start --workspace /path/to/project --port 8765
```

- Offer demo mode as a clear choice.
- Later, offer GitHub import as another clear choice.

Acceptance:

- A first-time user can tell whether they are on landing, demo, or a real
  workspace.
- The UI does not imply a live agent is connected unless one is.

## P0: Demo Mode

Goal: demo mode should be real enough to teach the product, but clearly marked.

Current contract:

- `agentcanvas start --demo` opens the bundled demo workspace.
- `/api/context` can report `mode: "demo"`, `isDemo: true`, and `demoFixture`.

Needed user experience:

- Show a visible `Demo mode` label.
- Use the same indexing, pending request, status, and re-index paths as a real
  workspace.
- Keep demo files isolated from the source fixture.
- Use neutral copy such as `No agent connected` when no agent/session exists.

Acceptance:

- A request created in demo mode writes to the demo workspace's
  `.agentcanvas/pending/`.
- The UI never suggests the demo request changed the user's own repo.

See [demo-mode.md](demo-mode.md).

## P0: Pending Requests

Goal: a canvas edit becomes a durable request, not a disappearing UI event.

Current contract:

- `POST /api/changes` writes `.agentcanvas/pending/*.md` and `.json`.
- `agentcanvas pending --workspace <workspace>` lists requests.
- `agentcanvas status --workspace <workspace> <pending-id> --status ...`
  updates status.
- `GET /api/pending` returns current requests.
- `POST /api/status` updates status from the local API.

Needed user experience:

- Show the pending request title and status in the handoff UI.
- Make the Markdown request easy to copy.
- Show the structured JSON path for tools.
- Show status history when present.

Acceptance:

- The browser cannot mark a request done unless the pending record says `done`.
- Agents can work entirely from files and CLI commands.

## P0: Agent Polling And Status

Goal: agents should have a boring, reliable loop.

Today the loop is:

```bash
agentcanvas pending --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified."
```

Needed next contract:

- Add `agentcanvas watch --workspace <workspace> [--session-id <id>]` so an
  agent can wait for new or changed requests.
- Add session filtering to `pending`, `watch`, and `status`.
- Keep `needs_input` and `blocked` visible in the canvas.

Acceptance:

- A running agent can poll or watch without guessing where files live.
- A user can see whether the agent has started, needs input, or finished.

## P0: Copy Fallback

Goal: AgentCanvas works even before any live adapter exists.

Current contract:

- Pending requests include human-readable Markdown.
- The handoff overlay can show a copyable prompt.

Needed user experience:

- If there is no connected agent/session, default the primary action to copy.
- Use words like `Copy prompt` or `Create request`, not `Send to agent`.
- The copied text should include:
  - workspace path
  - pending request path
  - matching JSON path
  - acceptance criteria
  - status commands

Acceptance:

- A user can paste the prompt into Codex, Claude Code, Cursor, Antigravity, or a
  generic terminal agent and get the same basic workflow.

## P0: Explicit Integration Paths

AgentCanvas should support four paths without mixing them up.

### Skill Path

Status: started.

Contract:

- `skill/agentcanvas/SKILL.md` teaches an agent how to use AgentCanvas.
- `skill/agentcanvas/references/*.md` holds optional prompt/reference details.
- The skill must stay self-contained and not assume another skill is installed.

Next:

- Keep the skill aligned with this product contract.
- Add examples only when they remove real ambiguity.

### Local API Path

Status: started.

Contract:

- `GET /api/context`: current workspace, mode, assistant, demo flag, session id.
- `GET /api/graph`: current workflow graph.
- `GET /api/pending`: pending requests.
- `POST /api/changes`: create a pending request.
- `POST /api/status`: update request status.
- `POST /api/reindex`: re-index the workspace.

Next:

- Document request/response shapes once they stabilize.
- Keep token checks on local API calls.

### MCP Path

Status: planned.

Contract should map to the same actions:

- `agentcanvas.get_context`
- `agentcanvas.list_pending`
- `agentcanvas.create_request`
- `agentcanvas.update_status`
- `agentcanvas.reindex`

MCP should not invent a second workflow. It should expose the same local state
agents already use through files, CLI, and API.

### Webhooks Path

Status: planned.

Contract should allow outside systems to report back:

- request started
- request needs input
- request blocked
- request done
- CI/test result attached
- reply/note added

Webhooks should update pending records. They should not directly edit source
files.

## P1: Session Binding

Goal: the browser and an agent can talk about the same work session.

Current contract:

- `agentcanvas start --session-id <id>` appends `sessionId` to the URL.
- `/api/context` accepts `sessionId` or `session_id`.
- Pending requests created through the UI can include the session id.

Needed:

- Add `--session-id` to `pending`, `watch`, and `status`.
- Show the active session id in an inspectable place.
- Include session id in copy prompts when present.

## P1: Replies And Threads

Goal: an agent can ask a question without losing the request.

Current contract:

- `status_history` exists in pending JSON when status changes.
- A latest `note` can be stored.

Needed:

- Add `thread: [{role, body, created_at}]`.
- Add `agentcanvas reply <pending-id> --message ...`.
- Add `/api/reply`.
- Render the thread in the handoff panel.

## P1: Projection

Goal: use agents or LLMs to turn grounded code facts into a human-readable
canvas, while validating before writing.

Current contract:

- The indexer can emit `source_facts.v1`.
- The projection contract can produce `canvas_query.v1`.
- `agentcanvas apply-query --query <file> --dry-run` validates before writing.

Needed:

- Store raw facts and projected canvas separately.
- Add projection status: `not_projected`, `projecting`, `projected`,
  `projection_failed`.
- Add a command that prints/copies the projection prompt.

See [projection.md](projection.md).

## P1: GitHub Import

Goal: a user can start from a repo URL, not only a local path.

Needed contract:

- Public repo clone path.
- Private repo auth failure path.
- Branch selection.
- Clone destination.
- Copyable fallback commands when the app cannot do it directly.

## P2: Search And Scale

Goal: search should cite real indexed evidence.

Needed contract:

- `/api/search?q=...` over workflow IR, source facts, and pending requests.
- Results include labels, files, and evidence.
- Frontend search uses the API rather than only local UI text.

## Product Voice

Use plain words:

- `Create request`
- `Copy prompt`
- `Agent started`
- `Needs input`
- `Blocked`
- `Done`
- `Demo mode`
- `No agent connected`

Avoid magic words:

- `Sent` when nothing received it
- `Working` from a timer
- `All set` before verification
- agent-specific names when no agent is connected
