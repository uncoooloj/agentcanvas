export function calculateSubtotal(items) {
  return Number(
    items.reduce((total, item) => total + item.price * item.quantity, 0).toFixed(2)
  );
}

export function calculateTotal(items, options = {}) {
  const subtotal = calculateSubtotal(items);
  const deliveryFee = deliveryFeeForPlan(options.deliveryPlan || "standard");
  return Number((subtotal + deliveryFee).toFixed(2));
}

export function deliveryFeeForPlan(deliveryPlan) {
  if (deliveryPlan === "priority") {
    return 12;
  } else if (deliveryPlan === "free-standard") {
    return 0;
  } else {
    return 4.5;
  }
}
