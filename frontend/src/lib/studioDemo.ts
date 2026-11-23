import { diffCounts, type FileDiff, type FileSlice, type StudioBootstrapResponse, type StudioDocument, type StudioEdge, type StudioFlow, type StudioNode } from "./studioTypes"

const workspace = "/workspace/shopfront"
const branch = "feature/retry-sms-receipt"
const paths = {
  checkout: "apps/shopfront/src/routes/checkout.tsx",
  orders: "services/checkout/src/orders.ts",
  inventory: "services/inventory/src/reservations.ts",
  webhook: "services/checkout/src/webhooks/stripe.ts",
  receipt: "workers/notifications/src/receipt.ts",
  stripe: "packages/stripe-gateway/src/client.ts",
  db: "services/orders/src/repository.ts",
  refund: "services/checkout/src/refunds.ts",
  signIn: "apps/shopfront/src/routes/sign-in.tsx",
  retry: "services/checkout/src/retry.ts",
} as const

const sources = {
  checkout: `import { json, redirect } from "@remix-run/node";
import { api, requireCart, requireCustomer } from "~/server";

export async function action({ request }: ActionArgs) {
  const customer = await requireCustomer(request);
  const cart = await requireCart(request, customer.id);
  const attemptKey = request.headers.get("Idempotency-Key") ?? cart.revision;
  try {
    const payment = await api.checkout.create({ cartId: cart.id, attemptKey });
    return redirect(payment.url);
  } catch (error) {
    if (error instanceof OutOfStockError) {
      return json({ unavailable: error.skus }, { status: 409 });
    }
    throw error;
  }
}`,
  orders: `export async function createOrder(input: CreateOrderInput) {
  const cart = await carts.requireActive(input.cartId, input.customerId);
  const previous = await orders.findByAttempt(input.attemptKey);
  if (previous) return stripe.resumePayment(previous.paymentIntentId);

  const stock = await inventory.reserve(cart.items, input.attemptKey);
  const order = await orders.insert({
    customerId: cart.customerId,
    reservationId: stock.id,
    totalCents: cart.totalCents,
    attemptKey: input.attemptKey,
    status: "pending_payment",
  });
  return stripe.createPaymentIntent(order, input.attemptKey);
}`,
  inventory: `export async function reserve(items: LineItem[], attemptKey: string) {
  return db.transaction(async (tx) => {
    const rows = await tx.stock.lockForUpdate(items.map((item) => item.sku));
    const unavailable = findUnavailable(rows, items);
    if (unavailable.length) throw new OutOfStockError(unavailable);
    return tx.reservations.insert({ items, attemptKey, expiresInSeconds: 900 });
  });
}

export async function releaseReservation(id: string) {
  await db.reservations.releaseIfHeld(id);
}`,
  webhook: `router.post("/webhooks/stripe", { config: { rawBody: true } }, async (request, reply) => {
  const signature = request.headers["stripe-signature"];
  const event = stripe.verifyEvent(request.rawBody, signature);
  const firstDelivery = await stripeEvents.claim(event.id);
  if (!firstDelivery) return reply.code(200).send({ duplicate: true });

  const payment = getPaymentIntent(event);
  if (event.type === "payment_intent.succeeded") {
    await orders.markPaid(payment.id, event.id);
  } else if (event.type === "payment_intent.payment_failed") {
    await inventory.releaseReservation(payment.metadata.reservationId);
  }

  return reply.code(200).send({ received: true });
});`,
  receipt: `export async function sendReceipt(job: ReceiptJob) {
  await email.sendReceipt(job.orderId, { key: job.id });
  const consent = await preferences.canSendSms(job.customerId);
  if (!consent) return;

  await queue.add("send-receipt-sms", {
    orderId: job.orderId,
    key: job.id,
    attempts: 3,
    backoff: { type: "exponential", delay: 1000 },
  });
}

export async function deliverSms(job: SmsReceiptJob) {
  await sms.send(job.orderId, { idempotencyKey: job.key });
}`,
  stripe: `export async function createPaymentIntent(order: Order, attemptKey: string) {
  const payment = await stripe.paymentIntents.create({
    amount: order.totalCents,
    currency: "usd",
    metadata: { orderId: order.id, reservationId: order.reservationId },
  }, { idempotencyKey: attemptKey });
  return payment;
}`,
  db: `export async function insert(input: NewOrder) {
  return db.orders.insertOrGet(input, { uniqueBy: "attemptKey" });
}

export async function markPaid(intentId: string, eventId: string) {
  return db.transaction(async (tx) => {
    const order = await tx.orders.transition(intentId, "pending_payment", "paid");
    if (!order) return;
    await tx.outbox.insert({
      topic: "receipt.requested", orderId: order.id, dedupeKey: eventId,
    });
  });
}`,
  refund: `export async function refundOrder(input: RefundRequest) {
  const order = await orders.lockForRefund(input.orderId);
  if (input.amount > order.refundableCents) {
    return { ok: false, reason: "Refund exceeds the remaining balance" };
  }

  const refund = await gateway.refund(order.paymentIntentId, {
    amount: input.amount, idempotencyKey: input.requestId,
  });
  await orders.recordRefund(order.id, refund.id, input.amount);

  await Promise.all([
    queue.add("send-refund-receipt", { orderId: order.id, refundId: refund.id }),
    audit.record("refund.issued", { orderId: order.id, refundId: refund.id }),
  ]);
  return { ok: true, refundId: refund.id };
}`,
  signIn: `export async function action({ request }: ActionArgs) {
  const credentials = await request.formData();
  const identity = await auth.verifyPassword(credentials);
  if (!identity || !await auth.verifyChallenge(identity.id, credentials)) {
    return json({ error: "Invalid credentials" }, { status: 401 });
  }
  return sessions.createResponse(identity.id, { httpOnly: true, sameSite: "lax" });
}

export async function refreshSession(request: Request) {
  const session = await sessions.read(request);
  if (!session || !session.isRefreshable) return redirect("/sign-in");
  if (session.expiresInSeconds > 60) return new Response(null, { status: 204 });
  const rotated = await sessions.rotate(session.id, session.refreshToken);
  return sessions.setCookie(rotated);
}`,
  retry: `export async function recordAttempt(scope: string, idempotencyKey: string) {
  return attempts.upsert({ scope, idempotencyKey, state: "started" });
}

export async function runWithRetry<T>(attemptId: string, work: () => Promise<T>) {
  try {
    const result = await retry(work, { attempts: 3, shouldRetry: isTemporaryFailure });
    await attempts.complete(attemptId);
    return result;
  } catch (error) {
    await attempts.fail(attemptId, categorizeFailure(error));
    throw error;
  }
}`,
}

