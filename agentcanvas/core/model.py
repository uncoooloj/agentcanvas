"""Core AgentCanvas repo-understanding model.

This module is intentionally stdlib-only. Indexers can emit plain dictionaries,
while Python integrations can use the dataclasses below for safer construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from pathlib import PurePosixPath
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CORE_SCHEMA = "agentcanvas.core.v1"
CANVAS_SCHEMA = "agentcanvas.canvas.v1"

FACT_COLLECTIONS: Tuple[str, ...] = (
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
FACT_KIND_BY_COLLECTION = {
    "files": "file",
    "symbols": "symbol",
    "routes": "route",
    "calls": "call",
    "events": "event",
    "jobs": "job",
    "databases": "database",
    "external_services": "external_service",
    "decisions": "decision",
}
CANVAS_STEP_KINDS = ("When", "Do", "If", "ElseIf", "Else")
_STEP_KIND_ALIASES = {
    "when": "When",
    "do": "Do",
    "if": "If",
    "else_if": "ElseIf",
    "elseif": "ElseIf",
    "elif": "ElseIf",
    "else": "Else",
}
_HTTP_METHOD_ALIASES = {"DEL": "DELETE"}
_ID_RE = re.compile(r"[^a-zA-Z0-9_.:/-]+")


class ModelValidationError(ValueError):
    """Raised when a typed model object is internally invalid."""


def normalize_path(path: str) -> str:
    """Return a stable POSIX-style repo path without a leading ``./``."""

    cleaned = str(path).replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned:
        return "."
    return PurePosixPath(cleaned).as_posix()


def normalize_http_method(method: str) -> str:
    normalized = str(method).strip().upper()
    return _HTTP_METHOD_ALIASES.get(normalized, normalized)


def normalize_id_segment(value: Any, fallback: str = "item") -> str:
    cleaned = _ID_RE.sub("-", str(value).strip()).strip("-").lower()
    return cleaned or fallback


def make_fact_id(kind: str, *parts: Any) -> str:
    tail = ":".join(normalize_id_segment(part) for part in parts if part is not None)
    return f"{normalize_id_segment(kind)}:{tail or 'unknown'}"


def canonical_step_kind(kind: str) -> str:
    try:
        return _STEP_KIND_ALIASES[str(kind).strip().replace("-", "_").lower()]
    except KeyError as exc:
        raise ModelValidationError(f"unknown canvas step kind: {kind!r}") from exc


def _as_tuple(values: Optional[Iterable[Any]]) -> Tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, tuple):
        return values
    if isinstance(values, list):
        return tuple(values)
    return (values,)


def _clean_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, tuple):
            value = list(value)
        if value == [] or value == {}:
            continue
        cleaned[key] = value
    return cleaned


def _model_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_model_value(item) for item in value]
    if isinstance(value, list):
        return [_model_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_value(item) for key, item in value.items()}
    return value


def _dataclass_payload(instance: Any, extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    payload = {item.name: _model_value(getattr(instance, item.name)) for item in fields(instance)}
    if extra:
        payload.update(extra)
    return _clean_dict(payload)


@dataclass(frozen=True)
class SourceLocation:
    path: str
    line: Optional[int] = None
    end_line: Optional[int] = None
    column: Optional[int] = None
    end_column: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalize_path(self.path))
        for name in ("line", "end_line", "column", "end_column"):
            value = getattr(self, name)
            if value is not None and int(value) < 1:
                raise ModelValidationError(f"{name} must be positive")

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceLocation":
        return cls(
            path=str(payload.get("path") or "."),
            line=payload.get("line"),
            end_line=payload.get("end_line"),
            column=payload.get("column"),
            end_column=payload.get("end_column"),
        )


@dataclass(frozen=True)
class Confidence:
    score: float
    rationale: str = ""
    signals: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        score = float(self.score)
        if score < 0.0 or score > 1.0:
            raise ModelValidationError("confidence score must be between 0.0 and 1.0")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "signals", tuple(str(item) for item in self.signals))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Confidence":
        return cls(
            score=float(payload.get("score", 1.0)),
            rationale=str(payload.get("rationale") or ""),
            signals=tuple(str(item) for item in payload.get("signals") or ()),
        )


def _default_confidence() -> Confidence:
    return Confidence(1.0)


@dataclass(frozen=True)
class Provenance:
    extractor: str
    location: Optional[SourceLocation] = None
    evidence: str = ""
    confidence: Optional[Confidence] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        location = self.location
        if location is not None and not isinstance(location, SourceLocation):
            location = SourceLocation.from_dict(location)  # type: ignore[arg-type]
        confidence = self.confidence
        if confidence is not None and not isinstance(confidence, Confidence):
            confidence = Confidence.from_dict(confidence)  # type: ignore[arg-type]
        object.__setattr__(self, "location", location)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Provenance":
        location = payload.get("location")
        if location is None and payload.get("path"):
            location = {
                "path": payload.get("path"),
                "line": payload.get("line"),
                "end_line": payload.get("end_line"),
            }
        return cls(
            extractor=str(payload.get("extractor") or payload.get("source") or "unknown"),
            location=SourceLocation.from_dict(location) if isinstance(location, Mapping) else location,
            evidence=str(payload.get("evidence") or ""),
            confidence=Confidence.from_dict(payload["confidence"])
            if isinstance(payload.get("confidence"), Mapping)
            else payload.get("confidence"),
            metadata=dict(payload.get("metadata") or {}),
        )


def _coerce_confidence(value: Any) -> Confidence:
    if value is None:
        return _default_confidence()
    if isinstance(value, Confidence):
        return value
    if isinstance(value, Mapping):
        return Confidence.from_dict(value)
    return Confidence(float(value))


def _coerce_provenance(values: Optional[Iterable[Any]]) -> Tuple[Provenance, ...]:
    items = []
    for value in _as_tuple(values):
        if isinstance(value, Provenance):
            items.append(value)
        elif isinstance(value, Mapping):
            items.append(Provenance.from_dict(value))
        else:
            raise ModelValidationError("provenance entries must be Provenance or mappings")
    return tuple(items)


@dataclass(frozen=True)
class FileFact:
    id: str
    path: str
    language: Optional[str] = None
    role: str = "source"
    size_bytes: Optional[int] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "file"

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalize_path(self.path))
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class SymbolFact:
    id: str
    name: str
    file_id: str
    symbol_type: str = "unknown"
    qualified_name: Optional[str] = None
    language: Optional[str] = None
    location: Optional[SourceLocation] = None
    exported: bool = False
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "symbol"

    def __post_init__(self) -> None:
        location = self.location
        if location is not None and not isinstance(location, SourceLocation):
            location = SourceLocation.from_dict(location)  # type: ignore[arg-type]
        object.__setattr__(self, "location", location)
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class RouteFact:
    id: str
    path: str
    file_id: str
    methods: Tuple[str, ...] = ("ANY",)
    handler_symbol_id: Optional[str] = None
    framework: Optional[str] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "route"

    def __post_init__(self) -> None:
        methods = tuple(dict.fromkeys(normalize_http_method(item) for item in self.methods or ("ANY",)))
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class CallFact:
    id: str
    caller_symbol_id: str
    target_name: str
    file_id: Optional[str] = None
    callee_symbol_id: Optional[str] = None
    call_type: str = "function"
    external_service_id: Optional[str] = None
    condition: Optional[str] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "call"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class EventFact:
    id: str
    name: str
    event_type: str
    file_id: Optional[str] = None
    symbol_id: Optional[str] = None
    channel: Optional[str] = None
    payload_schema: Optional[str] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "event"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", str(self.event_type).strip().lower())
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class JobFact:
    id: str
    name: str
    trigger: str
    file_id: Optional[str] = None
    handler_symbol_id: Optional[str] = None
    schedule: Optional[str] = None
    queue: Optional[str] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "job"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class DatabaseFact:
    id: str
    operation: str
    entity: str
    file_id: Optional[str] = None
    symbol_id: Optional[str] = None
    database: Optional[str] = None
    query_shape: Optional[str] = None
    condition: Optional[str] = None
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "database"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", str(self.operation).strip().lower())
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class ExternalServiceFact:
    id: str
    name: str
    service_type: str
    endpoint: Optional[str] = None
    file_id: Optional[str] = None
    symbol_id: Optional[str] = None
    config_refs: Tuple[str, ...] = field(default_factory=tuple)
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "external_service"

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_refs", tuple(self.config_refs or ()))
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class DecisionFact:
    id: str
    owner_symbol_id: str
    branch: str
    condition: Optional[str] = None
    order: int = 0
    group_id: Optional[str] = None
    file_id: Optional[str] = None
    then_refs: Tuple[str, ...] = field(default_factory=tuple)
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    kind: ClassVar[str] = "decision"

    def __post_init__(self) -> None:
        branch = canonical_step_kind(self.branch)
        if branch not in {"If", "ElseIf", "Else"}:
            raise ModelValidationError("decision branch must be If, ElseIf, or Else")
        object.__setattr__(self, "branch", branch)
        object.__setattr__(self, "then_refs", tuple(self.then_refs or ()))
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"kind": self.kind})


@dataclass(frozen=True)
class RepoFacts:
    files: Tuple[FileFact, ...] = field(default_factory=tuple)
    symbols: Tuple[SymbolFact, ...] = field(default_factory=tuple)
    routes: Tuple[RouteFact, ...] = field(default_factory=tuple)
    calls: Tuple[CallFact, ...] = field(default_factory=tuple)
    events: Tuple[EventFact, ...] = field(default_factory=tuple)
    jobs: Tuple[JobFact, ...] = field(default_factory=tuple)
    databases: Tuple[DatabaseFact, ...] = field(default_factory=tuple)
    external_services: Tuple[ExternalServiceFact, ...] = field(default_factory=tuple)
    decisions: Tuple[DecisionFact, ...] = field(default_factory=tuple)
    version: str = "0.1.0"
    workspace: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    schema: ClassVar[str] = CORE_SCHEMA

    def __post_init__(self) -> None:
        for name in FACT_COLLECTIONS:
            object.__setattr__(self, name, tuple(getattr(self, name) or ()))
        object.__setattr__(self, "workspace", dict(self.workspace or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def iter_facts(self) -> Iterable[Any]:
        for name in FACT_COLLECTIONS:
            yield from getattr(self, name)

    def to_dict(self) -> Dict[str, Any]:
        payload = _dataclass_payload(self, {"schema": self.schema})
        for name in FACT_COLLECTIONS:
            payload.setdefault(name, [])
        return payload


@dataclass(frozen=True)
class CanvasStep:
    id: str
    kind: str
    text: str
    refs: Tuple[str, ...] = field(default_factory=tuple)
    condition: Optional[str] = None
    steps: Tuple["CanvasStep", ...] = field(default_factory=tuple)
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", canonical_step_kind(self.kind))
        object.__setattr__(self, "refs", tuple(str(item) for item in self.refs or ()))
        object.__setattr__(self, "steps", tuple(_coerce_canvas_step(item) for item in self.steps or ()))
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if not str(self.text).strip():
            raise ModelValidationError("canvas step text is required")
        if self.kind == "Else" and self.condition:
            raise ModelValidationError("Else steps cannot have a condition")

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanvasStep":
        return cls(
            id=str(payload.get("id") or make_fact_id("step", payload.get("kind"), payload.get("text"))),
            kind=str(payload.get("kind") or "Do"),
            text=str(payload.get("text") or payload.get("label") or ""),
            refs=tuple(str(item) for item in payload.get("refs") or ()),
            condition=payload.get("condition"),
            steps=tuple(CanvasStep.from_dict(item) for item in payload.get("steps") or ()),
            provenance=tuple(payload.get("provenance") or ()),
            confidence=payload.get("confidence"),
            metadata=dict(payload.get("metadata") or {}),
        )


def _coerce_canvas_step(value: Any) -> CanvasStep:
    if isinstance(value, CanvasStep):
        return value
    if isinstance(value, Mapping):
        return CanvasStep.from_dict(value)
    raise ModelValidationError("canvas steps must be CanvasStep or mappings")


@dataclass(frozen=True)
class Journey:
    id: str
    title: str
    steps: Tuple[CanvasStep, ...]
    entry_refs: Tuple[str, ...] = field(default_factory=tuple)
    provenance: Tuple[Provenance, ...] = field(default_factory=tuple)
    confidence: Confidence = field(default_factory=_default_confidence)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(_coerce_canvas_step(item) for item in self.steps))
        object.__setattr__(self, "entry_refs", tuple(str(item) for item in self.entry_refs or ()))
        object.__setattr__(self, "provenance", _coerce_provenance(self.provenance))
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if not self.steps:
            raise ModelValidationError("journey requires at least one step")

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Journey":
        return cls(
            id=str(payload.get("id") or make_fact_id("journey", payload.get("title"))),
            title=str(payload.get("title") or ""),
            steps=tuple(CanvasStep.from_dict(item) for item in payload.get("steps") or ()),
            entry_refs=tuple(str(item) for item in payload.get("entry_refs") or ()),
            provenance=tuple(payload.get("provenance") or ()),
            confidence=payload.get("confidence"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class CanvasModel:
    journeys: Tuple[Journey, ...]
    version: str = "0.1.0"
    source_schema: str = CORE_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)

    schema: ClassVar[str] = CANVAS_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "journeys", tuple(_coerce_journey(item) for item in self.journeys))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return _dataclass_payload(self, {"schema": self.schema})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanvasModel":
        return cls(
            journeys=tuple(Journey.from_dict(item) for item in payload.get("journeys") or ()),
            version=str(payload.get("version") or "0.1.0"),
            source_schema=str(payload.get("source_schema") or CORE_SCHEMA),
            metadata=dict(payload.get("metadata") or {}),
        )


def _coerce_journey(value: Any) -> Journey:
    if isinstance(value, Journey):
        return value
    if isinstance(value, Mapping):
        return Journey.from_dict(value)
    raise ModelValidationError("journeys must be Journey or mappings")


def normalize_repo_facts(value: Any) -> Dict[str, Any]:
    """Normalize a ``RepoFacts`` object or JSON-like mapping into the core shape."""

    if isinstance(value, RepoFacts):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise TypeError("repo facts must be a RepoFacts instance or mapping")

    payload["schema"] = str(payload.get("schema") or CORE_SCHEMA)
    payload["version"] = str(payload.get("version") or "0.1.0")
    payload["workspace"] = dict(payload.get("workspace") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})

    for collection in FACT_COLLECTIONS:
        facts = []
        expected_kind = FACT_KIND_BY_COLLECTION[collection]
        for raw_fact in payload.get(collection) or ():
            if hasattr(raw_fact, "to_dict"):
                fact = raw_fact.to_dict()
            elif isinstance(raw_fact, Mapping):
                fact = dict(raw_fact)
            else:
                raise TypeError(f"{collection} entries must be mappings")

            fact["kind"] = str(fact.get("kind") or expected_kind)
            if fact["kind"] != expected_kind:
                fact.setdefault("declared_collection", collection)
            if "path" in fact:
                fact["path"] = normalize_path(str(fact["path"]))
            if "methods" in fact:
                fact["methods"] = list(
                    dict.fromkeys(normalize_http_method(item) for item in fact.get("methods") or ("ANY",))
                )
            if collection == "decisions" and fact.get("branch"):
                fact["branch"] = canonical_step_kind(str(fact["branch"]))
            if "provenance" in fact:
                fact["provenance"] = [_normalize_provenance_dict(item) for item in fact.get("provenance") or ()]
            if "confidence" in fact:
                fact["confidence"] = _normalize_confidence_dict(fact["confidence"])
            if not fact.get("id"):
                fact["id"] = _infer_fact_id(expected_kind, fact)
            facts.append(_clean_dict(fact))
        payload[collection] = facts
    return payload


def normalize_canvas_model(value: Any) -> Dict[str, Any]:
    if isinstance(value, CanvasModel):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise TypeError("canvas model must be a CanvasModel instance or mapping")

    payload["schema"] = str(payload.get("schema") or CANVAS_SCHEMA)
    payload["version"] = str(payload.get("version") or "0.1.0")
    payload["source_schema"] = str(payload.get("source_schema") or CORE_SCHEMA)
    payload["metadata"] = dict(payload.get("metadata") or {})
    payload["journeys"] = [_normalize_journey_dict(item) for item in payload.get("journeys") or ()]
    return payload


def validate_repo_facts(value: Any) -> List[str]:
    """Return validation errors for a repo-facts document."""

    errors: List[str] = []
    try:
        payload = normalize_repo_facts(value)
    except (TypeError, ValueError, ModelValidationError) as exc:
        return [str(exc)]

    if payload.get("schema") != CORE_SCHEMA:
        errors.append(f"schema must be {CORE_SCHEMA}")

    ids: Dict[str, str] = {}
    for collection in FACT_COLLECTIONS:
        for index, fact in enumerate(payload.get(collection) or ()):
            label = f"{collection}[{index}]"
            fact_id = fact.get("id")
            if not fact_id:
                errors.append(f"{label} is missing id")
                continue
            if fact_id in ids:
                errors.append(f"{label} duplicates id {fact_id!r} from {ids[fact_id]}")
            ids[fact_id] = label
            errors.extend(_validate_confidence(fact.get("confidence"), f"{label}.confidence"))
            errors.extend(_validate_provenance(fact.get("provenance") or (), f"{label}.provenance"))
            if collection == "files" and fact.get("path") and str(fact["path"]).startswith("/"):
                errors.append(f"{label}.path should be repo-relative")

    known_ids = set(ids)
    for index, symbol in enumerate(payload["symbols"]):
        _check_ref(errors, known_ids, symbol.get("file_id"), f"symbols[{index}].file_id")
    for index, route in enumerate(payload["routes"]):
        _check_ref(errors, known_ids, route.get("file_id"), f"routes[{index}].file_id")
        _check_ref(errors, known_ids, route.get("handler_symbol_id"), f"routes[{index}].handler_symbol_id", optional=True)
        if not route.get("methods"):
            errors.append(f"routes[{index}].methods must not be empty")
    for index, call in enumerate(payload["calls"]):
        _check_ref(errors, known_ids, call.get("caller_symbol_id"), f"calls[{index}].caller_symbol_id")
        _check_ref(errors, known_ids, call.get("callee_symbol_id"), f"calls[{index}].callee_symbol_id", optional=True)
        _check_ref(errors, known_ids, call.get("file_id"), f"calls[{index}].file_id", optional=True)
        _check_ref(errors, known_ids, call.get("external_service_id"), f"calls[{index}].external_service_id", optional=True)
    for index, event in enumerate(payload["events"]):
        _check_ref(errors, known_ids, event.get("file_id"), f"events[{index}].file_id", optional=True)
        _check_ref(errors, known_ids, event.get("symbol_id"), f"events[{index}].symbol_id", optional=True)
    for index, job in enumerate(payload["jobs"]):
        _check_ref(errors, known_ids, job.get("file_id"), f"jobs[{index}].file_id", optional=True)
        _check_ref(errors, known_ids, job.get("handler_symbol_id"), f"jobs[{index}].handler_symbol_id", optional=True)
    for index, database in enumerate(payload["databases"]):
        _check_ref(errors, known_ids, database.get("file_id"), f"databases[{index}].file_id", optional=True)
        _check_ref(errors, known_ids, database.get("symbol_id"), f"databases[{index}].symbol_id", optional=True)
    for index, service in enumerate(payload["external_services"]):
        _check_ref(errors, known_ids, service.get("file_id"), f"external_services[{index}].file_id", optional=True)
        _check_ref(errors, known_ids, service.get("symbol_id"), f"external_services[{index}].symbol_id", optional=True)
    for index, decision in enumerate(payload["decisions"]):
        _check_ref(errors, known_ids, decision.get("owner_symbol_id"), f"decisions[{index}].owner_symbol_id")
        _check_ref(errors, known_ids, decision.get("file_id"), f"decisions[{index}].file_id", optional=True)
        for ref in decision.get("then_refs") or ():
            _check_ref(errors, known_ids, ref, f"decisions[{index}].then_refs")
        if decision.get("branch") not in {"If", "ElseIf", "Else"}:
            errors.append(f"decisions[{index}].branch must be If, ElseIf, or Else")
    return errors


def validate_canvas_model(value: Any, known_fact_ids: Optional[Iterable[str]] = None) -> List[str]:
    """Return validation errors for a canonical canvas document."""

    errors: List[str] = []
    try:
        payload = normalize_canvas_model(value)
    except (TypeError, ValueError, ModelValidationError) as exc:
        return [str(exc)]

    if payload.get("schema") != CANVAS_SCHEMA:
        errors.append(f"schema must be {CANVAS_SCHEMA}")
    known = set(known_fact_ids or ())
    journey_ids: set[str] = set()
    for journey_index, journey in enumerate(payload.get("journeys") or ()):
        label = f"journeys[{journey_index}]"
        journey_id = journey.get("id")
        if not journey_id:
            errors.append(f"{label} is missing id")
        elif journey_id in journey_ids:
            errors.append(f"{label} duplicates journey id {journey_id!r}")
        journey_ids.add(journey_id)
        if not journey.get("steps"):
            errors.append(f"{label}.steps must not be empty")
        elif journey["steps"][0].get("kind") != "When":
            errors.append(f"{label}.steps should begin with a When step")
        errors.extend(_validate_steps(journey.get("steps") or (), f"{label}.steps", known))
    return errors


def all_fact_ids(value: Any) -> Tuple[str, ...]:
    payload = normalize_repo_facts(value)
    ids = []
    for collection in FACT_COLLECTIONS:
        ids.extend(str(fact["id"]) for fact in payload.get(collection) or () if fact.get("id"))
    return tuple(ids)


def _infer_fact_id(kind: str, fact: Mapping[str, Any]) -> str:
    if kind == "file":
        return make_fact_id(kind, fact.get("path"))
    if kind == "route":
        return make_fact_id(kind, ",".join(fact.get("methods") or ("ANY",)), fact.get("path"))
    return make_fact_id(kind, fact.get("name") or fact.get("target_name") or fact.get("entity") or fact.get("path"))


def _normalize_confidence_dict(value: Any) -> Dict[str, Any]:
    confidence = _coerce_confidence(value)
    return confidence.to_dict()


def _normalize_provenance_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Provenance):
        return value.to_dict()
    if isinstance(value, Mapping):
        return Provenance.from_dict(value).to_dict()
    raise TypeError("provenance entries must be mappings")


def _normalize_journey_dict(value: Any) -> Dict[str, Any]:
    journey = value if isinstance(value, Journey) else Journey.from_dict(value)
    return journey.to_dict()


def _validate_confidence(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    try:
        score = float(value.get("score") if isinstance(value, Mapping) else value)
    except (TypeError, ValueError):
        return [f"{label}.score must be numeric"]
    if score < 0.0 or score > 1.0:
        return [f"{label}.score must be between 0.0 and 1.0"]
    return []


def _validate_provenance(values: Sequence[Mapping[str, Any]], label: str) -> List[str]:
    errors: List[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            errors.append(f"{label}[{index}] must be an object")
            continue
        errors.extend(_validate_confidence(item.get("confidence"), f"{label}[{index}].confidence"))
        location = item.get("location")
        if location and isinstance(location, Mapping):
            for key in ("line", "end_line", "column", "end_column"):
                if location.get(key) is not None:
                    try:
                        is_positive = int(location[key]) >= 1
                    except (TypeError, ValueError):
                        errors.append(f"{label}[{index}].location.{key} must be numeric")
                        continue
                    if not is_positive:
                        errors.append(f"{label}[{index}].location.{key} must be positive")
    return errors


def _check_ref(
    errors: List[str],
    known_ids: set[str],
    value: Optional[str],
    label: str,
    optional: bool = False,
) -> None:
    if not value:
        if not optional:
            errors.append(f"{label} is required")
        return
    if value not in known_ids:
        errors.append(f"{label} references unknown fact id {value!r}")


def _validate_steps(
    steps: Sequence[Mapping[str, Any]],
    label: str,
    known_fact_ids: set[str],
) -> List[str]:
    errors: List[str] = []
    previous_branch: Optional[str] = None
    seen_else = False
    for index, step in enumerate(steps):
        step_label = f"{label}[{index}]"
        kind = step.get("kind")
        if kind not in CANVAS_STEP_KINDS:
            errors.append(f"{step_label}.kind must be one of {', '.join(CANVAS_STEP_KINDS)}")
            previous_branch = None
            continue
        if kind == "ElseIf":
            if previous_branch not in {"If", "ElseIf"} or seen_else:
                errors.append(f"{step_label} ElseIf must follow If or ElseIf")
        elif kind == "Else":
            if previous_branch not in {"If", "ElseIf"} or seen_else:
                errors.append(f"{step_label} Else must follow If or ElseIf")
            seen_else = True
        elif kind == "If":
            seen_else = False
        else:
            previous_branch = None
            seen_else = False

        if kind in {"If", "ElseIf"} and not (step.get("condition") or step.get("text")):
            errors.append(f"{step_label}.condition or text is required")
        if kind == "Else" and step.get("condition"):
            errors.append(f"{step_label}.condition is not allowed for Else")
        for ref in step.get("refs") or ():
            if known_fact_ids and ref not in known_fact_ids:
                errors.append(f"{step_label}.refs references unknown fact id {ref!r}")
        errors.extend(_validate_confidence(step.get("confidence"), f"{step_label}.confidence"))
        errors.extend(_validate_provenance(step.get("provenance") or (), f"{step_label}.provenance"))
        errors.extend(_validate_steps(step.get("steps") or (), f"{step_label}.steps", known_fact_ids))
        if kind in {"If", "ElseIf", "Else"}:
            previous_branch = kind
    return errors
