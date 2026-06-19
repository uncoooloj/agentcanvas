export function reserveInventory(items: Array<{ sku: string }>) {
  return {
    status: items.length ? "reserved" : "empty",
  };
}
