import { sendReturnDecisionMessage } from "./notify-customer.js";

export function requestReturnFlow(input = {}) {
  const request = normalizeReturnRequest(input);

  if (!request.orderId) {
    return {
      status: 400,
      body: { outcome: "rejected", reason: "missing_order" },
    };
  } else if (request.daysSinceDelivery > 30) {
    return {
      status: 202,
      body: {
        outcome: "manual_review",
        message: sendReturnDecisionMessage(request, "Needs support review"),
      },
    };
  } else if (request.reason === "damaged") {
    return {
      status: 201,
      body: {
        outcome: "replacement_created",
        message: sendReturnDecisionMessage(request, "Replacement approved"),
      },
    };
  } else {
    return {
      status: 201,
      body: {
        outcome: "refund_created",
        message: sendReturnDecisionMessage(request, "Refund approved"),
      },
    };
  }
}

export function normalizeReturnRequest(input = {}) {
  return {
    orderId: input.orderId || "",
    reason: input.reason || "changed_mind",
    daysSinceDelivery: Number(input.daysSinceDelivery || 0),
    customerEmail: input.customerEmail || "guest@example.test",
  };
}
