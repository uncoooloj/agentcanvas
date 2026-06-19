const DISCOUNTS = {
  WELCOME10: 0.1,
  SAVE20: 0.2,
};

export function applyDiscount(cart, discountCode) {
  const rate = DISCOUNTS[discountCode] || 0;

  if (!rate) {
    return cart;
  }

  return {
    ...cart,
    items: cart.items.map((item) => ({
      ...item,
      price: Number((item.price * (1 - rate)).toFixed(2)),
    })),
  };
}
