#!/usr/bin/env python3
"""Run AgentCanvas checks before GitHub, PyPI, or Cloudflare publishing."""

import argparse
import ast
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_METADATA_PATH = PROJECT_ROOT / "pyproject.toml"
RUNTIME_VERSION_PATH = PROJECT_ROOT / "agentcanvas" / "__init__.py"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PACKAGED_WEB_DIR = PROJECT_ROOT / "agentcanvas" / "web"
WRANGLER_CONFIG = PROJECT_ROOT / "wrangler.jsonc"
WRANGLER_AGENTCANVAS_CONFIG = PROJECT_ROOT / "wrangler.agentcanvas.jsonc"
DOGFOOD_PROOF_MANIFEST = PROJECT_ROOT / "tests" / "fixtures" / "dogfood-proof" / "manifest.valid.json"
DOGFOOD_MATRIX_MANIFEST = PROJECT_ROOT / "tests" / "fixtures" / "dogfood-matrix" / "matrix.partial.json"
MIN_PYTHON = (3, 9)


class VerificationError(RuntimeError):
    """A release verification step could not pass."""


def require_supported_python(version_info=None):
    version = version_info or sys.version_info
    if tuple(version[:2]) < MIN_PYTHON:
        raise VerificationError(
            "AgentCanvas release verification requires Python 3.9 or newer. "
            "Run `python3.9 scripts/verify_release.py` or use the Python version "
            "configured in CI."
        )


def read_package_version(path=PACKAGE_METADATA_PATH):
    """Read the release version from the package's PEP 621 metadata."""
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            raise VerificationError(
                "Release verification needs `tomllib` or `tomli` to read pyproject.toml."
            )

    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except OSError as error:
        raise VerificationError(f"Could not read package metadata at {path}: {error}")
    except Exception as error:
        raise VerificationError(f"Could not parse package metadata at {path}: {error}")

    project = document.get("project")
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version:
        raise VerificationError(f"Package metadata at {path} has no project.version.")
    return version


