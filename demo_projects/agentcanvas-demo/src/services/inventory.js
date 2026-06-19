const inventory = new Map([
  ["tea", 8],
  ["mug", 4],
  ["notebook", 0],
]);

let reservationSequence = 1;

export function reserveInventory(items) {
  const missingItems = items.filter(
    (item) => (inventory.get(item.sku) || 0) < item.quantity
  );

  if (missingItems.length > 0) {
    return {
      available: false,
      missingItems: missingItems.map((item) => item.sku),
    };
  }

  items.forEach((item) => {
    inventory.set(item.sku, (inventory.get(item.sku) || 0) - item.quantity);
  });

  return {
    available: true,
    reservationId: `RSV-${reservationSequence++}`,
  };
}

export function restockInventoryAction(event = {}) {
  const sku = event.sku || "notebook";
  const quantity = Number(event.quantity || 1);
  inventory.set(sku, (inventory.get(sku) || 0) + quantity);

  return {
    sku,
    quantity,
    onHand: inventory.get(sku),
  };
}

export function getInventorySnapshot() {
  return Object.fromEntries(inventory.entries());
}
