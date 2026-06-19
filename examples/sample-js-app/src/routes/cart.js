import { addItemToCart } from "../actions/add-to-cart.js";

export const cartRoute = {
  method: "POST",
  path: "/cart/items",
};

export function handleCartRoute(request, cart) {
  if (request.method !== cartRoute.method || request.path !== cartRoute.path) {
    return { status: 404, body: { error: "not found" } };
  }

  return {
    status: 200,
    body: addItemToCart(cart, request.body.item),
  };
}
