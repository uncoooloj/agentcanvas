#!/usr/bin/env python3
"""Validate AgentCanvas dogfood matrix manifests and gate completeness."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_dogfood_proof import DogfoodProofError, validate_manifest as validate_proof_manifest


SCHEMA = "agentcanvas.dogfood_matrix.v1"
RUN_STATUSES = {"clean", "failed", "blocked", "launch_note", "post_launch"}
LOOPS = {"interim_narrow", "full_loop"}
TRIAGE_CLASSES = {"none", "a", "b", "c"}


class DogfoodMatrixError(ValueError):
    """Raised when a dogfood matrix manifest is invalid or incomplete."""


def validate_matrix(path: Path, *, gate: bool = False) -> Dict[str, Any]:
    manifest_path = path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DogfoodMatrixError(f"{path} is not valid JSON: {error}")
    if not isinstance(manifest, Mapping):
        raise DogfoodMatrixError("matrix manifest must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise DogfoodMatrixError(f"schema must be {SCHEMA!r}")

    agents = _indexed_objects(manifest.get("agents"), "agents")
    workspaces = _indexed_objects(manifest.get("workspaces"), "workspaces")
    runs = manifest.get("runs")
    if not isinstance(runs, list):
        raise DogfoodMatrixError("runs must be a list")

    public_agents = {agent_id for agent_id, agent in agents.items() if agent.get("public_claim") is True}
    gate_workspaces = {workspace_id for workspace_id, workspace in workspaces.items() if workspace.get("gate") is True}
    if not public_agents:
        raise DogfoodMatrixError("at least one agent must have public_claim=true")
    if not gate_workspaces:
        raise DogfoodMatrixError("at least one workspace must have gate=true")

    clean_attempts: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
    run_count = 0
    proof_count = 0
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            raise DogfoodMatrixError(f"runs[{index}] must be an object")
        agent_id = _non_empty(run, "agent_id")
        workspace_id = _non_empty(run, "workspace_id")
        if agent_id not in agents:
            raise DogfoodMatrixError(f"runs[{index}].agent_id is unknown: {agent_id}")
        if workspace_id not in workspaces:
            raise DogfoodMatrixError(f"runs[{index}].workspace_id is unknown: {workspace_id}")
        attempt = _int_at_least(run, "attempt", 1)
        status = _non_empty(run, "status")
        if status not in RUN_STATUSES:
            raise DogfoodMatrixError(f"runs[{index}].status is unsupported: {status}")
        loop = _non_empty(run, "loop")
        if loop not in LOOPS:
            raise DogfoodMatrixError(f"runs[{index}].loop is unsupported: {loop}")
        _non_empty(run, "runbook_id")
        _int_at_least(run, "permission_prompt_count", 0)
        triage_class = _non_empty(run, "triage_class")
        if triage_class not in TRIAGE_CLASSES:
            raise DogfoodMatrixError(f"runs[{index}].triage_class is unsupported: {triage_class}")
        recording = run.get("recording")
        if recording is not None:
            _validate_recording(recording, index)
        proof_path = run.get("proof_manifest_path")
        if proof_path is not None:
            if not isinstance(proof_path, str) or not proof_path.strip():
                raise DogfoodMatrixError(f"runs[{index}].proof_manifest_path must be a non-empty string")
            proof_result = validate_proof_manifest(PROJECT_ROOT / proof_path)
            proof_count += 1
            if proof_result["agent"] != agent_id:
                raise DogfoodMatrixError(
                    f"runs[{index}] proof agent mismatch: run={agent_id}, proof={proof_result['agent']}"
                )
        if status == "clean" and loop == "full_loop":
            clean_attempts[(agent_id, workspace_id)].add(attempt)
        run_count += 1

    required_pairs = sorted((agent_id, workspace_id) for agent_id in sorted(public_agents) for workspace_id in sorted(gate_workspaces))
    missing = []
    for agent_id, workspace_id in required_pairs:
        attempts = sorted(clean_attempts.get((agent_id, workspace_id), set()))
        if not _has_two_consecutive_attempts(attempts):
            missing.append(
                {
                    "agent_id": agent_id,
                    "workspace_id": workspace_id,
                    "clean_attempts": attempts,
                    "required": "two_consecutive_clean_attempts",
                }
            )

    complete = not missing
    result = {
        "ok": True,
        "path": str(manifest_path),
        "agent_count": len(agents),
        "public_agent_count": len(public_agents),
        "workspace_count": len(workspaces),
        "gate_workspace_count": len(gate_workspaces),
        "run_count": run_count,
        "proof_count": proof_count,
        "required_pair_count": len(required_pairs),
        "complete": complete,
        "missing": missing,
    }
    if gate and not complete:
        raise DogfoodMatrixError(
            "dogfood matrix gate is incomplete: %s missing public-agent/workspace pairs"
            % len(missing)
        )
    return result


def _indexed_objects(value: Any, field: str) -> Dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise DogfoodMatrixError(f"{field} must be a non-empty list")
    items: Dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise DogfoodMatrixError(f"{field}[{index}] must be an object")
        item_id = _non_empty(item, "id")
        if item_id in items:
            raise DogfoodMatrixError(f"{field}[{index}].id is duplicated: {item_id}")
        items[item_id] = item
    return items


def _non_empty(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DogfoodMatrixError(f"{key} must be a non-empty string")
    return value.strip()


def _int_at_least(parent: Mapping[str, Any], key: str, minimum: int) -> int:
    value = parent.get(key)
    if not isinstance(value, int) or value < minimum:
        raise DogfoodMatrixError(f"{key} must be an integer >= {minimum}")
    return value


def _validate_recording(recording: Any, index: int) -> None:
    if not isinstance(recording, Mapping):
        raise DogfoodMatrixError(f"runs[{index}].recording must be an object")
    if not isinstance(recording.get("redacted"), bool):
        raise DogfoodMatrixError(f"runs[{index}].recording.redacted must be a boolean")
    has_path = False
    for key in ("raw_path", "public_path"):
        value = recording.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise DogfoodMatrixError(f"runs[{index}].recording.{key} must be a non-empty string")
        has_path = True
    if not has_path and not recording.get("notes"):
        raise DogfoodMatrixError(f"runs[{index}].recording must include a path or notes")


def _has_two_consecutive_attempts(attempts: Iterable[int]) -> bool:
    ordered = sorted(set(attempts))
    return any(current + 1 == following for current, following in zip(ordered, ordered[1:]))


def verify_matrices(paths: Iterable[Path], *, gate: bool) -> int:
    for path in paths:
        result = validate_matrix(path, gate=gate)
        status = "complete" if result["complete"] else "incomplete"
        print(
            "PASS: {path} status={status} runs={run_count} proofs={proof_count} missing={missing_count}".format(
                path=result["path"],
                status=status,
                run_count=result["run_count"],
                proof_count=result["proof_count"],
                missing_count=len(result["missing"]),
            ),
            flush=True,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate AgentCanvas dogfood matrix manifests.")
    parser.add_argument("matrices", nargs="+", type=Path)
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Fail unless every public claimed agent has two consecutive clean runs on each gate workspace.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return verify_matrices(args.matrices, gate=args.gate)
    except (DogfoodMatrixError, DogfoodProofError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
