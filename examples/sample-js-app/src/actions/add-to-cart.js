export function addItemToCart(cart, item) {
  const existing = cart.items.find((entry) => entry.sku === item.sku);

  if (existing) {
    return {
      ...cart,
      items: cart.items.map((entry) =>
        entry.sku === item.sku
          ? { ...entry, quantity: entry.quantity + item.quantity }
          : entry
      ),
    };
  }

  return {
    ...cart,
    items: [...cart.items, item],
  };
}
