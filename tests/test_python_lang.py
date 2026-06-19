import unittest
from pathlib import Path

from agentcanvas.languages.python_lang import extract_file, extract_source_facts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "python_sample_app.py"


class PythonLanguageExtractorTests(unittest.TestCase):
    maxDiff = None

    def test_extracts_python_source_facts(self):
        payload = extract_file(FIXTURE)
        facts = payload["facts"]

        imports = [fact for fact in facts if fact["type"] == "import"]
        imported_names = {fact["imported"] for fact in imports}
        self.assertIn("FastAPI", imported_names)
        self.assertIn("http_requests", {fact["local_name"] for fact in imports})

        symbols = [fact for fact in facts if fact["type"] == "symbol"]
        symbol_names = {fact["qualified_name"] for fact in symbols}
        self.assertIn("health_check", symbol_names)
        self.assertIn("create_order", symbol_names)
        self.assertIn("CheckoutView", symbol_names)
        self.assertIn("CheckoutView.as_view", symbol_names)

        routes = [fact for fact in facts if fact["type"] == "route"]
        route_paths = {fact["path"] for fact in routes}
        self.assertIn("/health", route_paths)
        self.assertIn("/orders/{order_id}", route_paths)
        self.assertIn("/legacy", route_paths)
        self.assertIn("checkout/", route_paths)

        route_methods = {
            fact["path"]: tuple(fact["methods"])
            for fact in routes
            if fact["path"] in {"/health", "/orders/{order_id}", "/legacy"}
        }
        self.assertEqual(route_methods["/health"], ("GET",))
        self.assertEqual(route_methods["/orders/{order_id}"], ("POST",))
        self.assertEqual(route_methods["/legacy"], ("GET", "POST"))

        calls = [fact for fact in facts if fact["type"] == "call"]
        call_names = {fact["function"] for fact in calls}
        self.assertIn("save_order", call_names)
        self.assertIn("fallback_enabled", call_names)
        self.assertIn("http_requests.get", call_names)
        self.assertIn("CheckoutView.as_view", call_names)

        branches = [fact for fact in facts if fact["type"] == "branch"]
        self.assertEqual([fact["kind"] for fact in branches], ["if", "elif", "else"])
        self.assertTrue(all(fact["provenance"]["line"] > 0 for fact in branches))

    def test_reports_syntax_errors_as_facts(self):
        payload = extract_source_facts("broken.py", "def nope(:\n")

        self.assertEqual(payload["errors"][0]["type"], "parse_error")
        self.assertEqual(payload["summary"]["by_type"]["parse_error"], 1)


if __name__ == "__main__":
    unittest.main()

