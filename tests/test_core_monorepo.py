import json
import tempfile
import unittest
from pathlib import Path

from agentcanvas.indexer import build_workflow_ir


def write_text(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents.strip() + "\n", encoding="utf-8")


class CoreMonorepoIndexerTests(unittest.TestCase):
    maxDiff = None

    def test_workflow_ir_reports_new_languages_and_distinct_app_surfaces(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "polyglot-monorepo"
            workspace.mkdir()

            write_text(
                workspace / "package.json",
                json.dumps(
                    {
                        "private": True,
                        "workspaces": ["apps/*", "services/*"],
                        "scripts": {"test": "echo test"},
                    }
                ),
            )
            write_text(
                workspace / "apps/customer-web/package.json",
                json.dumps(
                    {
                        "name": "@acme/customer-web",
                        "scripts": {"dev": "vite --host 127.0.0.1"},
                        "dependencies": {"@vitejs/plugin-react": "latest"},
                    }
                ),
            )
            write_text(
                workspace / "apps/admin/package.json",
                json.dumps(
                    {
                        "name": "@acme/admin",
                        "scripts": {"dev": "next dev"},
                        "dependencies": {"next": "latest", "react": "latest"},
                    }
                ),
            )

            write_text(
                workspace / "apps/customer-web/src/routes/checkout.ts",
                """
                export function checkoutRoute(cart: { items: unknown[] }) {
                  if (cart.items.length === 0) {
                    return "empty";
                  }
                  return "ready";
                }
                """,
            )
            write_text(
                workspace / "apps/admin/src/routes/users.ts",
                """
                export function usersRoute(isAdmin: boolean) {
                  if (isAdmin) {
                    return "users";
                  }
                  return "forbidden";
                }
                """,
            )
            write_text(
                workspace / "services/api/main.go",
                """
                package main

                import "net/http"

                func main() {
                  http.HandleFunc("/health", health)
                }

                func health(w http.ResponseWriter, r *http.Request) {}
                """,
            )
            write_text(
                workspace / "services/laravel/routes/web.php",
                """
                <?php

                use Illuminate\\Support\\Facades\\Route;

                Route::get('/orders', function () {
                    return 'orders';
                });
                """,
            )
            write_text(
                workspace / "services/rails/config/routes.rb",
                """
                Rails.application.routes.draw do
                  resources :orders
                end
                """,
            )
            write_text(
                workspace / "apps/flutter/lib/main.dart",
                """
                import 'package:flutter/widgets.dart';

                class OrdersScreen extends StatelessWidget {
                  Widget build(BuildContext context) {
                    return Container();
                  }
                }
                """,
            )
            write_text(
                workspace / "apps/ios/App/HomeView.swift",
                """
                import SwiftUI

                struct HomeView: View {
                  var body: some View {
                    Text("Home")
                  }
                }
                """,
            )
            write_text(
                workspace / "apps/android/app/src/main/java/com/acme/MainActivity.kt",
                """
                package com.acme

                import androidx.compose.runtime.Composable

                @Composable
                fun App() {
                  if (true) {
                    Screen()
                  }
                }
                """,
            )

            workflow_ir = build_workflow_ir(workspace)

            self.assertTrue(
                {
                    "javascript-typescript",
                    "go",
                    "php-laravel",
                    "ruby-rails",
                    "dart-flutter",
                    "swift",
                    "kotlin",
                }.issubset(set(workflow_ir["summary"].get("language_modules", [])))
            )

            surfaces = workflow_ir.get("app_surfaces") or []
            self.assertEqual(workflow_ir["summary"].get("app_surfaces"), len(surfaces))

            surface_paths = {
                surface.get("path") or surface.get("root") or surface.get("workspace_path")
                for surface in surfaces
            }
            self.assertTrue(all(surface_paths))
            self.assertIn("apps/customer-web", surface_paths)
            self.assertIn("apps/admin", surface_paths)
            self.assertGreaterEqual(len(surface_paths), 2)

            surface_ids = [surface.get("id") for surface in surfaces]
            self.assertTrue(all(surface_ids))
            self.assertEqual(len(surface_ids), len(set(surface_ids)))


if __name__ == "__main__":
    unittest.main()
