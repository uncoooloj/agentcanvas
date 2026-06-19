import { applyDiscount } from "./actions/apply-discount.js";
import { submitOrderAction } from "./actions/submit-order.js";
import { reserveInventory } from "./services/inventory.js";

export function calculateSubtotal(cart) {
  return cart.items.reduce((total, item) => total + item.price * item.quantity, 0);
}

export function submitCheckout(cart, options = {}) {
  if (!cart.items.length) {
    return { status: "empty" };
  }

  const reservation = reserveInventory(cart.items);
  if (reservation.status !== "reserved") {
    return { status: "blocked", reason: reservation.reason };
  }

  const discountedCart = applyDiscount(cart, options.discountCode);
  return submitOrderAction(discountedCart, {
    paymentMethod: options.paymentMethod || "card",
  });
}

export function createCheckoutSummary(cart, options = {}) {
  const discountedCart = applyDiscount(cart, options.discountCode);

  return {
    itemCount: cart.items.length,
    subtotal: calculateSubtotal(cart),
    total: calculateSubtotal(discountedCart),
  };
}
