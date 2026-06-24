# Publishing AgentCanvas

This is the short version for someone preparing AgentCanvas for use or publish.

## What Happens When You Run It

- `agentcanvas start` opens the landing page. It has not read a project yet.
- `agentcanvas start --demo` opens the bundled sample project. It uses the real
  AgentCanvas loop, but writes demo files, not files in your repo.
- `agentcanvas index --workspace /path/to/project` reads a real project and
  writes `.agentcanvas/workflow.ir.json`.
- `agentcanvas start --workspace /path/to/project` opens that project in the
  browser and reads AgentCanvas files from `.agentcanvas/`.

Running AgentCanvas should not edit source code. It creates or refreshes local
AgentCanvas files. Source-code edits only happen after a user creates an
implementation request and an agent works from that request.

## What The Agent Should Do Next

For a readable project map:

1. Read `.agentcanvas/workflow.ir.json`.
2. Write or refresh `.agentcanvas/canvas.ir.json` in plain English.
3. Keep source evidence linked where possible.
4. Do not change source code for canvas-only edits.

For an implementation request:

1. Read the pending `.md` and matching `.json` in `.agentcanvas/pending/`.
2. Mark the request `in_progress`.
3. Ask one clear `needs_input` question if the request is unclear.
4. Implement the smallest focused change.
5. Run the closest useful test or smoke check.
6. Re-index the workspace.
7. Mark the request `done` only after the change is verified.

## Before Publishing

Run the release verifier before publishing to GitHub, PyPI, or Cloudflare:

```bash
python3 scripts/verify_release.py
```

The verifier now includes a runtime API smoke check by default. It starts
AgentCanvas on a random localhost port against `examples/sample-js-app` and
checks the live `/api/context` and `/api/canvas` paths. That means the release
check proves more than "the code imports"; it proves the local server can answer
the core browser API.

Only skip runtime smoke when the machine cannot bind or request localhost:

```bash
python3 scripts/verify_release.py --skip-runtime-smoke
```

If you skip it, say plainly that the live runtime API path was not verified in
that environment.
