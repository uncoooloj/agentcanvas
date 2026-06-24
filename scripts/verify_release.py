#!/usr/bin/env python3
"""Run AgentCanvas checks before GitHub, PyPI, or Cloudflare publishing."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class VerificationError(RuntimeError):
    """A release verification step could not pass."""


def command_text(command):
    return " ".join(shlex.quote(str(part)) for part in command)


def with_project_pythonpath():
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT)
        if not pythonpath
        else str(PROJECT_ROOT) + os.pathsep + pythonpath
    )
    return env


def run_step(label, command, cwd, env=None, timeout=300, returncode_messages=None):
    print(f"\n== {label} ==", flush=True)
    print(f"Command: {command_text(command)}", flush=True)
    print(f"Working directory: {cwd}", flush=True)

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise VerificationError(
            f"{label} could not start because `{command[0]}` was not found."
        )
    except subprocess.TimeoutExpired:
        raise VerificationError(
            f"{label} did not finish within {timeout} seconds. "
            "Treat this as unknown, not a pass."
        )

    if completed.returncode != 0:
        if returncode_messages and completed.returncode in returncode_messages:
            raise VerificationError(returncode_messages[completed.returncode])
        raise VerificationError(
            f"{label} failed with exit code {completed.returncode}. "
            "Read the command output above for the failing details."
        )


def find_npm():
    npm = shutil.which("npm")
    if npm:
        return npm
    npm_cmd = shutil.which("npm.cmd")
    if npm_cmd:
        return npm_cmd
    return None


def require_frontend_build_tools(frontend_dir=FRONTEND_DIR):
    package_json = frontend_dir / "package.json"
    if not package_json.is_file():
        return None

    node_modules = frontend_dir / "node_modules"
    if not node_modules.is_dir():
        raise VerificationError(
            "Frontend build was not run because dependencies are missing. "
            "Run `npm install --prefix frontend`, then rerun this verifier."
        )

    npm = find_npm()
    if not npm:
        raise VerificationError(
            "Frontend dependencies exist, but `npm` was not found on PATH. "
            "Install Node.js/npm, then rerun this verifier."
        )

    return npm


def frontend_env(output_dir, base=None):
    env = os.environ.copy()
    env["AGENTCANVAS_VITE_OUT_DIR"] = str(output_dir)
    if base:
        env["AGENTCANVAS_VITE_BASE"] = base
    return env


def run_frontend_builds():
    npm = require_frontend_build_tools()
    if not npm:
        print("\n== Frontend build ==", flush=True)
        print("Skipped: frontend/package.json was not found.", flush=True)
        return

    with tempfile.TemporaryDirectory(prefix="agentcanvas-frontend-build-") as temp_root:
        temp_root_path = Path(temp_root)
        print(f"\nFrontend build output root: {temp_root_path}", flush=True)
        print(
            "Generated assets are written there so tracked web assets are not changed.",
            flush=True,
        )

        run_step(
            "Frontend build for PyPI/local web assets",
            [npm, "run", "build"],
            FRONTEND_DIR,
            env=frontend_env(temp_root_path / "web"),
            timeout=300,
        )
        run_step(
            "Frontend build for Cloudflare /agentcanvas/ path",
            [npm, "run", "build"],
            FRONTEND_DIR,
            env=frontend_env(temp_root_path / "cloudflare-agentcanvas", "/agentcanvas/"),
            timeout=300,
        )


def run_runtime_smoke(env):
    run_step(
        "AgentCanvas runtime API smoke test",
        [sys.executable, "scripts/smoke_runtime.py"],
        PROJECT_ROOT,
        env=env,
        timeout=120,
        returncode_messages={
            2: (
                "AgentCanvas runtime API smoke test was blocked by local sandbox "
                "permissions for localhost binding or requests. Rerun with "
                "permission to bind/connect to 127.0.0.1, or use "
                "`--skip-runtime-smoke` only when this environment cannot bind "
                "localhost."
            )
        },
    )


def run_python_checks(skip_runtime_smoke=False):
    env = with_project_pythonpath()
    run_step(
        "Python unit tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        PROJECT_ROOT,
        env=env,
        timeout=300,
    )
    run_step(
        "AgentCanvas CLI smoke test",
        [sys.executable, "scripts/smoke_mvp.py"],
        PROJECT_ROOT,
        env=env,
        timeout=120,
    )
    if skip_runtime_smoke:
        print("\n== AgentCanvas runtime API smoke test ==", flush=True)
        print("Skipped by --skip-runtime-smoke.", flush=True)
    else:
        run_runtime_smoke(env)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run lightweight AgentCanvas release checks before publishing to "
            "GitHub, PyPI, or Cloudflare."
        )
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Run only Python checks. Use this only when frontend verification is not needed.",
    )
    parser.add_argument(
        "--skip-runtime-smoke",
        action="store_true",
        help=(
            "Skip the localhost runtime API smoke. Use only in environments "
            "that cannot bind or request localhost."
        ),
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    print("AgentCanvas release verification", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)

    try:
        run_python_checks(skip_runtime_smoke=args.skip_runtime_smoke)
        if args.skip_frontend:
            print("\n== Frontend build ==", flush=True)
            print("Skipped by --skip-frontend.", flush=True)
        else:
            run_frontend_builds()
    except VerificationError as error:
        print(f"\nFAILED: {error}", file=sys.stderr)
        return 1

    print("\nAll requested release checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
