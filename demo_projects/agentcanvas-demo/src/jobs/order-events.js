import { sendDeliveryDelayAlert } from "../actions/notify-customer.js";
import { restockInventoryAction } from "../services/inventory.js";

export function enqueueFulfillmentJob(order) {
  return {
    job: "pack-and-ship-order",
    orderId: order.id,
    queue: "fulfillment",
    runAfter: "now",
  };
}

export function handleInventoryRestockedEventAction(event = {}) {
  const inventory = restockInventoryAction(event);

  return {
    status: 202,
    body: {
      outcome: "inventory_updated",
      inventory,
      background: {
        job: "notify-waitlisted-customers",
        sku: inventory.sku,
      },
    },
  };
}

export function handleDeliveryDelayedEventAction(event = {}) {
  return {
    status: 202,
    body: {
      outcome: "customer_notified",
      notification: sendDeliveryDelayAlert(event),
    },
  };
}
