"""Mapping helpers from language-neutral repo facts to AgentCanvas journeys."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .model import (
    CORE_SCHEMA,
    CanvasModel,
    CanvasStep,
    Journey,
    all_fact_ids,
    make_fact_id,
    normalize_repo_facts,
    validate_canvas_model,
    validate_repo_facts,
)


def repo_facts_to_canvas_model(repo_facts: Any, title: Optional[str] = None) -> CanvasModel:
    """Map normalized repo facts into canonical AgentCanvas journey language.

    The mapper is intentionally conservative: it only creates journeys for facts
    with clear runtime entry points (routes, jobs, and event listeners). Branches
    are emitted when indexers provide explicit ``decision`` facts.
    """

    fact_errors = validate_repo_facts(repo_facts)
    if fact_errors:
        raise ValueError("invalid repo facts: " + "; ".join(fact_errors))

    payload = normalize_repo_facts(repo_facts)
    index = _FactIndex(payload)
    journeys: List[Journey] = []

    for route in payload["routes"]:
        journeys.append(_route_journey(route, index))
    for job in payload["jobs"]:
        journeys.append(_job_journey(job, index))
    for event in payload["events"]:
        if str(event.get("event_type") or "").lower() in {"listen", "listener", "consume", "subscribe"}:
            journeys.append(_event_listener_journey(event, index))

    canvas = CanvasModel(
        journeys=tuple(journeys),
        source_schema=CORE_SCHEMA,
        metadata={
            "title": title or payload.get("workspace", {}).get("name") or "Repo behavior",
            "fact_counts": {name: len(payload.get(name) or ()) for name in index.collections},
        },
    )
    canvas_errors = validate_canvas_model(canvas, known_fact_ids=all_fact_ids(payload))
    if canvas_errors:
        raise ValueError("invalid canvas model: " + "; ".join(canvas_errors))
    return canvas


class _FactIndex:
    collections = (
        "files",
        "symbols",
        "routes",
        "calls",
        "events",
        "jobs",
        "databases",
        "external_services",
        "decisions",
    )

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.by_id: Dict[str, Dict[str, Any]] = {}
        self.calls_by_caller: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.db_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.events_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.services_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.decisions_by_owner: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for collection in self.collections:
            for fact in payload.get(collection) or ():
                self.by_id[fact["id"]] = fact

        for call in payload.get("calls") or ():
            self.calls_by_caller[call["caller_symbol_id"]].append(call)
        for database in payload.get("databases") or ():
            if database.get("symbol_id"):
                self.db_by_symbol[database["symbol_id"]].append(database)
        for event in payload.get("events") or ():
            if event.get("symbol_id"):
                self.events_by_symbol[event["symbol_id"]].append(event)
        for service in payload.get("external_services") or ():
            if service.get("symbol_id"):
                self.services_by_symbol[service["symbol_id"]].append(service)
        for decision in payload.get("decisions") or ():
            self.decisions_by_owner[decision["owner_symbol_id"]].append(decision)

        for values in (
            self.calls_by_caller,
            self.db_by_symbol,
            self.events_by_symbol,
            self.services_by_symbol,
            self.decisions_by_owner,
        ):
            for key in values:
                values[key] = sorted(values[key], key=lambda item: (item.get("order", 0), item.get("id", "")))

    def fact(self, fact_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not fact_id:
            return None
        return self.by_id.get(fact_id)

    def provenance_for(self, *facts: Optional[Mapping[str, Any]]) -> Tuple[Mapping[str, Any], ...]:
        provenance: List[Mapping[str, Any]] = []
        for fact in facts:
            if fact:
                provenance.extend(fact.get("provenance") or ())
        return tuple(provenance)


def _route_journey(route: Mapping[str, Any], index: _FactIndex) -> Journey:
    methods = ", ".join(route.get("methods") or ("ANY",))
    path = route.get("path") or "/"
    handler = index.fact(route.get("handler_symbol_id"))
    steps = [
        CanvasStep(
            id=make_fact_id("step", route["id"], "when"),
            kind="When",
            text=f"{methods} {path} request arrives",
            refs=(route["id"],),
            provenance=index.provenance_for(route),
            confidence=route.get("confidence"),
        )
    ]
    steps.extend(_handler_steps(handler, index, route))
    return Journey(
        id=make_fact_id("journey", "route", methods, path),
        title=f"{methods} {path}",
        entry_refs=(route["id"],),
        steps=tuple(steps),
        provenance=index.provenance_for(route, handler),
        confidence=route.get("confidence"),
    )


def _job_journey(job: Mapping[str, Any], index: _FactIndex) -> Journey:
    handler = index.fact(job.get("handler_symbol_id"))
    trigger = job.get("schedule") or job.get("trigger") or "job trigger"
    steps = [
        CanvasStep(
            id=make_fact_id("step", job["id"], "when"),
            kind="When",
            text=f"{job.get('name') or 'Job'} runs on {trigger}",
            refs=(job["id"],),
            provenance=index.provenance_for(job),
            confidence=job.get("confidence"),
        )
    ]
    steps.extend(_handler_steps(handler, index, job))
    return Journey(
        id=make_fact_id("journey", "job", job.get("name") or job["id"]),
        title=str(job.get("name") or job["id"]),
        entry_refs=(job["id"],),
        steps=tuple(steps),
        provenance=index.provenance_for(job, handler),
        confidence=job.get("confidence"),
    )


def _event_listener_journey(event: Mapping[str, Any], index: _FactIndex) -> Journey:
    handler = index.fact(event.get("symbol_id"))
    name = event.get("name") or event["id"]
    steps = [
        CanvasStep(
            id=make_fact_id("step", event["id"], "when"),
            kind="When",
            text=f"{name} event is received",
            refs=(event["id"],),
            provenance=index.provenance_for(event),
            confidence=event.get("confidence"),
        )
    ]
    steps.extend(_handler_steps(handler, index, event))
    return Journey(
        id=make_fact_id("journey", "event", name),
        title=f"On {name}",
        entry_refs=(event["id"],),
        steps=tuple(steps),
        provenance=index.provenance_for(event, handler),
        confidence=event.get("confidence"),
    )


def _handler_steps(
    handler: Optional[Mapping[str, Any]],
    index: _FactIndex,
    entry_fact: Mapping[str, Any],
) -> List[CanvasStep]:
    if not handler:
        return []

    steps: List[CanvasStep] = [
        CanvasStep(
            id=make_fact_id("step", handler["id"], "do"),
            kind="Do",
            text=f"Run {handler.get('qualified_name') or handler.get('name') or handler['id']}",
            refs=(handler["id"],),
            provenance=index.provenance_for(handler),
            confidence=handler.get("confidence"),
        )
    ]

    decisions = index.decisions_by_owner.get(handler["id"]) or ()
    if decisions:
        steps.extend(_decision_steps(decisions, index))
        return steps

    steps.extend(_action_steps_for_symbol(handler["id"], index, exclude_refs={entry_fact["id"]}))
    return steps


def _decision_steps(decisions: Sequence[Mapping[str, Any]], index: _FactIndex) -> List[CanvasStep]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for decision in decisions:
        grouped[str(decision.get("group_id") or decision["id"])].append(decision)

    steps: List[CanvasStep] = []
    for group_id in sorted(grouped):
        for decision in sorted(grouped[group_id], key=lambda item: (item.get("order", 0), item["id"])):
            branch_kind = str(decision.get("branch") or "If")
            text = _decision_text(decision)
            branch_steps = _action_steps_for_refs(decision.get("then_refs") or (), index)
            steps.append(
                CanvasStep(
                    id=make_fact_id("step", decision["id"], branch_kind),
                    kind=branch_kind,
                    text=text,
                    condition=decision.get("condition") if branch_kind != "Else" else None,
                    refs=(decision["id"],) + tuple(decision.get("then_refs") or ()),
                    steps=tuple(branch_steps),
                    provenance=index.provenance_for(decision),
                    confidence=decision.get("confidence"),
                )
            )
    return steps


def _action_steps_for_symbol(
    symbol_id: str,
    index: _FactIndex,
    exclude_refs: Optional[Iterable[str]] = None,
) -> List[CanvasStep]:
    excluded = set(exclude_refs or ())
    facts: List[Mapping[str, Any]] = []
    facts.extend(index.calls_by_caller.get(symbol_id) or ())
    facts.extend(index.db_by_symbol.get(symbol_id) or ())
    facts.extend(index.services_by_symbol.get(symbol_id) or ())
    facts.extend(
        event
        for event in index.events_by_symbol.get(symbol_id) or ()
        if str(event.get("event_type") or "").lower() not in {"listen", "listener", "consume", "subscribe"}
    )
    return _action_steps_for_refs((fact["id"] for fact in facts if fact["id"] not in excluded), index)


def _action_steps_for_refs(refs: Iterable[str], index: _FactIndex) -> List[CanvasStep]:
    steps: List[CanvasStep] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        fact = index.fact(ref)
        if not fact:
            continue
        steps.append(
            CanvasStep(
                id=make_fact_id("step", ref, "do"),
                kind="Do",
                text=_describe_fact_action(fact, index),
                refs=(ref,),
                provenance=index.provenance_for(fact),
                confidence=fact.get("confidence"),
            )
        )
    return steps


def _decision_text(decision: Mapping[str, Any]) -> str:
    if decision.get("branch") == "Else":
        return "Otherwise"
    return str(decision.get("condition") or "condition matches")


def _describe_fact_action(fact: Mapping[str, Any], index: _FactIndex) -> str:
    kind = fact.get("kind")
    if kind == "call":
        if fact.get("external_service_id"):
            service = index.fact(fact.get("external_service_id"))
            service_name = service.get("name") if service else fact.get("external_service_id")
            return f"Call {service_name}"
        return f"Call {fact.get('target_name') or fact.get('callee_symbol_id') or fact['id']}"
    if kind == "database":
        return f"{str(fact.get('operation') or 'use').title()} {fact.get('entity') or 'data'}"
    if kind == "event":
        verb = "Emit" if str(fact.get("event_type") or "").lower() in {"emit", "publish", "produce"} else "Handle"
        return f"{verb} {fact.get('name') or fact['id']}"
    if kind == "external_service":
        return f"Use {fact.get('name') or fact['id']}"
    if kind == "symbol":
        return f"Run {fact.get('qualified_name') or fact.get('name') or fact['id']}"
    return f"Use {fact.get('name') or fact.get('id') or kind}"
