import unittest
from pathlib import Path

from agentcanvas.languages.js_ts import FACT_SCHEMA, parse_workspace


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "js_ts"


def _by_file(facts, key, path):
    return [item for item in facts[key] if item.get("file") == path or item.get("path") == path]


class JsTsLanguageExtractorTests(unittest.TestCase):
    maxDiff = None

    def test_extracts_language_neutral_source_facts(self):
        facts = parse_workspace(FIXTURE_ROOT)
        checkout_path = "src/routes/checkout.ts"

        self.assertEqual(facts["schema"], FACT_SCHEMA)
        self.assertEqual(facts["parser"]["strategy"], "regex")
        self.assertIn(checkout_path, {item["path"] for item in facts["files"]})
        self.assertEqual(
            {"branch", "export", "file", "import", "route", "symbol"},
            {item["type"] for item in facts["facts"]},
        )
        self.assertEqual(facts["summary"]["by_type"]["branch"], 3)

        imports = _by_file(facts, "imports", checkout_path)
        import_specs = {item["specifier"] for item in imports}
        self.assertIn("express", import_specs)
        self.assertIn("../services/inventory", import_specs)
        inventory_import = next(
            item for item in imports if item["specifier"] == "../services/inventory"
        )
        self.assertEqual(inventory_import["resolved_path"], "src/services/inventory.ts")

        symbols = _by_file(facts, "symbols", checkout_path)
        symbol_names = {item["name"] for item in symbols}
        self.assertIn("CheckoutRequest", symbol_names)
        self.assertIn("checkoutRoutes", symbol_names)
        self.assertIn("submitCheckout", symbol_names)

        submit_symbol = next(item for item in symbols if item["name"] == "submitCheckout")
        self.assertEqual(submit_symbol["symbol_kind"], "function")
        self.assertTrue(submit_symbol["exported"])
        self.assertEqual(submit_symbol["source_ref"]["line"], 16)

        exports = _by_file(facts, "exports", checkout_path)
        exported_names = {item["exported_name"] for item in exports}
        self.assertIn("reserveInventory", exported_names)
        self.assertIn("submitCheckout", exported_names)
        self.assertIn("default", exported_names)
        self.assertIn("legacyCheckout", exported_names)

        routes = _by_file(facts, "routes", checkout_path)
        route_pairs = {(item["method"], item["path"], item["route_kind"]) for item in routes}
        self.assertIn(("POST", "/checkout/submit", "handler-call"), route_pairs)
        self.assertIn(("GET", "/checkout/summary", "route-object"), route_pairs)
        self.assertIn((None, "/checkout", "file-route"), route_pairs)

        post_route = next(
            item
            for item in routes
            if item["method"] == "POST" and item["path"] == "/checkout/submit"
            and item["route_kind"] == "handler-call"
        )
        self.assertEqual(post_route["handler"], "submitCheckout")

        branches = _by_file(facts, "branches", checkout_path)
        branch_kinds = [item["branch_kind"] for item in branches]
        self.assertIn("if", branch_kinds)
        self.assertIn("else-if", branch_kinds)
        self.assertIn("else", branch_kinds)

        else_if = next(item for item in branches if item["branch_kind"] == "else-if")
        self.assertEqual(else_if["condition"], "req.body.preview")
        self.assertEqual(else_if["source_ref"]["line"], 19)

        for collection in ["symbols", "exports", "imports", "routes", "branches"]:
            for item in _by_file(facts, collection, checkout_path):
                with self.subTest(collection=collection, item=item["id"]):
                    self.assertEqual(item["source_ref"]["path"], checkout_path)
                    self.assertGreaterEqual(item["source_ref"]["line"], 1)


if __name__ == "__main__":
    unittest.main()
