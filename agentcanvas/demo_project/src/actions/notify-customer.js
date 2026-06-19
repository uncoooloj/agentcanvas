export function sendOrderConfirmation(order) {
  return {
    channel: "email",
    template: "order-confirmation",
    to: order.customerEmail,
    subject: `Order ${order.id} confirmed`,
  };
}

export function sendReturnDecisionMessage(returnRequest, decision) {
  return {
    channel: "email",
    template: "return-decision",
    to: returnRequest.customerEmail,
    decision,
  };
}

export function sendDeliveryDelayAlert(event) {
  return {
    channel: "email",
    template: "delivery-delay",
    to: event.customerEmail || "ops@example.test",
    orderId: event.orderId,
    newWindow: event.newWindow || "tomorrow",
  };
}
