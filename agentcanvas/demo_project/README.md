# AgentCanvas Demo Project

This is a small bundled project for AgentCanvas demo mode. It is real source code,
not frontend mock data, so the normal indexer can read routes, services, actions,
tests, and event handlers from it.

The project models a simple order desk:

- When someone posts to `POST /orders`, create an order.
- Do cart normalization, delivery-area checks, inventory reservation, pricing,
  customer notification, and fulfillment enqueueing.
- If the cart is empty, reject the order.
- Else if the delivery area is unsupported, ask for a different address.
- Else if inventory is unavailable, put the customer on a waitlist.
- Else if the customer is gold tier, use priority delivery.
- Else create a standard order.

It also includes:

- `GET /orders/:orderId` for lookup.
- `POST /returns` for return decisions.
- `POST /events/inventory-restocked` as a background/event action.
- `POST /events/delivery-delayed` as a customer notification event.
- A no-dependency smoke test in `tests/order-flow.test.js`.

Run the fixture directly:

```bash
npm test
node src/app.js
agentcanvas index --workspace .
```

The demo app intentionally uses plain ES modules and a tiny in-memory router so
it stays portable across machines without installing dependencies.
