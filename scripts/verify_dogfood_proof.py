#!/usr/bin/env python3
"""Validate local AgentCanvas dogfood proof manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "agentcanvas.dogfood_proof.v1"
CHECKLIST_STATUSES = {"passed", "failed", "blocked", "not_applicable"}
PENDING_STATUSES = {"verified", "done"}


class DogfoodProofError(ValueError):
    """Raised when a dogfood proof manifest is not replayable."""


def stable_directory_sha256(root: Path) -> str:
    if not root.is_dir():
        raise DogfoodProofError(f"workspace fixture path does not exist or is not a directory: {root}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if ".agentcanvas" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_manifest(path: Path) -> Dict[str, Any]:
    manifest_path = path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DogfoodProofError(f"{path} is not valid JSON: {error}")
    if not isinstance(manifest, Mapping):
        raise DogfoodProofError("proof manifest must be a JSON object")

    _require(manifest, "schema", SCHEMA)
    agent = _object(manifest, "agent")
    _non_empty(agent, "id")
    _non_empty(agent, "name")

    workspace = _object(manifest, "workspace")
    if workspace.get("type") not in {"fixture", "local-project", "external-project"}:
        raise DogfoodProofError("workspace.type must be fixture, local-project, or external-project")
    fixture_path = PROJECT_ROOT / _non_empty(workspace, "fixture_path")
    expected_hash = _non_empty(workspace, "fixture_sha256")
    actual_hash = stable_directory_sha256(fixture_path)
    if actual_hash != expected_hash:
        raise DogfoodProofError(
            f"workspace.fixture_sha256 mismatch for {fixture_path.relative_to(PROJECT_ROOT)}: "
            f"expected {expected_hash}, got {actual_hash}"
        )

    checklist = manifest.get("checklist")
    if not isinstance(checklist, list) or not checklist:
        raise DogfoodProofError("checklist must contain at least one item")
    for index, item in enumerate(checklist):
        if not isinstance(item, Mapping):
            raise DogfoodProofError(f"checklist[{index}] must be an object")
        _non_empty(item, "id")
        _non_empty(item, "title")
        if item.get("status") not in CHECKLIST_STATUSES:
            raise DogfoodProofError(f"checklist[{index}].status is not supported")

    permissions = _object(manifest, "permissions")
    prompt_count = permissions.get("prompt_count")
    if not isinstance(prompt_count, int) or prompt_count < 0:
        raise DogfoodProofError("permissions.prompt_count must be a non-negative integer")

    pending = _object(manifest, "pending_request")
    _non_empty(pending, "id")
    if pending.get("status") not in PENDING_STATUSES:
        raise DogfoodProofError("pending_request.status must be verified or done")
    _existing_file(pending, "markdown_path")
    _existing_file(pending, "json_path")
    conversation_path = _existing_file(pending, "conversation_jsonl_path")
    _validate_jsonl(conversation_path)

    verification = _object(manifest, "verification")
    _non_empty(verification, "command")
    _require(verification, "result", "passed")
    _non_empty(verification, "actor")
    if verification.get("evidence_path"):
        _existing_file(verification, "evidence_path")

    canvas = _object(manifest, "canvas")
    before = _int_at_least(canvas, "revision_before", 0)
    after = _int_at_least(canvas, "revision_after", 0)
    if after < before:
        raise DogfoodProofError("canvas.revision_after must be greater than or equal to revision_before")

    workflow_ir = _object(manifest, "workflow_ir")
    _non_empty(workflow_ir, "indexed_at_before")
    _non_empty(workflow_ir, "indexed_at_after")

    recording = _object(manifest, "recording")
    if not isinstance(recording.get("redacted"), bool):
        raise DogfoodProofError("recording.redacted must be a boolean")
    if not recording.get("path") and not recording.get("not_recorded_reason"):
        raise DogfoodProofError("recording must include path or not_recorded_reason")
    if recording.get("path"):
        _existing_file(recording, "path")

    return {
        "ok": True,
        "path": str(manifest_path),
        "agent": agent["id"],
        "workspace_hash": actual_hash,
        "checklist_items": len(checklist),
        "pending_request": pending["id"],
    }


def _object(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise DogfoodProofError(f"{key} must be an object")
    return value


def _require(parent: Mapping[str, Any], key: str, expected: str) -> None:
    if parent.get(key) != expected:
        raise DogfoodProofError(f"{key} must be {expected!r}")


def _non_empty(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DogfoodProofError(f"{key} must be a non-empty string")
    return value


def _int_at_least(parent: Mapping[str, Any], key: str, minimum: int) -> int:
    value = parent.get(key)
    if not isinstance(value, int) or value < minimum:
        raise DogfoodProofError(f"{key} must be an integer >= {minimum}")
    return value


def _existing_file(parent: Mapping[str, Any], key: str) -> Path:
    path = PROJECT_ROOT / _non_empty(parent, key)
    if not path.is_file():
        raise DogfoodProofError(f"{key} does not point to a file: {path}")
    return path


def _validate_jsonl(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise DogfoodProofError(f"{path} must contain at least one JSONL line")
    for index, line in enumerate(lines, start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise DogfoodProofError(f"{path}:{index} is not valid JSON: {error}")
        if not isinstance(item, Mapping):
            raise DogfoodProofError(f"{path}:{index} must be a JSON object")


def verify_manifests(paths: Iterable[Path]) -> int:
    for path in paths:
        result = validate_manifest(path)
        print(
            "PASS: {path} agent={agent} pending={pending_request} checklist={checklist_items}".format(**result),
            flush=True,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate AgentCanvas dogfood proof manifests.")
    parser.add_argument("manifests", nargs="+", type=Path)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return verify_manifests(args.manifests)
    except DogfoodProofError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
