import unittest
from pathlib import Path

from agentcanvas.languages import go_lang, php_lang, ruby_lang
from agentcanvas.languages.lightweight import FACT_SCHEMA


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def _facts(bundle, fact_type, path=None):
    facts = [fact for fact in bundle["facts"] if fact["type"] == fact_type]
    if path is not None:
        facts = [fact for fact in facts if fact.get("file") == path or fact.get("path") == path]
    return facts


class GoPhpRubyLanguageExtractorTests(unittest.TestCase):
    maxDiff = None

    def test_go_extracts_imports_routes_symbols_and_real_branches(self):
        bundle = go_lang.parse_workspace(FIXTURE_ROOT / "go_service")

        self.assertEqual(bundle["schema"], FACT_SCHEMA)
        self.assertEqual(bundle["parser"]["strategy"], "regex")

        imports = {fact["specifier"] for fact in _facts(bundle, "import")}
        self.assertIn("net/http", imports)
        self.assertIn("github.com/acme/audit", imports)
        self.assertIn("github.com/gorilla/mux", imports)
        self.assertNotIn("/health", imports)

        symbols = {fact["name"] for fact in _facts(bundle, "symbol")}
        self.assertIn("Server", symbols)
        self.assertIn("main", symbols)
        self.assertIn("healthHandler", symbols)
        self.assertIn("deleteUser", symbols)

        routes = {
            (fact["method"], fact["path"], fact.get("handler"))
            for fact in _facts(bundle, "route")
        }
        self.assertIn(("GET", "/health", "healthHandler"), routes)
        self.assertIn(("DELETE", "/users/{id}", "server.deleteUser"), routes)
        self.assertIn((None, "/ready", "healthHandler"), routes)

        branches = _facts(bundle, "branch")
        self.assertEqual(["err := run(); err != nil"], [fact["condition"] for fact in branches])

        calls = {fact["function"] for fact in _facts(bundle, "call")}
        self.assertIn("fmt.Println", calls)
        self.assertIn("run", calls)
        self.assertNotIn("import", calls)
        self.assertNotIn("healthHandler", calls)

    def test_php_laravel_extracts_grouped_imports_routes_and_ignores_comments(self):
        bundle = php_lang.parse_workspace(FIXTURE_ROOT / "php_laravel")

        self.assertEqual(bundle["schema"], FACT_SCHEMA)

        imports = {fact["specifier"] for fact in _facts(bundle, "import")}
        self.assertIn("App\\Http\\Controllers\\UserController", imports)
        self.assertIn("App\\Http\\Controllers\\ReportController", imports)
        self.assertIn("App\\Support\\route_metric", imports)

        symbols = {fact["name"] for fact in _facts(bundle, "symbol")}
        self.assertIn("UserController", symbols)
        self.assertIn("ReportController", symbols)
        self.assertIn("index", symbols)
        self.assertIn("store", symbols)

        routes = {
            (fact["method"], fact["path"], fact.get("handler"))
            for fact in _facts(bundle, "route")
        }
        self.assertIn(("GET", "/users", "UserController@index"), routes)
        self.assertIn((None, "/reports", "ReportController@store"), routes)
        self.assertIn(("DELETE", "/users/{user}", "UserController@destroy"), routes)

        route_paths = {fact["path"] for fact in _facts(bundle, "route")}
        self.assertNotIn("/commented-slash", route_paths)
        self.assertNotIn("/commented-hash", route_paths)

        branch_kinds = [fact["branch_kind"] for fact in _facts(bundle, "branch")]
        self.assertIn("if", branch_kinds)
        self.assertIn("else-if", branch_kinds)

    def test_ruby_rails_extracts_routes_qualified_methods_and_real_branches(self):
        bundle = ruby_lang.parse_workspace(FIXTURE_ROOT / "ruby_rails")

        self.assertEqual(bundle["schema"], FACT_SCHEMA)

        imports = {fact["specifier"] for fact in _facts(bundle, "import")}
        self.assertIn("net/http", imports)

        symbols = {fact["name"] for fact in _facts(bundle, "symbol")}
        self.assertIn("Jobs", symbols)
        self.assertIn("CheckoutJob", symbols)
        self.assertIn("self.call", symbols)

        routes = {
            (fact["method"], fact["path"], fact.get("handler"), fact["kind"])
            for fact in _facts(bundle, "route")
        }
        self.assertIn((None, "/", "home#index", "rails-root"), routes)
        self.assertIn((None, "users", None, "rails-resource"), routes)
        self.assertIn(("GET", "/health", "health#show", "rails-route"), routes)

        route_paths = {fact["path"] for fact in _facts(bundle, "route")}
        self.assertNotIn("/commented", route_paths)

        branches = _facts(bundle, "branch")
        self.assertEqual(["if", "else-if", "else"], [fact["branch_kind"] for fact in branches])
        self.assertNotIn("this string should not count", {fact["condition"] for fact in branches})

        calls = {fact["function"] for fact in _facts(bundle, "call")}
        self.assertIn("NotifyUser.call", calls)
        self.assertIn("Audit.log", calls)
        self.assertIn("ArchiveOrder.call", calls)
        self.assertNotIn("end", calls)


if __name__ == "__main__":
    unittest.main()
