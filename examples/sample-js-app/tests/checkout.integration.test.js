import { handleCartRoute } from "../src/routes/cart.js";
import { handleCheckoutRoute } from "../src/routes/checkout.js";

const emptyCart = { items: [] };

const cartResponse = handleCartRoute(
  {
    method: "POST",
    path: "/cart/items",
    body: {
      item: { sku: "tea", name: "Tea", price: 8, quantity: 2 },
    },
  },
  emptyCart
);

if (cartResponse.status !== 200 || cartResponse.body.items.length !== 1) {
  throw new Error("cart route did not add the item");
}

const summaryResponse = handleCheckoutRoute(
  {
    method: "GET",
    path: "/checkout/summary",
    query: { discountCode: "WELCOME10" },
  },
  cartResponse.body
);

if (summaryResponse.status !== 200 || summaryResponse.body.total !== 14.4) {
  throw new Error("checkout summary route returned the wrong total");
}

const submitResponse = handleCheckoutRoute(
  {
    method: "POST",
    path: "/checkout/submit",
    body: { paymentMethod: "invoice" },
  },
  cartResponse.body
);

if (submitResponse.status !== 202 || submitResponse.body.status !== "submitted") {
  throw new Error("checkout submit route did not submit");
}