def read_runtime_version(path=RUNTIME_VERSION_PATH):
    """Read the version reported by the runtime package source."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except OSError as error:
        raise VerificationError(f"Could not read runtime version at {path}: {error}")
    except SyntaxError as error:
        raise VerificationError(f"Could not parse runtime version at {path}: {error}")

    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in targets):
            continue
        value = statement.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
            return value.value
        raise VerificationError(f"Runtime version at {path} is not a non-empty string.")

    raise VerificationError(f"Runtime version at {path} does not define __version__.")


def verify_release_version(package_metadata_path=PACKAGE_METADATA_PATH, runtime_version_path=RUNTIME_VERSION_PATH):
    """Ensure package metadata and the runtime report the same release."""
    package_version = read_package_version(package_metadata_path)
    runtime_version = read_runtime_version(runtime_version_path)
    if package_version != runtime_version:
        raise VerificationError(
            "Package metadata and runtime versions diverge: "
            f"metadata={package_version!r}, runtime={runtime_version!r}."
        )
    print(f"Package metadata and runtime version match {package_version}.", flush=True)


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


def load_jsonc(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise VerificationError(f"{path.relative_to(PROJECT_ROOT)} is not valid JSON/JSONC: {error}")


def verify_cloudflare_config():
    print("\n== Cloudflare config contract ==", flush=True)
    primary = load_jsonc(WRANGLER_CONFIG)
    alternate = load_jsonc(WRANGLER_AGENTCANVAS_CONFIG)
    if primary != alternate:
        raise VerificationError(
            "wrangler.jsonc and wrangler.agentcanvas.jsonc drifted. "
            "Keep them identical or remove the duplicate config."
        )

    main = primary.get("main")
    assets = primary.get("assets") or {}
    build = primary.get("build") or {}
    routes = primary.get("routes") or []
    package = load_jsonc(FRONTEND_DIR / "package.json")
    scripts = package.get("scripts") or {}
    build_agentcanvas = scripts.get("build:agentcanvas", "")

    if main != "deploy/cloudflare/agentcanvas-worker.js":
        raise VerificationError("wrangler main must stay deploy/cloudflare/agentcanvas-worker.js.")
    if not (PROJECT_ROOT / main).is_file():
        raise VerificationError(f"wrangler main file does not exist: {main}")
    if assets.get("binding") != "ASSETS":
        raise VerificationError("wrangler assets.binding must stay ASSETS.")
    if assets.get("directory") != "./dist/cloudflare-agentcanvas":
        raise VerificationError("wrangler assets.directory must stay ./dist/cloudflare-agentcanvas.")
    if build.get("cwd") != "frontend":
        raise VerificationError("wrangler build.cwd must stay frontend.")
    if build.get("command") != "npm ci && npm run build:agentcanvas":
        raise VerificationError("wrangler build.command must stay npm ci && npm run build:agentcanvas.")
    if "AGENTCANVAS_VITE_BASE=/agentcanvas/" not in build_agentcanvas:
        raise VerificationError("frontend build:agentcanvas must set AGENTCANVAS_VITE_BASE=/agentcanvas/.")
    if "AGENTCANVAS_VITE_OUT_DIR=../dist/cloudflare-agentcanvas" not in build_agentcanvas:
        raise VerificationError("frontend build:agentcanvas must write ../dist/cloudflare-agentcanvas.")
    if not any(route.get("pattern") == "uncooloj.com/agentcanvas*" for route in routes if isinstance(route, dict)):
        raise VerificationError("wrangler routes must include uncooloj.com/agentcanvas*.")

    print("Cloudflare config matches the frontend /agentcanvas/ build contract.", flush=True)


def normalized_asset_bytes(path):
    data = path.read_bytes()
    if path.suffix.lower() not in {".css", ".html", ".js", ".json", ".svg", ".txt", ".webmanifest"}:
        return data
    text = data.decode("utf-8")
    lines = [line.rstrip(" \t") for line in text.splitlines()]
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def relative_files(root):
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def verify_packaged_web_assets(build_output):
    print("\n== Packaged web asset freshness ==", flush=True)
    if not PACKAGED_WEB_DIR.is_dir():
        raise VerificationError("agentcanvas/web is missing; package assets cannot be verified.")

    expected = relative_files(build_output)
    actual = relative_files(PACKAGED_WEB_DIR)
    if expected != actual:
        missing = [str(path) for path in expected if path not in actual]
        stale = [str(path) for path in actual if path not in expected]
        detail = []
        if missing:
            detail.append(f"missing committed assets: {', '.join(missing[:5])}")
        if stale:
            detail.append(f"stale committed assets: {', '.join(stale[:5])}")
        raise VerificationError(
            "Committed agentcanvas/web assets do not match a fresh frontend build"
            + (f" ({'; '.join(detail)})." if detail else ".")
        )

    for relative in expected:
        built = build_output / relative
        committed = PACKAGED_WEB_DIR / relative
        if normalized_asset_bytes(built) != normalized_asset_bytes(committed):
            raise VerificationError(
                "Committed agentcanvas/web assets are stale. "
                f"First mismatch: {relative}. Run `npm run build --prefix frontend` and commit the generated assets."
            )

    print("Committed agentcanvas/web assets match a fresh frontend build.", flush=True)


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
        verify_packaged_web_assets(temp_root_path / "web")
        run_step(
            "Frontend build for Cloudflare /agentcanvas/ path",
            [npm, "run", "build"],
            FRONTEND_DIR,
            env=frontend_env(temp_root_path / "cloudflare-agentcanvas", "/agentcanvas/"),
            timeout=300,
        )
        run_step(
            "Frontend unit tests",
            [npm, "test"],
            FRONTEND_DIR,
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


def run_pending_loop_smoke(env):
    run_step(
        "AgentCanvas pending-loop smoke test",
        [sys.executable, "scripts/smoke_pending_loop.py"],
        PROJECT_ROOT,
        env=env,
        timeout=120,
        returncode_messages={
            2: (
                "AgentCanvas pending-loop smoke test was blocked by local sandbox "
                "permissions for localhost binding or requests. Rerun with "
                "permission to bind/connect to 127.0.0.1, or use "
                "`--skip-runtime-smoke` only when this environment cannot bind "
                "localhost."
            )
        },
    )


def run_python_checks(
    skip_runtime_smoke=False,
    dogfood_matrix_manifest=DOGFOOD_MATRIX_MANIFEST,
    require_dogfood_gate=False,
):
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
        print("\n== AgentCanvas pending-loop smoke test ==", flush=True)
        print("Skipped by --skip-runtime-smoke.", flush=True)
    else:
        run_runtime_smoke(env)
        run_pending_loop_smoke(env)
    run_step(
        "Dogfood proof manifest",
        [sys.executable, "scripts/verify_dogfood_proof.py", str(DOGFOOD_PROOF_MANIFEST)],
        PROJECT_ROOT,
        env=env,
        timeout=60,
    )
    run_step(
        "Dogfood matrix manifest gate" if require_dogfood_gate else "Dogfood matrix manifest shape",
        [
            sys.executable,
            "scripts/verify_dogfood_matrix.py",
            *(["--gate"] if require_dogfood_gate else []),
            str(dogfood_matrix_manifest),
        ],
        PROJECT_ROOT,
        env=env,
        timeout=60,
    )


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
    parser.add_argument(
        "--dogfood-matrix",
        type=Path,
        default=DOGFOOD_MATRIX_MANIFEST,
        help=(
            "Dogfood matrix manifest to validate. Defaults to the intentionally "
            "partial fixture used for shape checks."
        ),
    )
    parser.add_argument(
        "--require-dogfood-gate",
        action="store_true",
        help="Fail unless the dogfood matrix satisfies the full public release gate.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    print("AgentCanvas release verification", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)

    try:
        require_supported_python()
        verify_release_version()
        verify_cloudflare_config()
        run_python_checks(
            skip_runtime_smoke=args.skip_runtime_smoke,
            dogfood_matrix_manifest=args.dogfood_matrix,
            require_dogfood_gate=args.require_dogfood_gate,
        )
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