type FileKey = keyof typeof sources
const fileByPath = new Map<string, FileKey>(Object.entries(paths).map(([key, path]) => [path, key as FileKey]))

function step(
  id: string, kind: StudioNode["kind"], title: string, component_id: string,
  file: FileKey, anchor: string, summary: string, extra?: Partial<StudioNode>,
): StudioNode {
  const source = sources[file].split("\n")
  const line = source.findIndex((text) => text.includes(anchor)) + 1
  if (!line) throw new Error(`Missing demo code anchor ${anchor} in ${paths[file]}`)
  return {
    id, kind, title, component_id, summary, status: "verified",
    code_refs: [{ path: paths[file], line, end_line: Math.min(source.length, line + 2) }],
    ...extra,
  }
}

function edges(flowId: string, links: [source: string, target: string, kind?: StudioEdge["kind"], label?: string][]): StudioEdge[] {
  return links.map(([source, target, kind = "normal", label], index) => ({ id: `${flowId}-${index + 1}`, source, target, kind, label }))
}

const orderFlow: StudioFlow = {
  id: "placing-order", title: "Placing an order", trigger: "Customer submits checkout",
  summary: "Reserve inventory, create a pending order, and hand off to Stripe for payment.",
  component_ids: ["shopfront", "checkout", "inventory", "stripe", "orders"],
  nodes: [
    step("order-submit", "When", "Customer submits checkout", "shopfront", "checkout", "export async function action", "Read the signed-in customer and their cart."),
    step("order-create", "Do", "Start an idempotent order", "checkout", "orders", "findByAttempt", "Reuse payment if the checkout attempt already exists."),
    step("order-stock", "Decision", "Are all items available?", "inventory", "inventory", "findUnavailable", "Check available units while stock rows are locked."),
    step("order-reserve", "Do", "Hold inventory for 15 minutes", "inventory", "inventory", "expiresInSeconds", "Keep stock available during the payment window."),
    step("order-persist", "Do", "Persist the pending order", "orders", "db", "insertOrGet", "Store one order per checkout attempt."),
    step("order-intent", "Do", "Create a Stripe payment intent", "stripe", "stripe", "paymentIntents.create", "Send the amount and reservation ID using the attempt key."),
    step("order-redirect", "SubFlow", "Hand off to hosted payment", "shopfront", "checkout", "return redirect", "Stripe reports the payment result through its webhook.", { flow_ref: "stripe-webhooks" }),
    step("order-unavailable", "End", "Return unavailable items", "shopfront", "checkout", "status: 409", "Ask the customer to revise their cart."),
  ],
  edges: edges("order", [
    ["order-submit", "order-create"], ["order-create", "order-stock"],
    ["order-stock", "order-reserve", "branch", "In stock"], ["order-stock", "order-unavailable", "error", "Unavailable"],
    ["order-reserve", "order-persist"], ["order-persist", "order-intent"], ["order-intent", "order-redirect", "async", "Payment result"],
  ]),
}

