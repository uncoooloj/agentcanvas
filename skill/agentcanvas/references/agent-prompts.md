# Agent Prompt Snippets

Use these only when a user wants to copy an AgentCanvas request into a specific
coding agent. The base workflow does not depend on any adapter or vendor.

For canvas-only edits, tell the agent to update `.agentcanvas/canvas.ir.json`
directly and not change source code.

For all generated visible map text, default to plain English for non-technical
readers. Use short 2-5 word titles, everyday verbs, and workspace-type-sensitive
language. Keep file paths, package names, tool names, framework names, API
routes, schema terms, and other implementation jargon out of visible journey,
step, branch, lane, and summary text. Put technical provenance only in refs,
details, evidence ids, or supporting data.

For source-code implementation, always keep the status loop in the prompt:
inspect request, inspect workspace context, clarify if needed, implement only
after the request is clear, verify, re-index to refresh evidence, update status.

For projection prompts, keep the same safety loop: inspect `source_facts` and
`app_surfaces`, clarify before applying unclear output, generate grounded
human-readable journeys, validate, then apply to `.agentcanvas/canvas.ir.json`.

## Canvas Edit Prompt

```text
Use AgentCanvas for this workspace:
<workspace>

Read .agentcanvas/workflow.ir.json for evidence and .agentcanvas/canvas.ir.json for the current display canvas.

Apply this canvas-only edit to .agentcanvas/canvas.ir.json:
<canvas-edit>

Keep the visible map plain-English and non-technical. Use short 2-5 word titles, everyday verbs, and language that matches this workspace type. Do not put file paths, tool names, API routes, schema terms, or implementation jargon in visible titles, labels, lanes, branches, or summaries. Preserve evidence ids, source paths, or provenance in refs/details where possible. If the requested map change is ambiguous, ask a short plain-language question before applying it. Do not edit source code, create a pending implementation request, or re-index unless the user explicitly asks for source-code implementation or evidence refresh.
```

## Portable Handoff Prompt

```text
Use AgentCanvas for this workspace. Inspect .agentcanvas/pending, read the selected request's .md, and read the matching .json for structured context. Before editing, inspect the current workspace context and confirm four things are clear: the requested change, the affected flow or step, the acceptance criteria, and the verification path.

If any of those are ambiguous, risky, incomplete, or contradicted by the current workspace, do not enter execution mode yet. Ask the fewest useful clarifying questions in plain language, and update the request with needs_input plus the question.

Once the request is clear, mark it in_progress, make the smallest change that satisfies the acceptance criteria, run the agreed test or smoke check, re-index with agentcanvas index --workspace . to refresh evidence, update the request status, and summarize what changed and how it was verified.
```

## Short Handoff Prompt

```text
Work from .agentcanvas/pending only for explicit source-code implementation. Read the Markdown request and matching JSON, inspect the current workspace context, and clarify before editing unless the requested change, affected flow or step, acceptance criteria, and verification path are all clear. If clarification is needed, set status to needs_input with concise plain-language questions. Once clear, mark in_progress, implement the smallest focused change, verify it, re-index to refresh evidence, and update status.
```

## Needs-Input Status Note

```text
I need one decision before editing: <short plain-language question about the requested behavior, affected flow or step, acceptance criteria, verification path, or safety permission>.
```

## Status Commands

```bash
agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: <question>"
agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified: <test or smoke check>."
```

## Copy Fallback Template

```text
Use AgentCanvas for this workspace:
<workspace>

Implement this pending request:
<pending-md>

Use this structured context if useful:
<pending-json>

Before editing, inspect the request and current workspace context. Only start implementation once these are clear:

- requested change
- affected flow or step
- acceptance criteria
- verification path

If anything is unclear, risky, incomplete, or contradicted by the workspace, ask concise plain-language questions and mark the request needs_input:

agentcanvas status --workspace <workspace> <pending-id> --status needs_input --note "I need one decision before editing: <question>"

Once clear, mark the request in_progress, make the smallest change that satisfies the acceptance criteria, run the relevant test or smoke check, re-index with agentcanvas index --workspace <workspace> to refresh evidence, then mark the request done:

agentcanvas status --workspace <workspace> <pending-id> --status in_progress
agentcanvas index --workspace <workspace>
agentcanvas status --workspace <workspace> <pending-id> --status done --note "Implemented and verified: <test or smoke check>."
```

## Portable Projection Prompt

```text
Use AgentCanvas projection for this workspace:
<workspace>

Read .agentcanvas/workflow.ir.json, especially source_facts, projection_contract, and source_facts.repo.app_surfaces. If .agentcanvas/canvas.ir.json already exists, read it too so updates preserve the current display canvas.

Generate agentcanvas.canvas_query.v1 JSON in llm-assisted mode. Use source_facts and app_surfaces as the only evidence. Create plain-English, non-technical AgentCanvas journeys using When, Do, If, ElseIf, and Else. The visible map is for a non-technical project owner by default: use short 2-5 word titles, everyday verbs, and language that fits the workspace type. Use "project" when the type is unclear; use terms like site, store, game, lesson, workflow, or automation only when the evidence supports them. Use app_surfaces as lanes, participants, or drilldowns inside journeys. Cite fact_ids on every operation and include useful provenance in node or edge data. The query should materialize the display canvas in .agentcanvas/canvas.ir.json, not replace workflow facts.

Do not create top-level journeys from a raw file inventory. Files, tests, services, packages, modules, tool names, API routes, schema terms, and implementation jargon should appear only as supporting details, refs, provenance, or supporting nodes, not as visible journey or step titles.

If the intended journey, actor, outcome, affected surface, or evidence is unclear, ask concise clarifying questions before applying the result. If only part of the app is grounded, return a partial projection with warnings instead of guessing.

Validate first:

agentcanvas apply-query --workspace <workspace> --query <canvas-query.json> --dry-run

Apply only after validation passes and the user wants the display canvas written:

agentcanvas apply-query --workspace <workspace> --query <canvas-query.json>

This writes .agentcanvas/canvas.ir.json. It does not overwrite .agentcanvas/workflow.ir.json.
```
