import { createCheckoutSummary, submitCheckout } from "./src/checkout.js";

const cart = {
  items: [{ sku: "tea", name: "Tea", price: 8, quantity: 2 }],
};

if (submitCheckout(cart).status !== "submitted") {
  throw new Error("checkout did not submit");
}

const summary = createCheckoutSummary(cart, { discountCode: "WELCOME10" });

if (summary.total !== 14.4) {
  throw new Error(`expected discounted total 14.4, received ${summary.total}`);
}