const webhookFlow: StudioFlow = {
  id: "stripe-webhooks", title: "Handling Stripe webhooks", trigger: "Stripe delivers a payment event",
  summary: "Verify and deduplicate payment events, then queue receipts for paid orders.",
  component_ids: ["stripe", "checkout", "orders", "notifications", "inventory"],
  diff_status: "modified", diff_summary: "Receipts now use an outbox. Customers who opt in get an SMS with bounded retries.",
  nodes: [
    step("webhook-receive", "When", "Receive a Stripe event", "checkout", "webhook", "router.post", "Accept the signed request with its raw body."),
    step("webhook-verify", "Do", "Verify the Stripe signature", "checkout", "webhook", "stripe.verifyEvent", "Validate the signature before reading the event."),
    step("webhook-duplicate", "Decision", "Has this event been processed?", "checkout", "webhook", "stripeEvents.claim", "Reserve the event ID so concurrent deliveries cannot apply twice."),
    step("webhook-ack", "End", "Acknowledge by a separate handler", "checkout", "webhook", "duplicate: true", "The existing route now handles duplicate responses directly.", { diff_status: "removed", diff_summary: "The standalone acknowledgement path moved into the webhook route." }),
    step("webhook-paid", "Decision", "Did payment succeed?", "checkout", "webhook", 'event.type === "payment_intent.succeeded"', "Dispatch the signed payment outcome."),
    step("webhook-confirm", "Do", "Mark the order paid", "orders", "db", 'transition(intentId', "Commit the payment state and receipt event in one transaction.", { diff_status: "modified", diff_summary: "Write a deduplicated receipt event to the outbox with the state transition." }),
    step("webhook-receipt", "Do", "Send the email receipt", "notifications", "receipt", "email.sendReceipt", "Deliver email with the receipt job ID as its key.", { diff_status: "modified", diff_summary: "Separate email from the optional SMS job." }),
    step("proposal-sms-opt-in", "Decision", "Did the customer opt in to SMS?", "notifications", "receipt", "preferences.canSendSms", "Use the saved consent before scheduling a text.", { diff_status: "added", diff_summary: "SMS delivery now checks the customer’s saved consent." }),
    step("proposal-retry-sms", "Loop", "Retry temporary SMS failures", "notifications", "receipt", "attempts: 3", "Back off between up to three attempts.", { diff_status: "added", diff_summary: "Queue SMS separately with exponential backoff." }),
    step("webhook-receipt-done", "End", "Finish receipt delivery", "notifications", "receipt", "sms.send(job.orderId", "Complete the receipt after email-only delivery or processing the SMS job."),
    step("webhook-failed", "Do", "Release the inventory hold", "inventory", "inventory", "releaseIfHeld", "Return the reserved items after a payment failure."),
    step("webhook-done", "End", "Acknowledge Stripe", "checkout", "webhook", "received: true", "Return 200 after processing the event."),
  ],
  edges: edges("webhook", [
    ["webhook-receive", "webhook-verify"], ["webhook-verify", "webhook-duplicate"],
    ["webhook-duplicate", "webhook-ack", "branch", "Previous route"], ["webhook-duplicate", "webhook-done", "branch", "Duplicate"],
    ["webhook-duplicate", "webhook-paid", "branch", "First delivery"],
    ["webhook-paid", "webhook-confirm", "branch", "Paid"], ["webhook-paid", "webhook-failed", "error", "Failed"],
    ["webhook-confirm", "webhook-done"], ["webhook-confirm", "webhook-receipt", "async", "Receipt outbox"],
    ["webhook-receipt", "proposal-sms-opt-in"], ["proposal-sms-opt-in", "proposal-retry-sms", "branch", "Opted in"],
    ["proposal-sms-opt-in", "webhook-receipt-done", "branch", "Email only"], ["proposal-retry-sms", "webhook-receipt-done"],
    ["webhook-failed", "webhook-done"],
  ]),
}

