import { normalizeCart } from "../services/cart.js";
import {
  checkDeliveryAreaCondition,
  chooseDeliveryDecision,
  describeDeliveryWindow,
} from "../services/delivery.js";
import { reserveInventory } from "../services/inventory.js";
import { calculateTotal } from "../services/pricing.js";
import { sendOrderConfirmation } from "./notify-customer.js";
import { enqueueFulfillmentJob } from "../jobs/order-events.js";

const orders = new Map();
let nextOrderNumber = 4200;

export function createOrderFlow(input = {}) {
  const cart = normalizeCart(input);

  if (cart.items.length === 0) {
    return rejectOrder("cart_empty", "Add at least one item before checkout.");
  } else if (!checkDeliveryAreaCondition(cart.deliveryPostcode)) {
    return requestAddressFix(cart);
  } else {
    const reservation = reserveInventory(cart.items);

    if (!reservation.available) {
      return waitlistUnavailableItems(cart, reservation);
    } else if (cart.customer.loyaltyTier === "gold") {
      return completeOrder(cart, reservation, "priority");
    } else if (chooseDeliveryDecision(cart) === "free-standard") {
      return completeOrder(cart, reservation, "free-standard");
    } else {
      return completeOrder(cart, reservation, "standard");
    }
  }
}

export function getOrderSnapshot(orderId) {
  return orders.get(orderId) || null;
}

export function rejectOrder(reason, message) {
  return {
    status: 400,
    body: {
      outcome: "rejected",
      reason,
      message,
    },
  };
}

export function requestAddressFix(cart) {
  return {
    status: 422,
    body: {
      outcome: "needs_address",
      deliveryPostcode: cart.deliveryPostcode,
      message: "Choose a supported delivery postcode.",
    },
  };
}

export function waitlistUnavailableItems(cart, reservation) {
  return {
    status: 409,
    body: {
      outcome: "waitlisted",
      missingItems: reservation.missingItems,
      message: "Some items are out of stock. We will notify the customer when they return.",
      customerEmail: cart.customer.email,
    },
  };
}

export function completeOrder(cart, reservation, deliveryPlan) {
  const order = {
    id: `ORDER-${nextOrderNumber++}`,
    customerEmail: cart.customer.email,
    deliveryPostcode: cart.deliveryPostcode,
    deliveryPlan,
    deliveryWindow: describeDeliveryWindow(deliveryPlan),
    reservationId: reservation.reservationId,
    total: calculateTotal(cart.items, { deliveryPlan }),
    items: cart.items,
  };

  orders.set(order.id, order);

  return {
    status: 201,
    body: {
      outcome: "created",
      order,
      notification: sendOrderConfirmation(order),
      background: enqueueFulfillmentJob(order),
    },
  };
}
