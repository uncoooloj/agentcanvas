"""Evidence fingerprint helpers for canvas v2 documents.

The helpers here are intentionally stdlib-only and side-effect light. They
compute the evidence object a v2 canvas can embed to prove which workflow IR it
was authored from, then compare that embedded evidence with the current
workspace evidence.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from agentcanvas.ir import IR_FILENAME, STATE_DIR_NAME, resolve_workspace, state_paths


EVIDENCE_STATUS_FRESH = "fresh"
EVIDENCE_STATUS_STALE = "stale"
EVIDENCE_STATUS_POSSIBLY_STALE = "possibly-stale"

EVIDENCE_FIELDS = (
    "git_head",
    "workflow_generated_at",
    "workflow_sha256",
    "source_facts_sha256",
)


def build_current_workflow_evidence(workspace: Any) -> Dict[str, Optional[str]]:
    """Return a canvas v2 evidence object for the workspace workflow IR."""

    root = resolve_workspace(workspace)
    _state_dir, workflow_path, _pending_dir = state_paths(root)
    return build_workflow_evidence_from_path(workflow_path, workspace=root)


def build_workflow_evidence_from_path(
    workflow_path: Any,
    *,
    workspace: Any = None,
) -> Dict[str, Optional[str]]:
    """Return evidence for a workflow IR file, hashing its exact bytes."""

    path = Path(workflow_path)
    workflow_bytes = path.read_bytes()
    workflow_ir = json.loads(workflow_bytes.decode("utf-8"))
    if not isinstance(workflow_ir, Mapping):
        raise ValueError("%s must contain a JSON object" % path)

    root = resolve_workspace(workspace) if workspace is not None else _default_workspace(path)
    return build_workflow_evidence(
        workflow_ir,
        workflow_bytes=workflow_bytes,
        git_head=current_git_head(root),
    )


def build_workflow_evidence(
    workflow_ir: Mapping[str, Any],
    *,
    workflow_bytes: bytes,
    git_head: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Return the top-level canvas v2 evidence object for a workflow IR."""

    return {
        "git_head": git_head,
        "workflow_generated_at": _optional_string(workflow_ir.get("generated_at")),
        "workflow_sha256": sha256_hex(workflow_bytes),
        "source_facts_sha256": source_facts_sha256(workflow_ir.get("source_facts")),
    }


def compare_canvas_evidence(
    canvas_evidence: Any,
    current_evidence: Mapping[str, Optional[str]],
) -> Dict[str, Any]:
    """Compare embedded canvas evidence with current workflow evidence.

    Exact fingerprint mismatches are stale. Missing evidence, missing current
    values, or non-object canvas evidence are possibly stale because the helper
    cannot prove freshness.
    """

    if not isinstance(current_evidence, Mapping):
        raise ValueError("current_evidence must be a mapping")

    if not isinstance(canvas_evidence, Mapping):
        return {
            "status": EVIDENCE_STATUS_POSSIBLY_STALE,
            "stale": None,
            "reasons": ["canvas evidence is missing or not an object"],
            "mismatched_fields": [],
            "unknown_fields": list(EVIDENCE_FIELDS),
        }

    mismatched = []
    unknown = []
    for field in EVIDENCE_FIELDS:
        canvas_value = _optional_string(canvas_evidence.get(field))
        current_value = _optional_string(current_evidence.get(field))
        if canvas_value is None or current_value is None:
            if canvas_value != current_value:
                unknown.append(field)
            continue
        if canvas_value != current_value:
            mismatched.append(field)

    reasons = []
    if mismatched:
        reasons.append("canvas evidence does not match current workflow evidence")
        return {
            "status": EVIDENCE_STATUS_STALE,
            "stale": True,
            "reasons": reasons,
            "mismatched_fields": mismatched,
            "unknown_fields": unknown,
        }
    if unknown:
        reasons.append("some evidence fields are missing or unavailable")
        return {
            "status": EVIDENCE_STATUS_POSSIBLY_STALE,
            "stale": None,
            "reasons": reasons,
            "mismatched_fields": [],
            "unknown_fields": unknown,
        }
    return {
        "status": EVIDENCE_STATUS_FRESH,
        "stale": False,
        "reasons": [],
        "mismatched_fields": [],
        "unknown_fields": [],
    }


def compare_canvas_with_current_workflow_evidence(
    canvas_document: Any,
    workspace: Any,
) -> Dict[str, Any]:
    """Compare a canvas document's embedded evidence with current workflow IR."""

    canvas_evidence = None
    if isinstance(canvas_document, Mapping):
        canvas_evidence = canvas_document.get("evidence")
    return compare_canvas_evidence(
        canvas_evidence,
        build_current_workflow_evidence(workspace),
    )


def source_facts_sha256(source_facts: Any) -> Optional[str]:
    """Return a deterministic hash for a source_facts bundle when present."""

    if source_facts is None:
        return None
    return sha256_hex(_canonical_source_facts_bytes(source_facts))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current_git_head(workspace: Any) -> Optional[str]:
    """Return HEAD for *workspace*, or None outside a usable git checkout."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(resolve_workspace(workspace)),
            capture_output=True,
            check=False,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _canonical_source_facts_bytes(source_facts: Any) -> bytes:
    return json.dumps(
        _canonicalize_source_facts(source_facts),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize_source_facts(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            if key == "facts" and isinstance(item, list):
                normalized[key] = sorted(
                    [_canonicalize_source_facts(fact) for fact in item],
                    key=_canonical_sort_key,
                )
            else:
                normalized[key] = _canonicalize_source_facts(item)
        return normalized
    if isinstance(value, list):
        return [_canonicalize_source_facts(item) for item in value]
    return value


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _default_workspace(workflow_path: Path) -> Path:
    parent = workflow_path.parent
    if parent.name == STATE_DIR_NAME and workflow_path.name == IR_FILENAME:
        return parent.parent
    return parent
