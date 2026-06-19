let orderSequence = 1000;

export function submitOrderAction(cart, options = {}) {
  const total = cart.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  return {
    status: "submitted",
    orderId: `order-${orderSequence++}`,
    paymentMethod: options.paymentMethod || "card",
    total: Number(total.toFixed(2)),
  };
}
