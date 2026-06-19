import unittest
from pathlib import Path

from agentcanvas.indexer import build_workflow_ir
from agentcanvas.languages import dart_lang, kotlin_lang, swift_lang
from agentcanvas.languages.lightweight import FACT_SCHEMA


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "mobile_native"


def _facts(payload, fact_type):
    return [fact for fact in payload["facts"] if fact["type"] == fact_type]


class MobileNativeLanguageExtractorTests(unittest.TestCase):
    maxDiff = None

    def test_extracts_dart_flutter_facts(self):
        payload = dart_lang.extract_file(FIXTURE_ROOT / "app.dart")
        self.assertEqual(payload["schema"], FACT_SCHEMA)

        imports = _facts(payload, "import")
        import_specs = {fact["specifier"] for fact in imports}
        self.assertIn("package:flutter/material.dart", import_specs)
        self.assertIn("package:go_router/go_router.dart", import_specs)
        self.assertIn("src/details.dart", import_specs)
        self.assertIn("home_state.dart", import_specs)
        self.assertEqual(
            "part",
            next(fact for fact in imports if fact["specifier"] == "home_state.dart")["kind"],
        )

        symbols = _facts(payload, "symbol")
        symbol_kinds = {fact["name"]: fact["symbol_kind"] for fact in symbols}
        self.assertEqual(symbol_kinds["UserId"], "extension type")
        self.assertEqual(symbol_kinds["HomeScreen"], "class")
        self.assertEqual(symbol_kinds["loadOrders"], "function")

        routes = {
            (fact["path"], fact["method"], fact["kind"])
            for fact in _facts(payload, "route")
        }
        self.assertIn(("/home", None, "flutter-go-route"), routes)
        self.assertIn(("/settings", None, "flutter-named-route"), routes)
        self.assertIn(("/orders", None, "flutter-navigation"), routes)

        branches = _facts(payload, "branch")
        else_if = next(fact for fact in branches if fact["branch_kind"] == "else-if")
        self.assertEqual(else_if["condition"], "DateTime.now().isUtc")

        calls = {fact["function"] for fact in _facts(payload, "call")}
        self.assertIn("Navigator.of", calls)
        self.assertIn("debugPrint", calls)
        self.assertNotIn("loadOrders", calls)

    def test_extracts_swift_swiftui_facts(self):
        payload = swift_lang.extract_file(FIXTURE_ROOT / "OrdersScreen.swift")
        self.assertEqual(payload["schema"], FACT_SCHEMA)

        imports = {fact["specifier"] for fact in _facts(payload, "import")}
        self.assertIn("SwiftUI", imports)
        self.assertIn("CheckoutApp", imports)

        symbols = {(fact["name"], fact["symbol_kind"]) for fact in _facts(payload, "symbol")}
        self.assertIn(("OrdersScreen", "struct"), symbols)
        self.assertIn(("OrdersScreen", "extension"), symbols)
        self.assertIn(("OrderDetailView", "struct"), symbols)
        self.assertIn(("refresh", "function"), symbols)
        self.assertIn(("trackOpen", "function"), symbols)

        routes = {
            (fact["path"], fact["method"], fact["kind"], fact.get("handler"))
            for fact in _facts(payload, "route")
        }
        self.assertIn(("OrderDetailView", None, "swiftui-navigation", "OrderDetailView"), routes)
        self.assertIn(("Route", None, "swiftui-navigation-destination", None), routes)
        self.assertIn(("OrdersScreen", None, "swiftui-screen", None), routes)

        branches = _facts(payload, "branch")
        if_branch = next(fact for fact in branches if fact["branch_kind"] == "if")
        self.assertEqual(if_branch["condition"], "Task.isCancelled")

        calls = {fact["function"] for fact in _facts(payload, "call")}
        self.assertIn("Analytics.shared.track", calls)
        self.assertNotIn("refresh", calls)

    def test_extracts_kotlin_android_facts(self):
        payload = kotlin_lang.extract_file(FIXTURE_ROOT / "OrdersRoutes.kt")
        self.assertEqual(payload["schema"], FACT_SCHEMA)

        imports = {fact["specifier"] for fact in _facts(payload, "import")}
        self.assertIn("io.ktor.server.routing.*", imports)
        self.assertIn("com.example.domain.Order", imports)

        symbols = {(fact["name"], fact["symbol_kind"]) for fact in _facts(payload, "symbol")}
        self.assertIn(("OrderDto", "data class"), symbols)
        self.assertIn(("ScreenState", "sealed interface"), symbols)
        self.assertIn(("toDto", "function"), symbols)
        self.assertIn(("ordersRoutes", "function"), symbols)
        self.assertIn(("fetchOrder", "function"), symbols)

        routes = {
            (fact["path"], fact["method"], fact["kind"])
            for fact in _facts(payload, "route")
        }
        self.assertIn(("/orders/{id}", "GET", "retrofit-route"), routes)
        self.assertIn(("/orders", "GET", "ktor-route"), routes)
        self.assertIn(("/orders", "POST", "ktor-route"), routes)
        self.assertIn(("/api", None, "ktor-route-scope"), routes)
        self.assertIn(("orders/{id}", None, "compose-navigation"), routes)
        self.assertIn(("settings", None, "compose-navigation-graph"), routes)

        branches = _facts(payload, "branch")
        switch_branch = next(fact for fact in branches if fact["branch_kind"] == "switch")
        self.assertEqual(switch_branch["condition"], "state")

        calls = {fact["function"] for fact in _facts(payload, "call")}
        self.assertIn("call.respondText", calls)
        self.assertNotIn("ordersRoutes", calls)

    def test_indexer_includes_mobile_native_language_modules(self):
        workflow_ir = build_workflow_ir(FIXTURE_ROOT)

        self.assertEqual(
            {"dart-flutter", "kotlin", "swift"},
            set(workflow_ir["summary"]["language_modules"]),
        )
        facts = workflow_ir["source_facts"]["facts"]
        self.assertTrue(
            any(
                fact["attributes"].get("language") == "dart-flutter"
                and fact["attributes"].get("fact_type") == "route"
                and fact["subject"] == "/home"
                for fact in facts
            )
        )
        self.assertTrue(
            any(
                fact["attributes"].get("language") == "swift"
                and fact["attributes"].get("fact_type") == "route"
                and fact["subject"] == "OrderDetailView"
                for fact in facts
            )
        )
        self.assertTrue(
            any(
                fact["attributes"].get("language") == "kotlin"
                and fact["attributes"].get("fact_type") == "route"
                and fact["subject"] == "GET /orders/{id}"
                for fact in facts
            )
        )


if __name__ == "__main__":
    unittest.main()
