"""Bootstrap prompt rendering for AgentCanvas."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from string import Template


DEFAULT_AGENT_LABEL = "the calling coding agent"


def render_bootstrap_prompt(
    *,
    workspace: Path,
    agent_label: str | None = None,
    workflow_relative_path: str,
    canvas_relative_path: str,
    canvas_path: Path,
) -> str:
    """Render the packaged bootstrap prompt for a calling agent."""

    label = _clean_agent_label(agent_label)
    template = _bootstrap_template()
    return template.substitute(
        agent_label=label,
        workspace=str(workspace),
        workspace_shell=shlex.quote(str(workspace)),
        workflow_relative_path=workflow_relative_path,
        canvas_relative_path=canvas_relative_path,
        canvas_path=str(canvas_path),
    ).strip()


def _clean_agent_label(agent_label: str | None) -> str:
    if not isinstance(agent_label, str):
        return DEFAULT_AGENT_LABEL
    label = re.sub(r"\s+", " ", agent_label).strip()
    return label[:80] if label else DEFAULT_AGENT_LABEL


def _bootstrap_template() -> Template:
    text = (Path(__file__).resolve().parent / "templates" / "bootstrap_prompt.md").read_text(
        encoding="utf-8"
    )
    return Template(text)
