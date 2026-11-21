import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcanvas.git_diff import (
    compute_stale_node_ids,
    get_file_diff,
    get_git_status,
    get_workspace_diff_summary,
    read_file_slice,
    resolve_workspace_path,
    safe_resolve_workspace_file,
)


class GitDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "workspace"
        self.root.mkdir()

    def git(self, *args):
        command = [
            "git", "-C", str(self.root), "-c", "user.name=Studio Test",
            "-c", "user.email=studio@example.test", "-c", "core.hooksPath=/dev/null",
            "-c", "core.autocrlf=false", *args,
        ]
        return subprocess.run(command, check=True, capture_output=True, timeout=5, text=True).stdout.strip()

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(text.encode("utf-8"))
        return file

    def init_repo(self):
        self.git("init", "-q", "-b", "main")

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "--no-gpg-sign", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def test_slice_windows_and_clamps_context(self):
        self.write("source.py", "".join(f"line {number}\n" for number in range(1, 201)))
        result = read_file_slice(self.root, "source.py", 100, 3)
        self.assertEqual((result["start_line"], result["end_line"], result["highlight_line"]), (97, 103, 100))
        self.assertEqual(result["lines"][3], {"number": 100, "text": "line 100"})
        self.assertEqual(result["absolute_path"], str(self.root / "source.py"))
        self.assertEqual(result["language"], "python")
        self.assertLessEqual(len(read_file_slice(self.root, "source.py", 100, 999)["lines"]), 120)
        self.assertEqual(read_file_slice(self.root, "source.py", 300, 2)["highlight_line"], 200)
        self.assertEqual(read_file_slice(self.root, "source.py", 1, 0)["lines"], [{"number": 1, "text": "line 1"}])
        with self.assertRaises(ValueError):
            read_file_slice(self.root, "source.py", 0)
        with self.assertRaises(ValueError):
            read_file_slice(self.root, "source.py", 1, -1)

    def test_missing_binary_empty_and_symlinked_sources(self):
        self.assertEqual(read_file_slice(self.root, "missing.py")["error"], "FILE_NOT_FOUND")
        (self.root / "bin").write_bytes(b"hello\0world")
        self.assertEqual(read_file_slice(self.root, "bin")["error"], "BINARY_FILE")
        self.write("empty", "")
        self.assertEqual(read_file_slice(self.root, "empty")["lines"], [])
        target = self.write("sample.py", "print('hi')\n")
        (self.root / "local.py").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "^PATH_OUTSIDE_WORKSPACE$"):
            read_file_slice(self.root, "local.py", 1)

    def test_rejects_internal_paths_and_internal_symlink_aliases(self):
        state = self.root / ".agentcanvas"
        state.mkdir()
        (state / "launch.json").write_text("{}", encoding="utf-8")
        metadata = self.root / ".git"
        metadata.mkdir()
        (metadata / "config").write_text("[core]\n", encoding="utf-8")
        (self.root / "state-alias").symlink_to(state, target_is_directory=True)
        (self.root / "metadata-alias").symlink_to(metadata, target_is_directory=True)
        for path in (
            ".agentcanvas/launch.json",
            ".AGENTCANVAS/launch.json",
            ".git/config",
            ".GIT/config",
            "state-alias/launch.json",
            "metadata-alias/config",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "^INTERNAL_PATH_FORBIDDEN$"):
                    safe_resolve_workspace_file(self.root, path)

    def test_resolve_workspace_path_allows_internal_paths_but_rejects_symlinks(self):
        state = self.root / ".agentcanvas"
        state.mkdir()
        launch = state / "launch.json"
        launch.write_text("{}", encoding="utf-8")
        target = self.write("source.py", "print('hi')\n")
        (self.root / "source-alias.py").symlink_to(target)
        self.assertEqual(resolve_workspace_path(self.root, ".agentcanvas/launch.json"), launch)
        with self.assertRaisesRegex(ValueError, "^PATH_OUTSIDE_WORKSPACE$"):
            resolve_workspace_path(self.root, "source-alias.py")

    def test_rejects_traversal_absolute_paths_and_symlink_escapes(self):
        outside = self.base / "neighbor.txt"
        outside.write_text("private fixture", encoding="utf-8")
        (self.root / "outside-link").symlink_to(outside)
        (self.root / "outside-dir").symlink_to(self.base, target_is_directory=True)
        for path in ("../neighbor.txt", "src/../src/foo.py", str(outside), r"C:\\foo.py", "outside-link", "outside-dir/neighbor.txt"):
            for operation in (safe_resolve_workspace_file, read_file_slice, get_file_diff):
                with self.subTest(path=path, operation=operation.__name__):
                    with self.assertRaisesRegex(ValueError, "^PATH_OUTSIDE_WORKSPACE$"):
                        operation(self.root, path)

    def test_non_git_workspace_is_usable(self):
        self.write("app.py", "print('hi')\n")
        self.assertEqual(get_git_status(self.root), {"branch": None, "head": None, "dirty": False, "changed_files": []})
        self.assertFalse(get_file_diff(self.root, "app.py")["has_diff"])
        self.assertEqual(get_workspace_diff_summary(self.root)["patch"], "")

    def test_broken_git_metadata_is_distinct_from_a_clean_workspace(self):
        self.write(".git", "gitdir: missing-object-store\n")
        self.assertEqual(get_git_status(self.root)["error"], "GIT_STATUS_UNAVAILABLE")
        self.assertEqual(get_file_diff(self.root, "app.py")["error"], "GIT_DIFF_UNAVAILABLE")
        self.assertEqual(get_workspace_diff_summary(self.root)["error"], "GIT_DIFF_UNAVAILABLE")

    def test_status_staleness_and_hunks_against_commits_and_worktree(self):
        self.init_repo()
        self.write("app.py", "before\n")
        self.write("delete.py", "delete me\n")
        self.write("untouched.py", "steady\n")
        start = self.commit("Baseline")
        self.write("app.py", "committed\n")
        self.git("mv", "delete.py", "moved.py")
        head = self.commit("Committed updates")
        self.write("app.py", "working\nextra line\n")
        self.git("add", "app.py")
        self.write("extra.py", "untracked\n")
        self.write(".agentcanvas/launch.json", "dummy launch data")
        status = get_git_status(self.root)
        self.assertEqual(status, {"branch": "main", "head": head, "dirty": True, "changed_files": ["app.py", "extra.py"]})
        document = {"git_head": start, "flows": [{"nodes": [
            {"id": name, "code_refs": [{"path": name}]} for name in ("app.py", "delete.py", "untouched.py", "extra.py")
        ]}]}
        self.assertEqual(compute_stale_node_ids(self.root, document), ["app.py", "delete.py", "extra.py"])

        working = get_file_diff(self.root, "app.py")
        self.assertTrue(working["has_diff"])
        self.assertEqual((working["additions"], working["deletions"]), (2, 1))
        self.assertIn({"kind": "addition", "text": "+working"}, working["hunks"][0]["lines"])
        committed = get_file_diff(self.root, "app.py", start + "..HEAD")
        self.assertIn({"kind": "addition", "text": "+committed"}, committed["hunks"][0]["lines"])
        self.assertEqual(committed["additions"], 1)
        self.assertEqual(get_file_diff(self.root, "extra.py")["additions"], 1)
        self.assertFalse(get_file_diff(self.root, "extra.py", start + "..HEAD")["has_diff"])
        self.assertEqual(get_file_diff(self.root, "app.py", "--output=unexpected")["error"], "INVALID_DIFF_BASE")

    def test_nested_workspace_and_literal_git_paths(self):
        self.init_repo()
        self.write("other.txt", "top\n")
        self.write("nested/[file].py", "one\n")
        self.write("nested/f.py", "stay\n")
        start = self.commit("Start")
        self.write("nested/[file].py", "two\n")
        self.write("other.txt", "changed\n")
        self.commit("Edit")
        self.write("nested/[file].py", "three\n")
        self.write("other.txt", "scratch\n")
        root = self.root / "nested"
        with patch.dict(os.environ, {"GIT_DIR": str(self.base / "unrelated")}):
            self.assertEqual(get_git_status(root)["changed_files"], ["[file].py"])
            self.assertEqual(get_file_diff(root, "[file].py")["additions"], 1)
            self.assertEqual(compute_stale_node_ids(root, {"git_head": start, "flows": [{"nodes": [
                {"id": "inside", "code_refs": [{"path": "[file].py"}]},
                {"id": "outside", "code_refs": [{"path": "other.txt"}]},
            ]}]}), ["inside"])
            summary = get_workspace_diff_summary(root)
        self.assertIn("[file].py", summary["stat"])
        self.assertNotIn("other.txt", summary["patch"])

    def test_patch_summary_truncates_large_changes_and_excludes_studio_state(self):
        self.init_repo()
        self.write("big.txt", "baseline\n")
        self.commit("Start")
        self.write("big.txt", ("A" * 75 + "\n") * 1000)
        self.write(".agentcanvas/runs.json", "mock private prompt\n")
        summary = get_workspace_diff_summary(self.root)
        self.assertTrue(summary["truncated"])
        self.assertLessEqual(len(summary["patch"].encode()), 40 * 1024)
        self.assertIn("big.txt", summary["stat"])
        self.assertNotIn("mock private prompt", summary["patch"])

    def test_diff_in_unborn_repository_includes_staged_and_untracked(self):
        self.init_repo()
        self.write("added.py", "one\n")
        self.git("add", "added.py")
        self.write("untracked.py", "two\n")
        self.assertEqual(get_file_diff(self.root, "added.py")["additions"], 1)
        self.assertEqual(get_file_diff(self.root, "untracked.py")["additions"], 1)
        summary = get_workspace_diff_summary(self.root)
        self.assertIn("+one", summary["patch"])
        self.assertIn("+two", summary["patch"])

    def test_passive_evidence_disables_required_git_filters(self):
        self.init_repo()
        self.write("src/app.txt", "before\n")
        self.write(".gitattributes", "*.txt filter=fixture\n")
        self.commit("Start")
        self.git("config", "filter.fixture.clean", str(self.base / "missing-fixture-binary"))
        self.git("config", "filter.fixture.required", "true")
        self.write("src/app.txt", "after\n")
        self.assertEqual(get_git_status(self.root)["changed_files"], ["src/app.txt"])
        self.assertEqual(get_file_diff(self.root, "src/app.txt")["additions"], 1)
        self.assertEqual(get_file_diff(self.root, "src")["error"], "INVALID_FILE_PATH")


if __name__ == "__main__":
    unittest.main()
