export type StudioMode = "current" | "diff" | "system"
export type SandboxTab = "system" | "flows" | "diff"

type StudioNode = {
  id: string
  label: string
  role: "When" | "Do" | "If" | "Service"
  file: string
  line: number
  source: string
  change?: "Modified" | "Added"
  diff?: string
  position: string
}

export const checkout: StudioNode[] = [
  {
    id: "order", label: "POST /orders", role: "When", position: "col-start-1 row-start-1",
    file: "src/orders/routes.ts", line: 12,
    source: 'router.post("/orders", async (req, res) => {\n  const order = await checkout(req.body)\n  res.status(201).json(order)\n})',
  },
  {
    id: "stock", label: "Reserve stock", role: "Do", position: "col-start-2 row-start-1",
    file: "src/inventory/reserve.ts", line: 18,
    source: "export async function reserveStock(items: Item[]) {\n  return inventory.reserve(items)\n}",
  },
  {
    id: "condition", label: "In stock", role: "If", position: "col-start-3 row-start-1",
    file: "src/orders/checkout.ts", line: 37,
    source: "const hold = await reserveStock(order.items)\nif (!hold.ok) {\n  return outOfStock(hold.missing)\n}",
  },
  {
    id: "charge", label: "Charge Stripe", role: "Do", position: "col-start-3 row-start-2",
    file: "src/payments/charge.ts", line: 42, change: "Modified",
    source: 'const payment = await stripe.paymentIntents.create({\n  amount: order.totalCents,\n  currency: "usd",\n})',
    diff: '@@ -42,4 +42,6 @@\n-const payment = await stripe.paymentIntents.create({\n+const payment = await retryWithBackoff(() =>\n+  stripe.paymentIntents.create({\n     amount: order.totalCents,\n     currency: "usd",\n-})\n+  }, { idempotencyKey: order.id }),\n+  { attempts: 3 })',
  },
  {
    id: "confirm", label: "Send confirmation", role: "Do", position: "col-start-2 row-start-2",
    file: "src/orders/checkout.ts", line: 51,
    source: "await mail.send({\n  to: order.email,\n  template: \"order-confirmation\",\n  data: { order },\n})",
  },
  {
    id: "sms", label: "Text delivery ETA via Twilio", role: "Do", position: "col-start-1 row-start-2",
    file: "src/notify/receipt.ts", line: 9, change: "Added",
    source: 'await twilio.messages.create({\n  to: order.phone,\n  body: `Delivery ETA: ${order.deliveryEta}`,\n})',
    diff: '@@ -9,0 +9,4 @@\n+await twilio.messages.create({\n+  to: order.phone,\n+  body: `Delivery ETA: ${order.deliveryEta}`,\n+})',
  },
  {
    id: "fallback", label: "Fallback: Queue manual retry", role: "Do", position: "col-start-1 row-start-3",
    file: "src/notify/receipt.ts", line: 14, change: "Added",
    source: 'catch (error) {\n  await queue.enqueue("manual-retry", {\n    orderId: order.id,\n  })\n}',
    diff: '@@ -14,0 +14,5 @@\n+catch (error) {\n+  await queue.enqueue("manual-retry", {\n+    orderId: order.id,\n+  })\n+}',
  },
]

export const services: StudioNode[] = [
  {
    id: "web", label: "Web App", role: "Service", position: "col-start-2 row-start-1",
    file: "src/web/checkout.ts", line: 24,
    source: 'await fetch("/orders", {\n  method: "POST",\n  body: JSON.stringify(cart),\n})',
  },
  {
    id: "api", label: "Order API", role: "Service", position: "col-start-2 row-start-2",
    file: "src/orders/routes.ts", line: 12,
    source: 'router.post("/orders", async (req, res) => {\n  res.json(await checkout(req.body))\n})',
  },
  {
    id: "inventory", label: "Inventory", role: "Service", position: "col-start-1 row-start-3",
    file: "src/inventory/client.ts", line: 8,
    source: 'export const inventory = new InventoryClient({\n  url: env.INVENTORY_URL,\n})',
  },
  {
    id: "stripe", label: "Stripe", role: "Service", position: "col-start-2 row-start-3",
    file: "src/payments/client.ts", line: 5,
    source: "export const stripe = new Stripe(env.STRIPE_KEY)",
  },
  {
    id: "notify", label: "Notify Worker", role: "Service", position: "col-start-3 row-start-3",
    file: "src/notify/worker.ts", line: 22,
    source: 'worker.on("order.confirmed", async (order) => {\n  await sendReceipt(order)\n})',
  },
]

export const steeringExamples = ["Add fraud check over $500", "Retry failed SMS"] as const

export function createProposal(input: string) {
  const request = input.trim()
  if (!request) return null

  if (request === steeringExamples[0]) {
    return {
      label: "Screen orders over $500",
      anchor: "charge" as const,
      file: "src/payments/charge.ts",
      line: 42,
      draft: "@@ -42,0 +42,3 @@\n+if (order.totalCents > 50_000) {\n+  await fraud.screen(order)\n+}",
    }
  }

  if (request === steeringExamples[1]) {
    return {
      label: "Retry failed SMS",
      anchor: "sms" as const,
      file: "src/notify/receipt.ts",
      line: 9,
      draft: "@@ -9,1 +9,1 @@\n-await sendDeliveryText(order)\n+await retryWithBackoff(() => sendDeliveryText(order))",
    }
  }

  return {
    label: request,
    anchor: "confirm" as const,
    file: "src/orders/checkout.ts",
    line: 42,
    draft: `@@ -42,0 +42,1 @@\n+// Steering pin: ${request}`,
  }
}

export function getSandboxUrl(href: string, tab: SandboxTab) {
  const url = new URL(href)
  url.searchParams.set("demo", "1")
  if (tab === "flows") {
    url.searchParams.delete("tab")
  } else {
    url.searchParams.set("tab", tab)
  }
  url.hash = ""
  return url.toString()
}
