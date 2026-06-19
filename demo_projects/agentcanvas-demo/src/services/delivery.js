import { calculateSubtotal } from "./pricing.js";

const SUPPORTED_PREFIXES = ["EC", "N", "NW", "SE", "SW", "W"];

export function checkDeliveryAreaCondition(postcode) {
  const normalized = String(postcode || "").toUpperCase();
  return SUPPORTED_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

export function chooseDeliveryDecision(cart) {
  if (cart.customer.loyaltyTier === "gold") {
    return "priority";
  } else if (calculateSubtotal(cart.items) >= 100) {
    return "free-standard";
  } else {
    return "standard";
  }
}

export function describeDeliveryWindow(deliveryPlan) {
  if (deliveryPlan === "priority") {
    return "today";
  } else if (deliveryPlan === "free-standard") {
    return "2-3 days";
  } else {
    return "3-5 days";
  }
}
