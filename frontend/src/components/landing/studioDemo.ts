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

type ProposalAnchor = "charge" | "sms" | "confirm"

function proposalAt(anchor: ProposalAnchor, label: string, edit: (source: string) => string[]) {
  const node = checkout.find((node) => node.id === anchor)
  if (!node) throw new Error(`Missing steering anchor: ${anchor}`)

  const changes = edit(node.source)
  const before = changes.filter((line) => !line.startsWith("+")).length
  const after = changes.filter((line) => !line.startsWith("-")).length
  return {
    label,
    anchor,
    file: node.file,
    line: node.line,
    draft: [`@@ -${node.line},${before} +${node.line},${after} @@`, ...changes].join("\n"),
  }
}

export function createProposal(input: string) {
  const request = input.trim()
  if (!request) return null

  if (request === steeringExamples[0]) {
    return proposalAt("charge", "Screen orders over $500", (source) => [
      "+if (order.totalCents > 50_000) {",
      "+  await fraud.screen(order)",
      "+}",
      ` ${source.split("\n")[0]}`,
    ])
  }

  if (request === steeringExamples[1]) {
    return proposalAt("sms", "Retry failed SMS", (source) => {
      const [first, ...rest] = source.split("\n")
      return [
        `-${first}`,
        `+${first.replace("await ", "await retryWithBackoff(() => ")}`,
        ...rest.slice(0, -1).map((line) => ` ${line}`),
        `-${rest.at(-1)}`,
        `+${rest.at(-1)})`,
      ]
    })
  }

  return proposalAt("confirm", request, (source) => [
    ...`Steering pin: ${request}`.split(/\r\n?|\n/).map((line) => `+// ${line}`),
    ` ${source.split("\n")[0]}`,
  ])
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
