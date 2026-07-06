"""Bootstrap prompt rendering for AgentCanvas."""

from __future__ import annotations

import re
import shlex
from importlib import resources
from pathlib import Path, PurePath
from string import Template
from typing import Dict, List


DEFAULT_AGENT_LABEL = "the calling coding agent"
LANDING_AGENT_LABEL = "your AI coding agent"
LANDING_WORKSPACE = Path("./your-project")
BOOTSTRAP_PERMISSION_PROMPTS = [
    {
        "label": "Install",
        "reason": "Only if AgentCanvas is not already available.",
    },
    {
        "label": "Run",
        "reason": "Starts the localhost AgentCanvas server for this workspace.",
    },
    {
        "label": "Connect",
        "reason": "Only when your agent uses the optional MCP bridge.",
    },
]
SUPPORTED_SETUP_AGENTS = {"claude-code", "codex", "cursor", "antigravity", "generic", "auto"}


def render_bootstrap_prompt(
    *,
    workspace: PurePath,
    agent_label: str | None = None,
    workflow_relative_path: str,
    canvas_relative_path: str,
    canvas_path: PurePath,
) -> str:
    """Render the packaged bootstrap prompt for a calling agent."""

    label = _clean_agent_label(agent_label)
    template = _bootstrap_template()
    workspace_prompt = _prompt_path(workspace)
    canvas_path_prompt = _prompt_path(canvas_path)
    return template.substitute(
        agent_label=label,
        agent_setup_arg=_agent_setup_arg(label),
        workspace=workspace_prompt,
        workspace_shell=shlex.quote(workspace_prompt),
        workflow_relative_path=workflow_relative_path,
        canvas_relative_path=canvas_relative_path,
        canvas_path=canvas_path_prompt,
    ).strip()


def build_landing_bootstrap_prompt() -> str:
    """Return the website prompt block rendered from the packaged template."""

    return render_bootstrap_prompt(
        workspace=LANDING_WORKSPACE,
        agent_label=LANDING_AGENT_LABEL,
        workflow_relative_path=".agentcanvas/workflow.ir.json",
        canvas_relative_path=".agentcanvas/canvas.ir.json",
        canvas_path=LANDING_WORKSPACE / ".agentcanvas" / "canvas.ir.json",
    )


def build_bootstrap_permission_prompts() -> List[Dict[str, str]]:
    """Return the expected first-run permission prompts for website narration."""

    return [dict(item) for item in BOOTSTRAP_PERMISSION_PROMPTS]


def _clean_agent_label(agent_label: str | None) -> str:
    if not isinstance(agent_label, str):
        return DEFAULT_AGENT_LABEL
    label = re.sub(r"\s+", " ", agent_label).strip()
    return label[:80] if label else DEFAULT_AGENT_LABEL


def _agent_setup_arg(agent_label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", agent_label.lower()).strip("-")
    return key if key in SUPPORTED_SETUP_AGENTS else "auto"


def _prompt_path(path: PurePath) -> str:
    return str(path).replace("\\", "/")


def _bootstrap_template() -> Template:
    if hasattr(resources, "files"):
        text = resources.files("agentcanvas").joinpath("templates/bootstrap_prompt.md").read_text(encoding="utf-8")
    else:
        text = Path(__file__).with_name("templates").joinpath("bootstrap_prompt.md").read_text(encoding="utf-8")
    return Template(text)
