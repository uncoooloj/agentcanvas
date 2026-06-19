# Demo Mode

Demo mode is the empty-state path for opening AgentCanvas without an agent and
without a workspace. It should use the bundled real fixture at
`demo_projects/agentcanvas-demo` through the same indexer and server pipeline as
any other workspace. It should not use frontend hard-coded workflow data.

## Trigger

Start demo mode only when no workspace was supplied and no launching agent was
identified.

- No workspace means neither positional `path` nor `--workspace` was provided.
- No agent means no explicit `--agent` and no recognized agent environment hint.
- If a workspace is supplied, index and serve that workspace normally.
- If an agent is supplied but no workspace is supplied, prefer asking for a
  workspace or offering demo mode explicitly instead of silently pretending the
  demo fixture is the agent's project.

## Runtime Behavior

Use a writable copy of the fixture, not frontend mock data.

1. Resolve the bundled fixture path relative to the installed AgentCanvas package
   or repository root.
2. Copy `demo_projects/agentcanvas-demo` into a writable demo workspace, such as
   a cache or temp directory.
3. Run `index_workspace(demo_workspace)` to create
   `.agentcanvas/workflow.ir.json` from the copied source files.
4. Start the normal server against that demo workspace.
5. Let canvas edits write pending requests under the demo workspace's
   `.agentcanvas/pending/` directory.

The demo copy can be reset between launches. The source fixture should stay
pristine so package installs and repository checkouts remain clean.

## Nav Highlight

Demo mode must be visible in the top nav, especially around the pill that
currently shows the assistant.

Recommended behavior:

- Add `isDemo: true` and `demoFixture: "agentcanvas-demo"` to `/api/context`
  when serving the fixture.
- Render a clear `Demo mode` pill adjacent to, or replacing, the assistant pill.
- If no agent is connected, the assistant-area text should say
  `No agent connected` rather than implying Codex, Claude Code, Cursor, or any
  other assistant is active.
- Include the demo workspace name/path in the hover title or secondary context,
  so users can tell generated pending requests are going to the demo copy.
- Use a distinct visual treatment for demo mode, but keep it local and calm:
  this is an orientation state, not an error.

## Fixture Scenarios

The bundled fixture exercises the current AgentCanvas pipeline with:

- Routes: `POST /orders`, `GET /orders/:orderId`, `POST /returns`,
  `POST /events/inventory-restocked`, and `POST /events/delivery-delayed`.
- Services: cart normalization, delivery-area conditions, inventory reservation,
  pricing, and delivery-plan decisions.
- Actions: order creation, customer notification, return decisions, and
  fulfillment queueing.
- Background/event behavior: inventory restock events enqueue a waitlist
  notification job, and delivery delay events send a customer alert.
- Tests: `tests/order-flow.test.js` covers the order branches, return route, and
  event routes without external dependencies.

The order flow intentionally contains When/Do/If/Else If/Else behavior:

- When a shopper posts to `POST /orders`.
- Do normalization, delivery checks, inventory reservation, pricing, customer
  notification, and fulfillment enqueueing.
- If the cart is empty, reject it.
- Else if the delivery area is unsupported, request a different address.
- Else if inventory is unavailable, waitlist the customer.
- Else if the customer is gold tier, create a priority order.
- Else create a standard order.

## Integration Points

Expected code changes when wiring this in:

- `agentcanvas/cli.py`: distinguish an omitted workspace from the current
  default of `"."`, so `agentcanvas start` can enter demo mode only when the
  user truly supplied no workspace.
- `agentcanvas/server.py`: carry demo metadata into `/api/context` and serve the
  normal `/api/graph` response from the indexed demo workspace.
- `agentcanvas/indexer.py`: no special demo behavior should be required. The
  fixture is ordinary source code and should index like any other workspace.
- `frontend/src/App.tsx` and nav/context components: stop using hard-coded demo
  workflow data for the no-workspace path. Read the indexed graph from
  `/api/graph`, read `isDemo` from `/api/context`, and highlight demo mode near
  the assistant pill.
- Packaging: include `demo_projects/agentcanvas-demo` in source distributions
  and installed packages, or copy it from the repository root in editable/dev
  installs.

Manual verification command:

```bash
python3 scripts/smoke_mvp.py demo_projects/agentcanvas-demo
```
