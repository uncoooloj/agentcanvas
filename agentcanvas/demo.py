"""Built-in demo workspace helpers for AgentCanvas."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path


DEMO_FIXTURE_NAME = "agentcanvas-demo"


def demo_fixture() -> Path:
    """Return the best available read-only demo fixture path."""

    package_root = Path(__file__).resolve().parent
    repo_root = package_root.parent

    rich_fixture = repo_root / "demo_projects" / DEMO_FIXTURE_NAME
    if rich_fixture.exists():
        return rich_fixture.resolve()

    packaged_fixture = package_root / "demo_project"
    if packaged_fixture.exists():
        return packaged_fixture.resolve()

    return (repo_root / "examples" / "sample-js-app").resolve()


def demo_workspace() -> Path:
    """Copy the demo fixture into a writable temp workspace and return it."""

    source = demo_fixture()
    temp_root = Path(tempfile.mkdtemp(prefix="agentcanvas-demo-"))
    target = temp_root / source.name
    ignore = shutil.ignore_patterns(".agentcanvas", "node_modules", "__pycache__")
    shutil.copytree(str(source), str(target), ignore=ignore)
    marker = target / ".agentcanvas-demo"
    marker.write_text(f"fixture={source.name}\nid={uuid.uuid4().hex}\n", encoding="utf-8")
    return target.resolve()
