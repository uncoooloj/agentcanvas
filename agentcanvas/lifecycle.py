"""Shared pending-request lifecycle definitions."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Set


class PendingStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    DONE = "done"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


def _status_values(*statuses: PendingStatus) -> Set[str]:
    return {status.value for status in statuses}


def _status_value(status: Any) -> Any:
    return status.value if isinstance(status, PendingStatus) else status


PENDING = PendingStatus.PENDING.value
SENT = PendingStatus.SENT.value
IN_PROGRESS = PendingStatus.IN_PROGRESS.value
IMPLEMENTED = PendingStatus.IMPLEMENTED.value
NEEDS_INPUT = PendingStatus.NEEDS_INPUT.value
BLOCKED = PendingStatus.BLOCKED.value
VERIFIED = PendingStatus.VERIFIED.value
DONE = PendingStatus.DONE.value
CANCELLED = PendingStatus.CANCELLED.value
REJECTED = PendingStatus.REJECTED.value

PENDING_STATUSES = {status.value for status in PendingStatus}

REF_PROTECTING = _status_values(
    PendingStatus.PENDING,
    PendingStatus.SENT,
    PendingStatus.IN_PROGRESS,
    PendingStatus.IMPLEMENTED,
    PendingStatus.NEEDS_INPUT,
    PendingStatus.BLOCKED,
)
TERMINAL = _status_values(
    PendingStatus.VERIFIED,
    PendingStatus.DONE,
    PendingStatus.CANCELLED,
    PendingStatus.REJECTED,
)
UI_GROUPS = {
    "needs-you": _status_values(PendingStatus.NEEDS_INPUT),
    "in-motion": _status_values(
        PendingStatus.PENDING,
        PendingStatus.SENT,
        PendingStatus.IN_PROGRESS,
        PendingStatus.IMPLEMENTED,
    ),
    "finished": _status_values(PendingStatus.VERIFIED, PendingStatus.DONE),
    "stopped": _status_values(
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
}

_TRANSITIONS = {
    PENDING: _status_values(
        PendingStatus.SENT,
        PendingStatus.IN_PROGRESS,
        PendingStatus.NEEDS_INPUT,
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
    SENT: _status_values(
        PendingStatus.IN_PROGRESS,
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
    IN_PROGRESS: _status_values(
        PendingStatus.NEEDS_INPUT,
        PendingStatus.IMPLEMENTED,
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
    NEEDS_INPUT: _status_values(
        PendingStatus.IN_PROGRESS,
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
    IMPLEMENTED: _status_values(
        PendingStatus.IN_PROGRESS,
        PendingStatus.VERIFIED,
        PendingStatus.BLOCKED,
        PendingStatus.CANCELLED,
        PendingStatus.REJECTED,
    ),
    VERIFIED: _status_values(PendingStatus.DONE),
    DONE: set(),
    CANCELLED: set(),
    REJECTED: set(),
}


class LifecycleError(ValueError):
    """Raised when a pending-request lifecycle operation is invalid."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[str] = None,
        allowed: Optional[Set[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.allowed = set(allowed or set())
        self.details = details or {}


def validate_status(status: str) -> str:
    status = _status_value(status)
    if status not in PENDING_STATUSES:
        allowed = ", ".join(sorted(PENDING_STATUSES))
        raise LifecycleError(
            "status must be one of: %s" % allowed,
            status=status,
            allowed=set(PENDING_STATUSES),
        )
    return status


def allowed_next_statuses(current: str, record: Optional[Mapping[str, Any]] = None) -> Set[str]:
    current = validate_status(current)
    if current == BLOCKED:
        prior = _blocked_return_status(record)
        allowed = {CANCELLED, REJECTED}
        if prior and prior not in TERMINAL:
            allowed.add(prior)
        return allowed
    return set(_TRANSITIONS.get(current, set()))


def is_ref_protecting(status: Any) -> bool:
    status = _status_value(status)
    return (status if isinstance(status, str) else PENDING) in REF_PROTECTING


def transition_record(
    record: Mapping[str, Any],
    status: str,
    *,
    at: str,
    actor: str = "agentcanvas",
    note: Optional[str] = None,
    evidence: Optional[Mapping[str, Any]] = None,
    enforce_transitions: bool = False,
) -> Dict[str, Any]:
    target = validate_status(status)
    updated = deepcopy(dict(record))
    current = _status_value(updated.get("status", PENDING))
    if not isinstance(current, str) or current not in PENDING_STATUSES:
        current = PENDING

    if enforce_transitions and target != current:
        allowed = allowed_next_statuses(current, updated)
        if target not in allowed:
            raise LifecycleError(
                "illegal status transition from %s to %s" % (current, target),
                status=target,
                allowed=allowed,
                details={"from": current, "to": target, "allowed": sorted(allowed)},
            )

    if target == VERIFIED and not isinstance(evidence, Mapping):
        raise LifecycleError(
            "verified status requires evidence",
            status=target,
            allowed=allowed_next_statuses(current, updated),
            details={"required_evidence": ["actor", "at", "check", "result"]},
        )

    if target == BLOCKED and current != BLOCKED and current not in TERMINAL:
        updated["blocked_from"] = current
    elif current == BLOCKED and target != BLOCKED:
        updated.pop("blocked_from", None)

    updated["status"] = target
    updated["updated_at"] = at
    if note:
        updated["note"] = note
    if target == VERIFIED and isinstance(evidence, Mapping):
        updated["verification"] = dict(evidence)

    transition = {
        "at": at,
        "actor": actor,
        "from": current,
        "to": target,
    }
    if note:
        transition["note"] = note
    if target == VERIFIED and isinstance(evidence, Mapping):
        transition["evidence"] = dict(evidence)

    history = list(updated.get("history") or [])
    history.append(transition)
    updated["history"] = history

    status_history = list(updated.get("status_history") or [])
    compat_entry = {
        "status": target,
        "updated_at": at,
        "from": current,
        "to": target,
        "actor": actor,
    }
    if note:
        compat_entry["note"] = note
    status_history.append(compat_entry)
    updated["status_history"] = status_history
    return updated


def _blocked_return_status(record: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(record, Mapping):
        return None
    prior = _status_value(record.get("blocked_from"))
    if isinstance(prior, str) and prior in PENDING_STATUSES:
        return prior
    for item in reversed(list(record.get("history") or [])):
        if not isinstance(item, Mapping):
            continue
        if item.get("to") == BLOCKED:
            candidate = _status_value(item.get("from"))
            if isinstance(candidate, str) and candidate in PENDING_STATUSES:
                return candidate
    return None
