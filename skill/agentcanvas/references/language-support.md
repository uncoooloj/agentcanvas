# Language Support Reference

Use this when a user asks to add or review AgentCanvas support for a new
programming language.

## Principle

Do not try to build a perfect parser first.

AgentCanvas needs grounded facts with paths and evidence. A caller LLM or agent
can turn those facts into a cleaner canvas, but the facts need to be honest.
The readable map is agent-authored; parsers and indexers are helpers that make
the evidence stronger.

The pipeline is:

```text
language module -> workflow.ir.json/source_facts.v1 -> projection contract -> canvas_query.v1 -> canvas.ir.json
```

`workflow.ir.json` keeps raw repo evidence. `canvas.ir.json` is the display
canvas the invoking agent updates for the browser.

## Checklist

1. Add `agentcanvas/languages/<language_name>.py`.
2. Expose `extract_source_facts(path, source=None)`.
3. Add `parse_workspace(root, paths=None)` when workspace-level parsing helps.
4. Export the module from `agentcanvas/languages/__init__.py`.
5. Add file extensions to source discovery in `agentcanvas/indexer.py`.
6. Call the module from `build_source_facts(...)`.
7. Emit JSON-safe facts with stable ids, kind/type, language, path, and line
   evidence.
8. Add tests under `tests/test_<language_name>_language.py`.
9. Add at least one fixture under `tests/fixtures/`.
10. Run `python3 -m unittest discover`.

## Minimum Useful Facts

- `file`: path, source/test role, line count
- `import`: dependencies and local resolution when known
- `symbol`: functions, classes, handlers, components, commands
- `route`: HTTP routes, file routes, RPC handlers, CLI entry points
- `branch`: `if`, `else if`/`elif`, `else`, switch/case, guards

Useful next facts:

- `call`
- `job`
- `event`
- `database`
- `external_service`
- `webhook`
- `test`

## Rules

- Keep language modules provider-agnostic and agent-agnostic.
- Prefer error facts over hard failures for unreadable or invalid files.
- Include source evidence on every meaningful fact.
- Keep the frontend language-neutral.
- Validate LLM-generated canvas query JSON before writing it:

```bash
agentcanvas apply-query --workspace <workspace> --query <file> --dry-run
```

The full repository guide lives at `docs/language-support.md` when this skill is
used from the AgentCanvas source tree.
