import {
  handleDeliveryDelayedEventAction,
  handleInventoryRestockedEventAction,
} from "../jobs/order-events.js";

export function registerEventRoutes(router) {
  router.post("/events/inventory-restocked", inventoryRestockedRoute);
  router.post("/events/delivery-delayed", deliveryDelayedRoute);
}

export function inventoryRestockedRoute(request) {
  return handleInventoryRestockedEventAction(request.body || {});
}

export function deliveryDelayedRoute(request) {
  return handleDeliveryDelayedEventAction(request.body || {});
}
