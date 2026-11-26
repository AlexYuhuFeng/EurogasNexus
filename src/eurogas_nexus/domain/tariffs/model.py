"""One public tariff publication, its identity, its content and how a newer one supersedes it.

A *tariff* is what one publisher charges for one product at one facility over one period: an
ENTSOG reserve price for yearly firm exit capacity at an interconnection point, a terminal's
regasification slot for a cargo class, a storage operator's bundled unit. Each time the
publisher's figure (or its status) changes, the platform records a new **version**; the older
version stays readable, so a valuation made last week can be re-read as it was.

Identity and content
--------------------
``tariff_key`` is the identity every version of one tariff shares: the publisher, the
facility, the direction or service, the product and the first day of the period. It never
includes the value or the status. ``content_hash`` is taken over what the publication says:
value, unit, currency, period, status, firmness, operator, market area and source URL. The
retrieval time, the platform's document id and the publication time are not content: the same
figure read again tomorrow is the same version.

Status
------
``INDICATIVE`` or ``FINAL``. A publisher that issues provisional figures first (consultation,
regulator approval pending) and final ones later changes the status of the same tariff, and
that change is a version of its own, ``status_change``, which names the status before and the
basis of the new one (the publisher stated it, a reviewer accepted it, or, for a row that
carries no marker, NC TAR Art. 29's rule: ``tariff_year.nc_tar_status``). Indicative never
silently becomes final: the change is recorded, published as a market event and shown in the
version history, and a reader always sees which status a figure has.

A tariff that leaves the register (an administrator's entry withdrawn) is recorded as a
``withdrawn`` version, so as-of reads before the withdrawal still find it.

TAR-1：公开费率的版本模型（标识、内容哈希、指示性/最终状态及其变更，不静默地由指示性变为最终）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from eurogas_nexus.domain.tariffs.tariff_year import (
    BASIS_AUCTION_HELD,
    BASIS_BEFORE_AUCTION,
    BASIS_IN_FORCE,
    RULE_BASES,
    nc_tar_status,
    tariff_year_for,
)

INDICATIVE = "INDICATIVE"
FINAL = "FINAL"
STATUSES = (INDICATIVE, FINAL)

#: Why a version has the status it has.
BASIS_OPERATOR_STATED = "operator_stated"
BASIS_FIGURES_DISAGREE = "figures_disagree"
BASIS_REVIEWED = "reviewed"
BASIS_AWAITING_REVIEW = "awaiting_review"
BASIS_RULE = "regulation_rule"
#: TAR-2: a row with no marker takes NC TAR Art. 29's rule, evaluated at the instant asked
#: for (``tariff_year.nc_tar_status``).
BASIS_NC_TAR_AUCTION_HELD = BASIS_AUCTION_HELD
BASIS_NC_TAR_BEFORE_AUCTION = BASIS_BEFORE_AUCTION
BASIS_NC_TAR_IN_FORCE = BASIS_IN_FORCE
#: TAR-1 recorded these for ENTSOG rows without a marker (the period's start decided). No new
#: version takes them; versions already recorded keep them and are read under the NC TAR rule.
BASIS_PERIOD_STARTED = "period_started"
BASIS_PERIOD_NOT_STARTED = "period_not_started"
LEGACY_BASES = frozenset({BASIS_PERIOD_STARTED, BASIS_PERIOD_NOT_STARTED})
STATUS_BASES = frozenset(
    {
        BASIS_OPERATOR_STATED,
        BASIS_FIGURES_DISAGREE,
        BASIS_REVIEWED,
        BASIS_AWAITING_REVIEW,
        BASIS_RULE,
        BASIS_NC_TAR_AUCTION_HELD,
        BASIS_NC_TAR_BEFORE_AUCTION,
        BASIS_NC_TAR_IN_FORCE,
    }
)
#: Bases whose status is a rule evaluated at the instant read, not a statement.
RULE_DERIVED_BASES = frozenset(RULE_BASES | LEGACY_BASES)


def status_as_of(status: str, basis: str, tariff_year_from: date, as_of: date) -> tuple[str, str]:
    """The status a version has as of ``as_of``.

    A stated status (operator, reviewer, ENTSOG's unit check) is what it says. A rule-derived
    one (no marker on the row) is the NC TAR rule evaluated at ``as_of`` for the tariff year's
    first day (all of a tariff year's prices are published together), so a row read in June
    is indicative as of June and final as of the August after the yearly auction without being
    read again; a TAR-1 ``period_started`` version is read the same way.
    """

    if basis in RULE_DERIVED_BASES:
        return nc_tar_status(tariff_year_from, as_of)
    return status, basis

#: Facility kinds a tariff can be charged at.
FACILITY_KINDS = frozenset({"point", "terminal", "storage"})

#: Register capacity product -> the duration it books.
DURATIONS = {
    "ANNUAL": "yearly",
    "QUARTERLY": "quarterly",
    "MONTHLY": "monthly",
    "DAILY": "daily",
    "WITHIN_DAY": "within_day",
}

MAX_KEY = 200


class TariffError(ValueError):
    """A tariff that cannot be recorded as stated (names the rule broken)."""


class ChangeKind(StrEnum):
    """What a version is, relative to the one before it."""

    FIRST = "first"  # no version held before
    REVISED = "revised"  # the figure, period or source changed; the status did not
    STATUS_CHANGE = "status_change"  # INDICATIVE -> FINAL, or FINAL -> INDICATIVE
    WITHDRAWN = "withdrawn"  # the tariff left the register


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class TariffSpec:
    """One tariff as a publisher states it now (what a version records).

    Attributes:
        tariff_key: Identity shared by every version (publisher, facility, product, start).
        publisher_id: The publisher in the registry (``publishers.PUBLISHERS``).
        facility_kind: ``point`` (interconnection or entry/exit point), ``terminal`` (LNG),
            ``storage``.
        facility_id: The point key, terminal id or storage facility id.
        product: The capacity product (``ANNUAL`` ... ``WITHIN_DAY``) or a terminal or storage
            service (``bundled_slot``, ``spot``).
        value: The figure as published, in ``unit`` and ``currency``; ``None`` when the
            publication states the tariff by cargo class only (``by_class``).
        period_from: The first gas day the figure applies to.
        period_to: The last gas day it applies to (inclusive); ``None`` when open-ended.
        status: ``INDICATIVE`` or ``FINAL``.
        status_basis: Why it has that status (``STATUS_BASES``).
        published_at_utc: When the publisher published it (``None``: not stated).
        retrieved_at_utc: When this platform read it.
        source_url: Where the figure was published.
        source_ref: The platform's row or document reference (not content).
    """

    tariff_key: str
    publisher_id: str
    facility_kind: str
    facility_id: str
    facility_name: str
    operator: str
    product: str
    unit: str
    currency: str
    period_from: date
    status: str
    status_basis: str
    retrieved_at_utc: datetime
    source_url: str
    value: float | None = None
    period_to: date | None = None
    direction: str | None = None
    firmness: str | None = None
    country: str | None = None
    market_area: str | None = None
    published_at_utc: datetime | None = None
    source_ref: str = ""
    by_class: dict[str, float] = field(default_factory=dict)
    #: TAR-2: the tariff year the publication belongs to (``tariff_year.TariffYear.label``);
    #: derived from the period, so not content. Empty: worked out from the period.
    tariff_year: str = ""

    def __post_init__(self) -> None:
        if not self.tariff_key or len(self.tariff_key) > MAX_KEY:
            raise TariffError(f"tariff_key must be 1-{MAX_KEY} characters")
        if self.status not in STATUSES:
            raise TariffError(f"status must be INDICATIVE or FINAL, not {self.status!r}")
        if self.status_basis not in STATUS_BASES:
            raise TariffError(f"unknown status basis {self.status_basis!r}")
        if self.facility_kind not in FACILITY_KINDS:
            raise TariffError(f"unknown facility kind {self.facility_kind!r}")
        if self.value is None and not self.by_class:
            raise TariffError("a tariff needs a value or a value per cargo class")
        if self.value is not None and (self.value != self.value or self.value < 0):
            raise TariffError("a tariff value must be a non-negative number")
        if self.period_to is not None and self.period_to < self.period_from:
            raise TariffError("period_to is before period_from")
        if not self.source_url.startswith("https://"):
            raise TariffError("source_url must be an https address")
        object.__setattr__(self, "retrieved_at_utc", _aware(self.retrieved_at_utc))
        object.__setattr__(self, "published_at_utc", _aware(self.published_at_utc))
        if not self.tariff_year:
            label = tariff_year_for(self.period_from, self.period_to).label
            object.__setattr__(self, "tariff_year", label[:40])

    @property
    def duration(self) -> str | None:
        """The duration the product books (``yearly`` ...), when it is a capacity product."""

        return DURATIONS.get(self.product.upper())

    def content(self) -> dict[str, Any]:
        """What the publication says (the hashed fields)."""

        return {
            "value": None if self.value is None else repr(float(self.value)),
            "by_class": {k: repr(float(v)) for k, v in sorted(self.by_class.items())},
            "unit": self.unit,
            "currency": self.currency.upper(),
            "period_from": self.period_from.isoformat(),
            "period_to": None if self.period_to is None else self.period_to.isoformat(),
            "status": self.status,
            "status_basis": self.status_basis,
            "direction": self.direction,
            "firmness": self.firmness,
            "operator": self.operator,
            "market_area": self.market_area,
            "product": self.product,
            "source_url": self.source_url,
        }

    @property
    def content_hash(self) -> str:
        """SHA-256 of :meth:`content` (retrieval and publication times excluded)."""

        return hashlib.sha256(_canonical(self.content()).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class HeldVersion:
    """The current version held for one tariff key."""

    version: int
    content_hash: str
    status: str
    retrieved_at_utc: datetime | None
    withdrawn: bool = False


@dataclass(frozen=True)
class VersionDecision:
    """What recording a spec does: write a version (``kind``) or nothing (``reason``)."""

    writes: bool
    version: int
    kind: ChangeKind | None = None
    previous_status: str | None = None
    reason: str = ""


def decide_version(spec: TariffSpec, held: HeldVersion | None) -> VersionDecision:
    """Compare a spec with the current version of its key.

    * nothing held: version 1, ``first``;
    * same content as the current version: nothing written (``unchanged``);
    * retrieved before the current version was: nothing written (``out_of_order``: an older
      read must not supersede a newer one);
    * the status differs: ``status_change`` (named, never silent), else ``revised``.

    A key whose current version is ``withdrawn`` and appears again starts a new version
    (``revised`` or ``status_change`` against the status it had).
    """

    if held is None:
        return VersionDecision(True, 1, ChangeKind.FIRST)
    if not held.withdrawn and held.content_hash == spec.content_hash:
        return VersionDecision(False, held.version, reason="unchanged")
    held_at = _aware(held.retrieved_at_utc)
    if held_at is not None and spec.retrieved_at_utc < held_at and not held.withdrawn:
        return VersionDecision(False, held.version, reason="out_of_order")
    kind = ChangeKind.STATUS_CHANGE if held.status != spec.status else ChangeKind.REVISED
    return VersionDecision(True, held.version + 1, kind, previous_status=held.status)


def status_change_label(previous: str | None, current: str) -> str | None:
    """``INDICATIVE->FINAL`` (finalised) or ``FINAL->INDICATIVE`` (reopened); else ``None``."""

    if previous is None or previous == current:
        return None
    return f"{previous}->{current}"


__all__ = [
    "BASIS_AWAITING_REVIEW",
    "BASIS_FIGURES_DISAGREE",
    "BASIS_OPERATOR_STATED",
    "BASIS_NC_TAR_AUCTION_HELD",
    "BASIS_NC_TAR_BEFORE_AUCTION",
    "BASIS_NC_TAR_IN_FORCE",
    "BASIS_PERIOD_NOT_STARTED",
    "BASIS_PERIOD_STARTED",
    "LEGACY_BASES",
    "RULE_DERIVED_BASES",
    "BASIS_REVIEWED",
    "BASIS_RULE",
    "DURATIONS",
    "FACILITY_KINDS",
    "FINAL",
    "INDICATIVE",
    "STATUSES",
    "STATUS_BASES",
    "ChangeKind",
    "HeldVersion",
    "TariffError",
    "TariffSpec",
    "VersionDecision",
    "decide_version",
    "status_as_of",
    "status_change_label",
]
