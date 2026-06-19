import { createOrderFlow, getOrderSnapshot } from "../actions/create-order.js";

export function registerOrderRoutes(router) {
  router.post("/orders", createOrderRoute);
  router.get("/orders/:orderId", getOrderRoute);
}

export function createOrderRoute(request) {
  return createOrderFlow(request.body || {});
}

export function getOrderRoute(request) {
  const order = getOrderSnapshot(request.params.orderId);

  if (!order) {
    return { status: 404, body: { error: "order_not_found" } };
  }

  return { status: 200, body: order };
}