const refundFlow: StudioFlow = {
  id: "issuing-refunds", title: "Issuing refunds", trigger: "Support approves a refund",
  summary: "Lock a refundable order, execute the Stripe refund, and record the result.",
  component_ids: ["checkout", "stripe", "orders", "notifications"],
  nodes: [
    step("refund-request", "When", "Support submits a refund", "checkout", "refund", "export async function refundOrder", "Accept an order, amount, and support request ID."),
    step("refund-lock", "Do", "Lock the order for refund", "orders", "refund", "orders.lockForRefund", "Prevent concurrent adjustments to the refundable balance."),
    step("refund-eligible", "Decision", "Is the amount refundable?", "checkout", "refund", "input.amount > order", "Compare the requested amount with the remaining balance."),
    step("refund-stripe", "Do", "Create the Stripe refund", "stripe", "refund", "gateway.refund", "Use the support request ID as the idempotency key."),
    step("refund-record", "Do", "Record the refund transaction", "orders", "refund", "orders.recordRefund", "Keep the Stripe refund ID on the order ledger."),
    step("refund-notify", "Parallel", "Queue the receipt and audit entry", "notifications", "refund", "Promise.all", "Send the customer’s receipt and retain a support audit trail.", { status: "stale" }),
    step("refund-end", "End", "Confirm the refund to support", "checkout", "refund", "ok: true", "Return the refund ID once recorded."),
    step("refund-reject", "End", "Explain the balance limit", "checkout", "refund", "ok: false", "Return an actionable reason before contacting Stripe."),
  ],
  edges: edges("refund", [
    ["refund-request", "refund-lock"], ["refund-lock", "refund-eligible"],
    ["refund-eligible", "refund-stripe", "branch", "Eligible"], ["refund-eligible", "refund-reject", "error", "Over balance"],
    ["refund-stripe", "refund-record"], ["refund-record", "refund-notify", "async"], ["refund-notify", "refund-end"],
  ]),
}

const sessionFlow: StudioFlow = {
  id: "sign-in-session-refresh", title: "Signing in & session refresh", trigger: "Customer signs in or a session nears expiry",
  summary: "Authenticate a customer, issue a secure cookie, and refresh it before expiration.",
  component_ids: ["shopfront", "checkout", "orders"],
  nodes: [
    step("session-submit", "When", "Customer submits credentials", "shopfront", "signIn", "const credentials", "Read the credentials from the sign-in form."),
    step("session-verify", "Do", "Verify the password", "checkout", "signIn", "auth.verifyPassword", "Look up the account using the supplied credentials."),
    step("session-valid", "Decision", "Is the challenge valid?", "checkout", "signIn", "auth.verifyChallenge", "Require the challenge in addition to valid credentials."),
    step("session-create", "Do", "Issue a secure session cookie", "shopfront", "signIn", "sessions.createResponse", "Set an HTTP-only cookie with a SameSite policy."),
    step("session-wait", "Wait", "Wait until the refresh window", "shopfront", "signIn", "session.expiresInSeconds", "Delay cookie rotation until expiry is less than a minute away."),
    step("session-refresh", "Decision", "Can the session be refreshed?", "checkout", "signIn", "!session.isRefreshable", "Reject expired or revoked refresh sessions."),
    step("session-renew", "Loop", "Rotate the session token", "orders", "signIn", "sessions.rotate", "Replace the token and continue with the new cookie."),
    step("session-denied", "End", "Show a sign-in error", "shopfront", "signIn", "Invalid credentials", "Return a generic credential error to the form."),
    step("session-expired", "End", "Require sign-in again", "shopfront", "signIn", 'redirect("/sign-in")', "Send the customer back to authentication."),
  ],
  edges: edges("session", [
    ["session-submit", "session-verify"], ["session-verify", "session-valid"],
    ["session-valid", "session-create", "branch", "Verified"], ["session-valid", "session-denied", "error", "Denied"],
    ["session-create", "session-wait"], ["session-wait", "session-refresh", "async", "Near expiry"],
    ["session-refresh", "session-renew", "branch", "Eligible"], ["session-refresh", "session-expired", "error", "Expired"],
    ["session-renew", "session-wait", "loop_back", "Cookie rotated"],
  ]),
}

