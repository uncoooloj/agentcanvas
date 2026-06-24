import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.core import (
    annotate_bundle_with_surfaces,
    app_surface_for_path,
    detect_app_surfaces,
    infer_workspace_profile,
)


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _workspace_files(root: Path):
    return sorted(path for path in root.rglob("*") if path.is_file())


class AppSurfaceDetectionTests(unittest.TestCase):
    maxDiff = None

    def test_detects_mobile_web_and_backend_signup_surfaces_in_monorepo(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _write(
                root,
                "apps/mobile/pubspec.yaml",
                "name: agentcanvas_mobile\n"
                "dependencies:\n"
                "  flutter:\n"
                "    sdk: flutter\n",
            )
            _write(root, "apps/mobile/lib/main.dart", "void main() {}\n")
            _write(
                root,
                "apps/mobile/lib/screens/signup.dart",
                "class SignupScreen {}\n",
            )
            _write(
                root,
                "apps/web/package.json",
                json.dumps(
                    {
                        "name": "@agentcanvas/web",
                        "scripts": {"dev": "next dev", "build": "next build"},
                        "dependencies": {
                            "next": "15.0.0",
                            "react": "19.0.0",
                            "react-dom": "19.0.0",
                        },
                    }
                ),
            )
            _write(root, "apps/web/src/main.tsx", "export function boot() {}\n")
            _write(
                root,
                "apps/web/src/app/signup/page.tsx",
                "export default function SignupPage() { return null }\n",
            )
            _write(root, "apps/backend/go.mod", "module example.com/agentcanvas/backend\n")
            _write(
                root,
                "apps/backend/composer.json",
                json.dumps({"require": {"laravel/framework": "^11.0"}}),
            )
            _write(root, "apps/backend/Gemfile", "source 'https://rubygems.org'\ngem 'rails'\n")
            _write(root, "apps/backend/cmd/api/main.go", "package main\nfunc main() {}\n")
            _write(
                root,
                "apps/backend/internal/signup/handler.go",
                "package signup\nfunc Handler() {}\n",
            )

            surfaces = detect_app_surfaces(root, _workspace_files(root))
            by_root = {surface["root"]: surface for surface in surfaces}

            self.assertEqual({"apps/backend", "apps/mobile", "apps/web"}, set(by_root))
            self.assertEqual(
                {
                    "apps/mobile": "mobile",
                    "apps/web": "web",
                    "apps/backend": "backend",
                },
                {surface_root: surface["type"] for surface_root, surface in by_root.items()},
            )
            self.assertEqual("app:mobile", by_root["apps/mobile"]["id"])
            self.assertEqual("app:web", by_root["apps/web"]["id"])
            self.assertEqual("app:backend", by_root["apps/backend"]["id"])

            self.assertIn("apps/mobile/pubspec.yaml", by_root["apps/mobile"]["manifest_paths"])
            self.assertIn("apps/web/package.json", by_root["apps/web"]["manifest_paths"])
            self.assertEqual(
                {
                    "apps/backend/Gemfile",
                    "apps/backend/composer.json",
                    "apps/backend/go.mod",
                },
                set(by_root["apps/backend"]["manifest_paths"]),
            )

            mobile_hints = {hint["path"] for hint in by_root["apps/mobile"]["entry_hints"]}
            web_hints = {hint["path"]: hint for hint in by_root["apps/web"]["entry_hints"]}
            backend_hints = {hint["path"] for hint in by_root["apps/backend"]["entry_hints"]}

            self.assertIn("apps/mobile/lib/main.dart", mobile_hints)
            self.assertIn("apps/mobile/lib/screens/signup.dart", mobile_hints)
            self.assertEqual("/signup", web_hints["apps/web/src/app/signup/page.tsx"]["detail"])
            self.assertIn("apps/backend/cmd/api/main.go", backend_hints)
            self.assertIn("apps/backend/internal/signup/handler.go", backend_hints)

            self.assertEqual(
                "app:mobile",
                app_surface_for_path("apps/mobile/lib/screens/signup.dart", surfaces)["id"],
            )
            self.assertEqual(
                "app:web",
                app_surface_for_path("apps/web/src/app/signup/page.tsx", surfaces)["id"],
            )
            self.assertEqual(
                "app:backend",
                app_surface_for_path("apps/backend/internal/signup/handler.go", surfaces)["id"],
            )

    def test_annotates_language_facts_with_surface_metadata(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            _write(root, "apps/mobile/pubspec.yaml", "name: mobile\ndependencies:\n  flutter:\n")
            _write(root, "apps/mobile/lib/screens/signup.dart", "class SignupScreen {}\n")
            _write(
                root,
                "apps/web/package.json",
                json.dumps({"dependencies": {"next": "15.0.0", "react": "19.0.0"}}),
            )
            _write(root, "apps/web/src/app/signup/page.tsx", "export default function Page() {}\n")
            _write(root, "apps/backend/go.mod", "module example.com/backend\n")
            _write(root, "apps/backend/internal/signup/handler.go", "package signup\n")
            surfaces = detect_app_surfaces(root, _workspace_files(root))
            bundle = {
                "facts": [
                    {"id": "mobile", "file": "apps/mobile/lib/screens/signup.dart"},
                    {
                        "id": "web",
                        "path": "/signup",
                        "source_ref": {"path": "apps/web/src/app/signup/page.tsx"},
                    },
                    {"id": "backend", "file": "apps/backend/internal/signup/handler.go"},
                ]
            }

            annotate_bundle_with_surfaces(bundle, surfaces)

            by_id = {fact["id"]: fact for fact in bundle["facts"]}
            self.assertEqual("app:mobile", by_id["mobile"]["app_surface_id"])
            self.assertEqual("mobile", by_id["mobile"]["app_surface_type"])
            self.assertEqual("app:web", by_id["web"]["app_surface_id"])
            self.assertEqual("web", by_id["web"]["app_surface_type"])
            self.assertEqual("app:backend", by_id["backend"]["app_surface_id"])
            self.assertEqual("backend", by_id["backend"]["app_surface_type"])

    def test_infers_app_workspace_profile_from_web_surface(self):
        profile = infer_workspace_profile(
            {
                "workspace": {"name": "shop"},
                "summary": {"routes": 0},
                "app_surfaces": [
                    {
                        "id": "app:web",
                        "name": "web",
                        "type": "web",
                        "root": ".",
                        "manifest_paths": ["package.json"],
                    }
                ],
            }
        )

        self.assertEqual("app", profile["kind"])
        self.assertEqual("app", profile["product_language"]["singular"])

    def test_infers_backend_workspace_profile_from_routes_and_surface(self):
        profile = infer_workspace_profile(
            {
                "workspace": {"name": "orders-api"},
                "summary": {"routes": 3},
                "app_surfaces": [
                    {
                        "id": "app:backend",
                        "name": "backend",
                        "type": "backend",
                        "root": ".",
                        "manifest_paths": ["go.mod"],
                    }
                ],
            }
        )

        self.assertEqual("api_backend", profile["kind"])
        self.assertEqual("service", profile["product_language"]["singular"])

    def test_infers_library_package_profile_from_package_surface(self):
        profile = infer_workspace_profile(
            {
                "workspace": {"name": "example-sdk"},
                "summary": {},
                "package": {"manifests": [{"path": "sdk/python/pyproject.toml"}]},
                "app_surfaces": [
                    {
                        "id": "app:python",
                        "name": "python",
                        "type": "package",
                        "root": "sdk/python",
                        "manifest_paths": ["sdk/python/pyproject.toml"],
                    }
                ],
            }
        )

        self.assertEqual("library_package", profile["kind"])
        self.assertEqual("package", profile["product_language"]["singular"])

    def test_infers_monorepo_profile_from_mixed_app_surfaces(self):
        profile = infer_workspace_profile(
            {
                "workspace": {"name": "acme-platform"},
                "summary": {"routes": 4},
                "app_surfaces": [
                    {"id": "app:web", "name": "web", "type": "web", "root": "apps/web"},
                    {"id": "app:mobile", "name": "mobile", "type": "mobile", "root": "apps/mobile"},
                    {"id": "app:api", "name": "api", "type": "backend", "root": "apps/api"},
                ],
            }
        )

        self.assertEqual("monorepo_mixed", profile["kind"])
        self.assertEqual("workspace", profile["product_language"]["singular"])


if __name__ == "__main__":
    unittest.main()
