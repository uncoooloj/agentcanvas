# Demo Mode

Demo mode is the safe way to try AgentCanvas without pointing it at your own
repo.

It should feel like the real product, not a fake frontend mock. It should also
be clearly labeled so nobody mistakes it for their workspace.

## How To Start It

Explicit demo:

```bash
agentcanvas start --demo --port 8765
```

No-workspace landing:

```bash
agentcanvas start --port 8765
```

The landing page may offer "Try demo". The direct demo command should skip the
landing page.

## Product Rules

- Demo mode uses a bundled sample project.
- Demo mode runs through the same indexer and server as a real workspace.
- Canvas edits create normal pending requests under the demo workspace.
- Status updates use the same `agentcanvas status` and `/api/status` paths.
- Re-index uses the same `agentcanvas index` and `/api/reindex` paths.
- The source demo fixture stays clean.

## Context Contract

`/api/context` should make demo mode obvious:

```json
{
  "mode": "demo",
  "isDemo": true,
  "demoFixture": "agentcanvas-demo",
  "assistant": "No agent connected"
}
```

If an agent was explicitly supplied, the assistant label can use that agent.
If not, do not imply Codex, Claude Code, Cursor, Antigravity, or any other agent
is attached.

## UI Copy

Use direct labels:

- `Demo mode`
- `No agent connected`
- `Create request`
- `Copy prompt`
- `Open a real workspace`

Avoid labels that imply real work happened:

- `Sent to agent` when no agent received it
- `Working` from a timer
- `Done` before the pending request is marked done

## Fixture Behavior

The bundled fixture should exercise a believable app flow:

- routes
- services
- actions
- events or webhook-like handlers
- tests
- at least one branch path such as `if`, `else if`, and `else`

The demo should teach the loop:

1. inspect the flow
2. create a request
3. copy or hand it to an agent
4. update status
5. re-index

## Implementation Notes

Expected code areas when wiring or reviewing demo mode:

- `agentcanvas/cli.py`: keep `--demo` explicit and keep bare `start` as landing.
- `agentcanvas/server.py`: report demo state through `/api/context`.
- `agentcanvas/indexer.py`: treat the fixture like ordinary source code.
- UI: read `/api/context` and `/api/graph`; do not use hard-coded demo graph
  data when the indexed fixture is available.
- Packaging: include the fixture in source and installed builds.

Manual verification:

```bash
python3 scripts/smoke_mvp.py demo_projects/agentcanvas-demo
```