export const demoDocument: StudioDocument = {
  schema: "agentcanvas.studio.v3",
  components: [
    { id: "shopfront", name: "Shopfront Web", kind: "web", path: "apps/shopfront", summary: "Customer storefront, account, and authenticated checkout.", tech: ["Remix", "React"], entrypoints: [paths.checkout, paths.signIn] },
    { id: "checkout", name: "Checkout API", kind: "service", path: "services/checkout", summary: "Coordinates payments, signed webhooks, and refunds.", tech: ["Fastify", "TypeScript"], entrypoints: [paths.orders, paths.webhook, paths.refund] },
    { id: "inventory", name: "Inventory Service", kind: "service", path: "services/inventory", summary: "Holds stock during payment and releases failed reservations.", tech: ["Node.js", "PostgreSQL"], entrypoints: [paths.inventory] },
    { id: "stripe", name: "Stripe Gateway", kind: "external", path: "packages/stripe-gateway", summary: "Creates payment intents and sends signed outcome events.", tech: ["Stripe SDK"], entrypoints: [paths.stripe] },
    { id: "notifications", name: "Notification Worker", kind: "worker", path: "workers/notifications", summary: "Delivers email receipts and opt-in SMS from durable jobs.", tech: ["BullMQ", "Redis"], entrypoints: [paths.receipt], diff_status: "modified" },
    { id: "orders", name: "Orders DB", kind: "db", path: "services/orders", summary: "Transactional order and refund ledger with a receipt outbox.", tech: ["PostgreSQL"], entrypoints: [paths.db], diff_status: "modified" },
  ],
  component_edges: [
    { id: "shop-checkout", source: "shopfront", target: "checkout", label: "Checkout requests", protocol: "HTTPS" },
    { id: "checkout-stock", source: "checkout", target: "inventory", label: "Reserve stock", protocol: "gRPC" },
    { id: "checkout-stripe", source: "checkout", target: "stripe", label: "Payment intents", protocol: "HTTPS" },
    { id: "stripe-checkout", source: "stripe", target: "checkout", label: "Signed webhooks", protocol: "HTTPS" },
    { id: "checkout-orders", source: "checkout", target: "orders", label: "Persist orders", protocol: "SQL" },
    { id: "orders-notify", source: "orders", target: "notifications", label: "Receipt outbox", protocol: "Queue", diff_status: "added" },
  ],
  flows: [orderFlow, webhookFlow, refundFlow, sessionFlow],
}

const before: Partial<Record<FileKey, string>> = {
  receipt: `export async function sendReceipt(job: ReceiptJob) {
  await email.sendReceipt(job.orderId);
  await sms.send(job.orderId);
}`,
  db: sources.db.replace(/    await tx\.outbox\.insert\(\{[\s\S]*?\n    \}\);/, '    await queue.add("send-receipt", { orderId: order.id });'),
  webhook: sources.webhook.replace('  if (!firstDelivery) return reply.code(200).send({ duplicate: true });', '  if (!firstDelivery) return acknowledgeDuplicate(reply);'),
  retry: "",
}

export function demoBootstrap(): StudioBootstrapResponse {
  return {
    ok: true, mode: "demo", workspace, workspace_name: "Shopfront Commerce",
    git: { branch, head: "71d44aa", dirty: false, changed_files: [paths.webhook, paths.db, paths.receipt], diff_base: "main" },
    runner: { preferred: "codex", available: [{ id: "codex", label: "Codex", binary: "codex" }] },
    has_mapped_canvas: true, stale_node_ids: ["refund-notify"], document: structuredClone(demoDocument),
    annotations: [], active_run: null, recent_runs: [],
  }
}

export function demoFileSlice(path: string, line?: number, context = 12): FileSlice {
  const file = fileByPath.get(path)
  const source = file ? sources[file].split("\n") : ["// This file is outside the sandbox fixtures."]
  const highlight = Math.min(Math.max(line ?? 1, 1), source.length)
  const start_line = Math.max(1, highlight - context)
  const end_line = Math.min(source.length, highlight + context)
  return {
    ok: true, path, start_line, end_line, highlight_line: line ? highlight : null,
    lines: source.slice(start_line - 1, end_line).map((text, index) => ({ number: start_line + index, text })),
    language: path.endsWith(".tsx") ? "TSX" : "TypeScript", absolute_path: `${workspace}/${path}`,
  }
}

