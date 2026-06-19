import { createCheckoutSummary, submitCheckout } from "../checkout.js";

export const checkoutRoutes = [
  { method: "GET", path: "/checkout/summary" },
  { method: "POST", path: "/checkout/submit" },
];

export function handleCheckoutRoute(request, cart) {
  if (request.method === "GET" && request.path === "/checkout/summary") {
    return {
      status: 200,
      body: createCheckoutSummary(cart, request.query || {}),
    };
  }

  if (request.method === "POST" && request.path === "/checkout/submit") {
    return {
      status: 202,
      body: submitCheckout(cart, request.body || {}),
    };
  }

  return { status: 404, body: { error: "not found" } };
}
