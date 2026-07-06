import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentcanvas.adapters import (
    AGENT_UNDETECTED_EXIT,
    AdapterSetupError,
    detect_agent,
    render_skill_template,
    setup_adapter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _agentcanvas_env(extra=None):
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    for key in list(env):
        if key.startswith(("CLAUDE", "CODEX", "OPENAI_CODEX", "CURSOR")):
            env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def _snapshot(root):
    files = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            files[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return files


class AdapterSetupTests(unittest.TestCase):
    maxDiff = None

    def test_setup_codex_writes_marked_section_and_preserves_outside_content(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            agents_path = workspace / "AGENTS.md"
            agents_path.write_text("# Project Rules\n\nKeep this.\n", encoding="utf-8")

            result = setup_adapter(workspace, agent="codex")
            first = _snapshot(workspace)
            result_again = setup_adapter(workspace, agent="codex")
            second = _snapshot(workspace)

            self.assertTrue(result["ok"])
            self.assertEqual(first, second)
            self.assertEqual(result_again["agent"], "codex")
            text = agents_path.read_text(encoding="utf-8")
            self.assertIn("Keep this.", text)
            self.assertIn("<!-- agentcanvas:start -->", text)
            self.assertIn("<!-- agentcanvas:end -->", text)
            self.assertIn("agentcanvas_workspace_status", text)
            self.assertIn("codex_config_snippet", result)
            self.assertFalse(result["codex_config_written"])

    def test_setup_claude_and_cursor_merge_mcp_config_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            (workspace / ".mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "existing": {"command": "already-here", "args": []}
                        }
                    }
                ),
                encoding="utf-8",
            )

            setup_adapter(workspace, agent="claude-code")
            first = _snapshot(workspace)
            setup_adapter(workspace, agent="claude-code")
            second = _snapshot(workspace)
            self.assertEqual(first, second)

            skill = workspace / ".claude" / "skills" / "agentcanvas" / "SKILL.md"
            self.assertEqual(skill.read_text(encoding="utf-8"), render_skill_template())
            mcp = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn("existing", mcp["mcpServers"])
            self.assertEqual(mcp["mcpServers"]["agentcanvas"]["command"], "agentcanvas")

            setup_adapter(workspace, agent="cursor")
            cursor_first = _snapshot(workspace)
            setup_adapter(workspace, agent="cursor")
            cursor_second = _snapshot(workspace)
            self.assertEqual(cursor_first, cursor_second)
            cursor_rule = workspace / ".cursor" / "rules" / "agentcanvas.mdc"
            self.assertIn("Cursor Notes", cursor_rule.read_text(encoding="utf-8"))
            cursor_mcp = json.loads((workspace / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(cursor_mcp["mcpServers"]["agentcanvas"]["args"][0], "mcp")

    def test_setup_generic_has_zero_mcp_mentions_and_antigravity_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            generic = setup_adapter(workspace, agent="generic")
            self.assertTrue(generic["ok"])
            generic_text = (workspace / "AGENT_CANVAS.md").read_text(encoding="utf-8")
            self.assertNotIn("MCP", generic_text)
            self.assertNotIn("mcp", generic_text)

            before = _snapshot(workspace)
            antigravity = setup_adapter(workspace, agent="antigravity")
            after = _snapshot(workspace)
            self.assertEqual(before, after)
            self.assertEqual(antigravity["written"], [])
            self.assertIn("experimental", antigravity["message"])
            self.assertIn("agentcanvas", antigravity["mcp"])

    def test_auto_detection_uses_env_then_workspace_and_reports_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            self.assertEqual(
                detect_agent(workspace, env={"CODEX_SESSION_ID": "abc"}).agent,
                "codex",
            )
            (workspace / ".claude").mkdir()
            self.assertEqual(detect_agent(workspace, env={}).agent, "claude-code")
            (workspace / ".cursor").mkdir()
            ambiguous = detect_agent(workspace, env={})
            self.assertIsNone(ambiguous.agent)
            self.assertTrue(ambiguous.ambiguous)
            self.assertIn("claude-code", ambiguous.matches)
            self.assertIn("cursor", ambiguous.matches)

            empty = Path(temp_root) / "empty"
            empty.mkdir()
            self.assertIsNone(detect_agent(empty, env={}).agent)

    def test_setup_auto_error_contract_and_init_alias_cli(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()

            with self.assertRaises(AdapterSetupError) as raised:
                setup_adapter(workspace, agent="auto", env={})
            self.assertEqual(raised.exception.code, "AGENT_UNDETECTED")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "setup",
                    "--workspace",
                    str(workspace),
                    "--agent",
                    "auto",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(completed.returncode, AGENT_UNDETECTED_EXIT)
            self.assertEqual(completed.stdout, "")
            self.assertIn("AGENT_UNDETECTED", completed.stderr)

            codex_workspace = Path(temp_root) / "codex-workspace"
            codex_workspace.mkdir()
            (codex_workspace / "AGENTS.md").write_text(
                "# AGENTS.md instructions\n",
                encoding="utf-8",
            )
            alias = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentcanvas",
                    "init",
                    "--workspace",
                    str(codex_workspace),
                    "--agent",
                    "auto",
                ],
                cwd=temp_root,
                env=_agentcanvas_env(),
                text=True,
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(alias.returncode, 0, alias.stdout + alias.stderr)
            payload = json.loads(alias.stdout)
            self.assertEqual(payload["agent"], "codex")
            self.assertTrue((codex_workspace / "AGENTS.md").is_file())

    def test_codex_config_write_is_opt_in_and_backed_up(self):
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root) / "workspace"
            workspace.mkdir()
            config_path = Path(temp_root) / "config.toml"
            config_path.write_text("# existing\n", encoding="utf-8")

            setup_adapter(workspace, agent="codex")
            self.assertEqual(config_path.read_text(encoding="utf-8"), "# existing\n")

            result = setup_adapter(
                workspace,
                agent="codex",
                write_codex_config=True,
                codex_config_path=config_path,
            )
            self.assertTrue(result["codex_config_written"])
            self.assertTrue(Path(result["codex_config_backup"]).is_file())
            self.assertIn("[mcp_servers.agentcanvas]", config_path.read_text(encoding="utf-8"))
            self.assertIn("[mcp_servers.agentcanvas]", result["codex_config_diff"])

    def test_repo_skill_is_generated_from_packaged_template(self):
        skill_path = PROJECT_ROOT / "skill" / "agentcanvas" / "SKILL.md"
        self.assertEqual(skill_path.read_text(encoding="utf-8"), render_skill_template())


if __name__ == "__main__":
    unittest.main()
