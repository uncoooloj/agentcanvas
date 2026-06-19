import assert from "node:assert/strict";
import { handleRequest, router } from "../src/app.js";
import { getInventorySnapshot } from "../src/services/inventory.js";

const routePaths = router.routes.map((route) => `${route.method} ${route.path}`);
assert.deepEqual(routePaths, [
  "POST /orders",
  "GET /orders/:orderId",
  "POST /returns",
  "POST /events/inventory-restocked",
  "POST /events/delivery-delayed",
]);

const emptyCart = handleRequest("POST", "/orders", {
  body: {
    deliveryPostcode: "EC1A 1AA",
    items: [],
  },
});
assert.equal(emptyCart.status, 400);
assert.equal(emptyCart.body.reason, "cart_empty");

const unsupportedArea = handleRequest("POST", "/orders", {
  body: {
    deliveryPostcode: "ZZ1 1AA",
    items: [{ sku: "tea", price: 8, quantity: 1 }],
  },
});
assert.equal(unsupportedArea.status, 422);
assert.equal(unsupportedArea.body.outcome, "needs_address");

const unavailableItem = handleRequest("POST", "/orders", {
  body: {
    deliveryPostcode: "EC1A 1AA",
    items: [{ sku: "notebook", price: 6, quantity: 1 }],
  },
});
assert.equal(unavailableItem.status, 409);
assert.deepEqual(unavailableItem.body.missingItems, ["notebook"]);

const createdOrder = handleRequest("POST", "/orders", {
  body: {
    customer: { email: "ada@example.test", loyaltyTier: "gold" },
    deliveryPostcode: "NW1 6XE",
    items: [{ sku: "tea", price: 8, quantity: 2 }],
  },
});
assert.equal(createdOrder.status, 201);
assert.equal(createdOrder.body.order.deliveryPlan, "priority");
assert.equal(createdOrder.body.notification.template, "order-confirmation");
assert.equal(createdOrder.body.background.queue, "fulfillment");

const orderLookup = handleRequest("GET", `/orders/${createdOrder.body.order.id}`);
assert.equal(orderLookup.status, 200);
assert.equal(orderLookup.body.id, createdOrder.body.order.id);

const returnRequest = handleRequest("POST", "/returns", {
  body: {
    orderId: createdOrder.body.order.id,
    reason: "damaged",
    daysSinceDelivery: 4,
    customerEmail: "ada@example.test",
  },
});
assert.equal(returnRequest.status, 201);
assert.equal(returnRequest.body.outcome, "replacement_created");

const restockEvent = handleRequest("POST", "/events/inventory-restocked", {
  body: { sku: "notebook", quantity: 3 },
});
assert.equal(restockEvent.status, 202);
assert.equal(getInventorySnapshot().notebook, 3);
assert.equal(restockEvent.body.background.job, "notify-waitlisted-customers");

const delayEvent = handleRequest("POST", "/events/delivery-delayed", {
  body: {
    orderId: createdOrder.body.order.id,
    customerEmail: "ada@example.test",
    newWindow: "tomorrow morning",
  },
});
assert.equal(delayEvent.status, 202);
assert.equal(delayEvent.body.notification.template, "delivery-delay");
