const OUT_OF_STOCK_SKUS = new Set(["sold-out-tea"]);

export function reserveInventory(items) {
  const unavailable = items.find((item) => OUT_OF_STOCK_SKUS.has(item.sku));

  if (unavailable) {
    return {
      status: "unavailable",
      reason: `${unavailable.sku} is out of stock`,
    };
  }

  return {
    status: "reserved",
    reservationId: `reservation-${items.length}`,
  };
}
