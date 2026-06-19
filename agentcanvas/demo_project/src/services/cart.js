export function normalizeCart(input = {}) {
  return {
    customer: {
      email: input.customer?.email || "guest@example.test",
      loyaltyTier: input.customer?.loyaltyTier || "standard",
    },
    deliveryPostcode: String(input.deliveryPostcode || "").trim().toUpperCase(),
    items: Array.isArray(input.items) ? input.items.map(normalizeItem) : [],
  };
}

export function hasEmptyCartCondition(cart) {
  return cart.items.length === 0;
}

function normalizeItem(item) {
  return {
    sku: String(item.sku || "").trim(),
    name: item.name || item.sku || "Item",
    quantity: Number(item.quantity || 1),
    price: Number(item.price || 0),
  };
}