export function demoFileDiff(path: string): FileDiff {
  const empty: FileDiff = { ok: true, path, base: "main", has_diff: false, hunks: [], additions: 0, deletions: 0 }
  const file = fileByPath.get(path)
  if (!file || before[file] === undefined) return empty
  const previous = before[file] ? before[file].split("\n") : []
  const current = sources[file].split("\n")
  let prefix = 0
  let suffix = 0
  while (prefix < previous.length && prefix < current.length && previous[prefix] === current[prefix]) prefix++
  while (suffix < previous.length - prefix && suffix < current.length - prefix
      && previous[previous.length - suffix - 1] === current[current.length - suffix - 1]) suffix++
  const removed = previous.slice(prefix, previous.length - suffix)
  const added = current.slice(prefix, current.length - suffix)
  const start = Math.max(0, prefix - 3)
  const leading = current.slice(start, prefix)
  const trailing = current.slice(current.length - suffix, current.length - Math.max(0, suffix - 3))
  const oldCount = leading.length + removed.length + trailing.length
  const newCount = leading.length + added.length + trailing.length
  const lines = [
    ...leading.map((line) => ` ${line}`), ...removed.map((line) => `-${line}`),
    ...added.map((line) => `+${line}`), ...trailing.map((line) => ` ${line}`),
  ]
  return {
    ...empty, has_diff: true, additions: added.length, deletions: removed.length,
    hunks: [{ header: `@@ -${oldCount ? start + 1 : start},${oldCount} +${start + 1},${newCount} @@`, lines }],
  }
}

export function demoProposal(document: StudioDocument, flowId: string, nodeIds: string[], prompt: string): StudioDocument {
  const proposal = structuredClone(document)
  for (const flow of proposal.flows) {
    delete flow.diff_status
    delete flow.diff_summary
    for (const node of flow.nodes) {
      delete node.diff_status
      delete node.diff_summary
    }
  }

  const flow = proposal.flows.find((item) => item.id === flowId) ?? proposal.flows[0]
  if (!flow?.nodes.length) return proposal
  const id = `sandbox-${flow.id}`
  const selected = flow.nodes.filter((node) => nodeIds.includes(node.id) && !node.id.startsWith(id))
  const scoped = selected.length ? selected : flow.nodes.filter((node) => node.kind === "Do" && !node.id.startsWith(id)).slice(0, 1)
  const anchor = scoped.find((node) => node.kind !== "End") ?? flow.nodes.find((node) => node.kind === "Do") ?? flow.nodes[0]
  for (const node of scoped.slice(0, 2)) {
    node.status = "proposed"
    node.diff_status = "modified"
    node.diff_summary = prompt ? `Requested change: ${prompt}` : "Pass the durable attempt key through this step."
  }

  const component = anchor.component_id ?? flow.component_ids[0]
  const added = [
    step(`${id}-attempt`, "Do", "Record a durable attempt", component, "retry", "attempts.upsert", "Keep a replay key for this operation."),
    step(`${id}-retry`, "Loop", "Retry temporary failures", component, "retry", "await retry(work", "Retry only transient errors. Record the final outcome."),
  ]

  for (const node of added) {
    node.status = "proposed"
    node.diff_status = "added"
    node.diff_summary = node.summary
    const index = flow.nodes.findIndex((item) => item.id === node.id)
    if (index === -1) flow.nodes.push(node)
    else flow.nodes[index] = node
  }

  const original = flow.edges.filter((edge) => !edge.id.startsWith(id))
  const previousRetry = original.filter((edge) => edge.source === added[1].id)
  const previousAnchor = flow.edges.find((edge) => edge.id === `${id}-begin`)?.source
  for (const edge of previousRetry) edge.source = previousAnchor ?? anchor.id
  for (const edge of original) if (edge.source === anchor.id) edge.source = added[1].id
  flow.edges = [...original,
    { id: `${id}-begin`, source: anchor.id, target: added[0].id, kind: "normal", diff_status: "added" },
    { id: `${id}-continue`, source: added[0].id, target: added[1].id, kind: "normal", diff_status: "added" },
  ]

  const counts = diffCounts(flow.nodes)
  flow.diff_status = "modified"
  flow.diff_summary = `Draft adds ${counts.added} steps for recording and retrying the operation.`
  return proposal
}

export function demoVerified(document: StudioDocument): StudioDocument {
  const verified = structuredClone(document)
  for (const flow of verified.flows) {
    for (const node of flow.nodes) if (node.status === "proposed") node.status = "verified"
  }
  return verified
}
