# Adding Language Support

AgentCanvas should not require a perfect parser for every language before it is
useful. The primary MVP path is LLM-assisted projection: language modules gather
grounded facts, chunks, and provenance, then the calling agent or LLM translates
those facts into human-readable canvas flows.

Language support is therefore a grounding layer, not the whole product.

## Architecture

```text
repo files
  |
  | language module
  v
source_facts.v1
  |
  | projection contract
  v
LLM-assisted canvas_query.v1
  |
  | validation + materialization
  v
workflow.ir.json
  |
  v
AgentCanvas UI
```

The indexer can also keep deterministic fallback graph nodes and edges, but the
LLM-assisted path is expected to produce the best human-readable journeys.

## What A Language Module Must Do

A language module lives under:

```text
agentcanvas/languages/<language_name>.py
```

It should expose one or more of these public functions:

```python
def extract_source_facts(path: str | Path, source: str | None = None) -> dict: ...
def extract_file(path: str | Path) -> dict: ...
def parse_workspace(root: str | Path, paths: Sequence[str | Path] | None = None) -> dict: ...
```

The module output must be JSON-serializable and should include:

- `schema`: usually `agentcanvas.source_facts.v1`
- `language`: stable language name, for example `python`, `javascript-typescript`
- `parser`: name, version, strategy, and capabilities when workspace-level
  extraction is available
- `facts`: flat list of fact dictionaries
- `summary`: counts by type and kind
- `errors` or `diagnostics`: parse/read problems represented as facts, not hard failures

## Built-In MVP Modules

The shared indexer registers these language modules today:

- `javascript-typescript`: `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`
- `python`: `.py`
- `go`: `.go`
- `php-laravel`: `.php`
- `ruby-rails`: `.rb`
- `dart-flutter`: `.dart`
- `swift`: `.swift`
- `kotlin`: `.kt`, `.kts`

The Go, PHP/Laravel, Ruby/Rails, Dart/Flutter, Swift, and Kotlin modules use
lightweight extraction for MVP coverage. They should still emit stable language
names, file facts, provenance, and best-effort imports, symbols, routes,
branches, and calls.

## Monorepo App Surfaces

Language facts should remain language-neutral, but the workflow IR should keep
monorepo app surfaces distinct. In a workspace with multiple apps, such as
`apps/customer-web` and `apps/admin`, the indexer should:

- expose each app under top-level `workflow_ir.app_surfaces`
- report the count in `workflow_ir.summary.app_surfaces`
- include stable surface identifiers or paths so two apps are not collapsed into
  one generic frontend or backend surface
- preserve enough surface metadata for source facts and projection prompts to
  connect files back to the app surface they belong to

This metadata belongs in the core workflow IR and source-facts grounding layer.
Do not make the frontend infer app surfaces from language-specific file paths.

## Fact Types

Start with the smallest useful set. A module does not need every fact type on
day one.

Required for MVP quality:

- `file`: source file path, readability, test/source role, line count
- `import`: module specifier/imported names and resolved local path when known
- `symbol`: functions, classes, exported handlers, components, views, commands
- `route`: HTTP routes, file routes, RPC handlers, CLI commands, or other entry points
- `branch`: `if`, `else if`/`elif`, `else`, switch/case, guard clauses where detectable

Useful next facts:

- `call`: function/method calls, especially calls from handlers to services
- `job`: cron jobs, background tasks, queue consumers, scheduled commands
- `event`: event producers/consumers, webhooks, message handlers
- `database`: reads/writes, migrations, model mutations, query entry points
- `external_service`: payment, email, storage, analytics, auth, and HTTP clients
- `test`: test files, test cases, fixtures, specs, or snapshots

Represent parse failures as `parse_error` or `read_error` facts with file and
line provenance. The index should continue whenever possible.

## Provenance Requirements

Every meaningful fact should point back to source evidence:

```json
{
  "id": "route:src/routes/orders.js:post:/orders",
  "type": "route",
  "kind": "handler",
  "language": "javascript-typescript",
  "path": "/orders",
  "method": "POST",
  "file": "src/routes/orders.js",
  "source_ref": {
    "path": "src/routes/orders.js",
    "line": 12,
    "column": 3
  }
}
```

Use `source_ref` or `provenance`. The shared indexer normalizes either shape into
`source_facts.v1` evidence.

## Registration Checklist

To add a new language:

1. Create `agentcanvas/languages/<language_name>.py`.
2. Export it from `agentcanvas/languages/__init__.py`.
3. Add its file extensions to the indexer's source discovery.
4. Call it from `build_source_facts(...)` in `agentcanvas/indexer.py`.
5. Normalize its raw facts through the shared source-facts bundle.
6. Add focused tests under `tests/test_<language_name>_language.py`.
7. Add a fixture under `tests/fixtures/` that includes at least one entry point,
   one call, and one branch.
8. Update this document if the language needs a special convention.

Do not make the frontend know about language-specific facts. The frontend should
consume the projected canvas model.

## Test Expectations

Each language module should have tests for:

- readable files produce `file` facts
- imports/dependencies are captured
- symbols/handlers are captured
- entry points are captured
- `if`, `else if`/`elif`, and `else` are captured when the language supports them
- source evidence includes paths and positive line numbers
- unreadable or syntactically invalid files become error facts

The CLI contract should also prove that indexing a workspace with that language
adds the language name to:

```json
{
  "summary": {
    "language_modules": ["<language>"]
  }
}
```

## LLM Projection Contract

Language modules should avoid trying to fully narrate the app. They should emit
grounded facts with enough evidence for an LLM to safely translate:

- "this file defines an entry point"
- "this handler calls this service"
- "this condition branches into these outcomes"
- "this queue/job/event can start behavior without a user request"

The projection layer then asks the caller LLM to produce `canvas_query.v1`. The
response must cite `fact_ids`, then AgentCanvas validates and materializes it:

```bash
agentcanvas apply-query --workspace <workspace> --query canvas-query.json
```

Use `--dry-run` first when integrating a new adapter:

```bash
agentcanvas apply-query --workspace <workspace> --query canvas-query.json --dry-run
```

## When To Use Real Parsers

Regex or lightweight AST extraction is acceptable for early support. Add a
stronger parser when it materially improves one of these:

- route/framework detection
- branch accuracy
- call graph quality
- import resolution
- speed on large repos
- source ranges and provenance

Keep the module API stable so the parser strategy can improve without changing
the rest of AgentCanvas.

## Non-Goals

Do not require a full compiler-grade semantic model before supporting a language.
Do not call a specific LLM provider from a language module. Do not make language
modules depend on Codex, Claude Code, Cursor, Antigravity, or any other agent.
