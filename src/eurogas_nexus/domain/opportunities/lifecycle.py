"""Persistence, hysteresis, material change and expiry of a stored opportunity (B.6).

- **Persistence**: a key is shown only after it was produced in ``persistence`` consecutive
  evaluations (default two); until then its state is ``new``.
- **Hysteresis**: a shown key is withdrawn (``expired``, reason ``no_longer_found``) only
  after ``removal_after_misses`` consecutive evaluations that did not produce it; one miss
  keeps it. An evaluator that failed does not count as a miss: a failure is not an absence.
- **Material change**: a value move of at least ``material_change`` (20 %) or a state change
  updates the same record with a new version (the version a dismissal was made against).
- **Expiry**: at ``expires_at`` the record leaves the list (reason ``validity_ended``).
- A record converted to a decision case stays converted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from eurogas_nexus.domain.opportunities.controls import Thresholds
from eurogas_nexus.domain.opportunities.model import ENDED_STATES, OpportunityState

#: Allowed system-state transitions (anything else is a defect).
TRANSITIONS: dict[OpportunityState, frozenset[OpportunityState]] = {
    OpportunityState.NEW: frozenset(
        {
            OpportunityState.NEW,
            OpportunityState.ACTIONABLE,
            OpportunityState.INDICATIVE,
            OpportunityState.WATCH,
            OpportunityState.BLOCKED,
            OpportunityState.EXPIRED,
        }
    ),
    **{
        state: frozenset(
            {
                OpportunityState.ACTIONABLE,
                OpportunityState.INDICATIVE,
                OpportunityState.WATCH,
                OpportunityState.BLOCKED,
                OpportunityState.EXPIRED,
                OpportunityState.CONVERTED,
            }
        )
        for state in (
            OpportunityState.ACTIONABLE,
            OpportunityState.INDICATIVE,
            OpportunityState.WATCH,
            OpportunityState.BLOCKED,
        )
    },
    # An expired key produced again (a later evaluation with the same legs and period)
    # starts over as new; a converted one never reopens.
    OpportunityState.EXPIRED: frozenset({OpportunityState.EXPIRED, OpportunityState.NEW}),
    OpportunityState.CONVERTED: frozenset({OpportunityState.CONVERTED}),
}


class TransitionError(ValueError):
    """A state change the lifecycle does not allow."""


def check_transition(old: OpportunityState, new: OpportunityState) -> None:
    """Raise unless ``old -> new`` is allowed.

    Raises:
        TransitionError: the transition is not in :data:`TRANSITIONS`.
    """

    if old == new and old is not OpportunityState.EXPIRED:
        return
    if new not in TRANSITIONS[old]:
        raise TransitionError(f"{old.value} -> {new.value} is not allowed")


@dataclass(frozen=True)
class Tracked:
    """The lifecycle fields of a stored record."""

    state: OpportunityState
    assessed_state: OpportunityState
    version: int
    consecutive_seen: int
    consecutive_missed: int
    surfaced: bool
    value: Decimal | None
    ended_reason: str | None = None


def _material(previous: Tracked, assessed: OpportunityState, value: Decimal | None, t: Thresholds):
    if previous.assessed_state is not assessed:
        return True
    old, new = previous.value, value
    if old is None or new is None:
        return (old is None) != (new is None)
    if old == 0:
        return new != 0
    return abs(new - old) / abs(old) >= t.material_change


def seen(
    previous: Tracked | None,
    assessed: OpportunityState,
    value: Decimal | None,
    thresholds: Thresholds,
) -> tuple[Tracked, bool]:
    """The record after an evaluation produced its key. Returns ``(tracked, new_version)``."""

    if previous is not None and previous.state is OpportunityState.CONVERTED:
        return previous, False
    if previous is None or previous.state is OpportunityState.EXPIRED:
        surfaced = thresholds.persistence <= 1
        state = assessed if surfaced else OpportunityState.NEW
        version = 1 if previous is None else previous.version + 1
        return Tracked(state, assessed, version, 1, 0, surfaced, value), True
    count = previous.consecutive_seen + 1
    surfaced = previous.surfaced or count >= thresholds.persistence
    state = assessed if surfaced else OpportunityState.NEW
    check_transition(previous.state, state)
    changed = _material(previous, assessed, value, thresholds) or (
        surfaced and not previous.surfaced
    )
    return (
        Tracked(
            state=state,
            assessed_state=assessed,
            version=previous.version + (1 if changed else 0),
            consecutive_seen=count,
            consecutive_missed=0,
            surfaced=surfaced,
            value=value if changed else previous.value,
        ),
        changed,
    )


def missed(previous: Tracked, thresholds: Thresholds) -> Tracked:
    """The record after a successful evaluation did not produce its key."""

    if previous.state in ENDED_STATES:
        return previous
    count = previous.consecutive_missed + 1
    if count >= thresholds.removal_after_misses or not previous.surfaced:
        # A key never shown goes at its first miss: it never passed the persistence rule.
        return Tracked(
            OpportunityState.EXPIRED,
            previous.assessed_state,
            previous.version,
            0,
            count,
            previous.surfaced,
            previous.value,
            "no_longer_found",
        )
    return Tracked(
        previous.state,
        previous.assessed_state,
        previous.version,
        0,
        count,
        previous.surfaced,
        previous.value,
    )


def expire_if_due(previous: Tracked, expires_at_utc: datetime, now_utc: datetime) -> Tracked:
    """Expire a record whose validity window has ended."""

    if previous.state in ENDED_STATES or expires_at_utc > now_utc:
        return previous
    return Tracked(
        OpportunityState.EXPIRED,
        previous.assessed_state,
        previous.version,
        previous.consecutive_seen,
        previous.consecutive_missed,
        previous.surfaced,
        previous.value,
        "validity_ended",
    )
