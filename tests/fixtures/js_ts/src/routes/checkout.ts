import express from "express";
import { reserveInventory as reserve } from "../services/inventory";
export { reserve as reserveInventory } from "../services/inventory";

const router = express.Router();

export interface CheckoutRequest {
  body?: { preview?: boolean };
}

export const checkoutRoutes = [
  { method: "GET", path: "/checkout/summary", handler: "summaryHandler" },
  { path: "/checkout/submit", method: "POST" },
];

export async function submitCheckout(req: CheckoutRequest, res) {
  if (!req.body) {
    return res.status(400).json({ error: "missing body" });
  } else if (req.body.preview) {
    return res.status(200).json({ status: "preview" });
  } else {
    reserve([]);
  }

  return res.status(202).json({ status: "submitted" });
}

router.post("/checkout/submit", submitCheckout);
router.get("/checkout/summary", (req, res) => res.json({ ok: true }));

export default router;
module.exports.legacyCheckout = submitCheckout;
