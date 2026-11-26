"""LNG-4: demurrage as the cargo's contract states it, converted with an FX fix the user picks.

When a Confirmation Notice is signed, its laytime and demurrage are the contract's: a rate per
day in the currency the contract names (often USD), the laytime, and terms such as "pro rata
per hour" or "half rate for weather delays". The disruption valuation is in EUR, the currency
the book's prices and P&L are in. So a demurrage rate held in another currency is converted,
and the conversion is a stated choice, never a hard-coded rate:

* **Where the terms come from**, first found wins, each named in the read:
  1. the cargo's Confirmation Notice (``LNG_CARGO`` contract terms: ``laytime_hours``,
     ``demurrage_rate_per_day``, ``demurrage_currency``, ``demurrage_terms``);
  2. the cargo's voyage terms (``lng_voyage_terms``: ``demurrage_rate_per_day`` with
     ``demurrage_currency``, from the desk or the ETRM cargo schedule; else the LNG-3
     ``demurrage_eur_per_day``);
  3. the master agreement the notice is made under (``LNG_MSPA``: laytime and
     ``demurrage_usd_per_day``).
* **The FX fix** is ECB's euro reference rate by default. The user may pick WMR or BFIX
  (licensed: only rows the principal is entitled to are offered, as for the price
  conversion), a rate date (the latest fix on or before it is used, and that date is shown),
  or enter a rate by hand (then the read says it was entered by hand). Rates come from the
  ``fx_observations`` the platform already holds; nothing here fetches one.
* **The reporting currency** is the viewer's (``reporting_currency``, EUR by default). A
  figure in EUR is shown beside its value in the reporting currency, at the same fix.
* **One conversion function.** Every currency conversion of the LNG-4 valuation (demurrage,
  another user's demurrage, an upstream contract price, a transport tariff, the reporting
  figures) goes through :func:`_fx_rate`, which answers the rate with its source, its date and
  the sources it tried. A source-precedence resolver (a contracted or clearing-bank rate
  first, then a published reference rate, then the ECB default) can replace its body without
  any caller changing.

Nothing is booked or paid: these figures value options for a person to choose between.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from eurogas_nexus.domain.market.fx_fixings import (
    FxFixingError,
    eur_rates_from_pairs,
    resolve_fixing,
)

REPORTING_CURRENCIES = ("EUR", "GBP", "USD")
#: The sources a user can pick: the benchmark fixes the platform knows, or a rate entered.
FX_SOURCES = ("ECB", "WMR", "BFIX", "manual")
MANUAL = "manual"
FIRM_ORDER_CONTEXT = "lng_demurrage"
DEMO_FX_SOURCE = "DEMO_Sim"


class FxChoiceError(ValueError):
    """An FX choice the read cannot work from (unknown source, a manual rate missing)."""


@dataclass(frozen=True)
class FxChoice:
    """How a foreign-currency figure is converted: the user's choice, ECB by default.

    ``rate`` (with ``source`` ``manual``) is units of ``rate_currency`` per 1 EUR, the way the
    ECB quotes its reference rates (EURUSD 1.0850 is 1.0850 USD per EUR).
    """

    source: str = "ECB"
    fixing: str | None = None
    rate_date: date | None = None
    rate: float | None = None
    rate_currency: str = "USD"
    reporting_currency: str = "EUR"

    def __post_init__(self) -> None:
        source = (self.source or "ECB").strip()
        if source.lower() == MANUAL:
            if self.rate is None or not self.rate > 0:
                raise FxChoiceError("an FX rate entered by hand must be a positive number")
        else:
            try:
                resolve_fixing(source, self.fixing)
            except FxFixingError as exc:
                raise FxChoiceError(str(exc)) from exc
        if self.reporting_currency not in REPORTING_CURRENCIES:
            raise FxChoiceError(
                f"reporting currency {self.reporting_currency!r} is not one of "
                + ", ".join(REPORTING_CURRENCIES)
            )

    @property
    def manual(self) -> bool:
        return (self.source or "").strip().lower() == MANUAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": MANUAL if self.manual else self.source.upper(),
            "fixing": None if self.manual else resolve_fixing(self.source, self.fixing).fixing_id,
            "rate_date": None if self.rate_date is None else self.rate_date.isoformat(),
            "rate": self.rate if self.manual else None,
            "rate_currency": self.rate_currency if self.manual else None,
            "reporting_currency": self.reporting_currency,
            "default": not self.manual
            and self.source.upper() == "ECB"
            and self.fixing in (None, "reference")
            and self.rate_date is None,
        }


@dataclass(frozen=True)
class FxRate:
    """One currency's rate against EUR as used: units of ``currency`` per 1 EUR."""

    currency: str
    units_per_eur: float
    source: str
    label: str
    value_date: str | None
    simulated: bool = False
    entered: bool = False

    def to_eur(self, amount: float) -> float:
        return amount / self.units_per_eur

    def from_eur(self, amount: float) -> float:
        return amount * self.units_per_eur

    def text(self) -> str:
        when = f" of {self.value_date}" if self.value_date else ""
        simulated = " (simulated demo rate)" if self.simulated else ""
        return f"{self.label}{when}: {self.units_per_eur:,.4f} {self.currency} per EUR{simulated}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "units_per_eur": self.units_per_eur,
            "source": self.source,
            "label": self.label,
            "value_date": self.value_date,
            "simulated": self.simulated,
            "entered_by_hand": self.entered,
        }


@dataclass
class FxBook:
    """The rates one read uses, from the rows the reader may see and the user's choice."""

    choice: FxChoice
    on: date
    rows: list[Mapping[str, Any]] = field(default_factory=list)
    allow_demo: bool = False
    session: Any = None
    allowed_systems: frozenset[str] | None = None

    def rate(self, currency: str) -> FxRate | None:
        """``currency`` per EUR under the choice, or ``None`` when no rate is held.

        With the default choice (ECB reference, no date) and a session, the firm's source order
        comes first (TAR-2's ``resolve_fx_rate``, context ``lng_demurrage``): a contracted or
        clearing bank's rate, then a published reference the reader is entitled to, then ECB.
        A source the user chose explicitly is used as chosen.
        """

        currency = (currency or "").upper()
        if currency == "EUR":
            return FxRate("EUR", 1.0, "identity", "EUR", None)
        choice = self.choice
        firm = self._firm_order(currency)
        if firm is not None:
            return firm
        if choice.manual:
            if currency != choice.rate_currency.upper():
                return None
            return FxRate(
                currency,
                float(choice.rate),
                MANUAL,
                "a rate entered by hand",
                None if choice.rate_date is None else choice.rate_date.isoformat(),
                entered=True,
            )
        fixing = resolve_fixing(choice.source, choice.fixing)
        until = (choice.rate_date or self.on).isoformat()
        found = self._latest(
            fixing.source_system, fixing.fixing_id, fixing.licensed, currency, until
        )
        if found is not None:
            return FxRate(currency, found[1], fixing.source_system, fixing.label, found[0])
        if fixing.source_system == "ECB" and self.allow_demo:
            found = self._latest(DEMO_FX_SOURCE, None, False, currency, until)
            if found is not None:
                return FxRate(
                    currency,
                    found[1],
                    DEMO_FX_SOURCE,
                    "demo reference rate",
                    found[0],
                    simulated=True,
                )
        return None

    def _firm_order(self, currency: str) -> FxRate | None:
        """The firm's order for ``currency`` per EUR when a bank or a published reference holds
        it; ``None`` leaves the ECB reference (and the demo rows) to the usual path."""

        if self.session is None or not self.choice.as_dict()["default"]:
            return None
        from datetime import UTC, datetime, time

        from eurogas_nexus.application.source_precedence import resolve_fx_rate
        from eurogas_nexus.domain.pricing.source_precedence import TIER_TEXT

        try:
            resolution = resolve_fx_rate(
                self.session,
                "EUR",
                currency,
                datetime.combine(self.on, time(23, 59, 59), tzinfo=UTC),
                FIRM_ORDER_CONTEXT,
                allowed_systems=self.allowed_systems,
            )
        except Exception:  # noqa: BLE001 - an unreadable order leaves the ECB reference
            return None
        used = resolution.used
        if (
            used is None
            or used.found is None
            or used.tier not in ("contracted_bank", "published_reference")
            or not resolution.value
        ):
            return None
        return FxRate(
            currency,
            float(resolution.value),
            used.found.source,
            TIER_TEXT.get(used.tier, used.tier),
            used.found.as_of[:10] if used.found.as_of else None,
        )

    def missing(self, currency: str) -> str:
        """Why no rate is held for ``currency``, in a sentence."""

        choice = self.choice
        if choice.manual:
            return f"the rate entered by hand is for {choice.rate_currency}, not {currency}"
        fixing = resolve_fixing(choice.source, choice.fixing)
        until = (choice.rate_date or self.on).isoformat()
        return f"no {fixing.label} for {currency} on or before {until} is held"

    def _latest(
        self,
        source: str,
        fixing_id: str | None,
        licensed: bool,
        currency: str,
        until: str,
    ) -> tuple[str, float] | None:
        by_date: dict[str, dict[str, float]] = {}
        for row in self.rows:
            if row.get("source_system") != source:
                continue
            if licensed and row.get("rate_type") != fixing_id:
                continue
            day = str(row.get("value_date") or "")[:10]
            value = row.get("rate")
            if not day or day > until or not isinstance(value, int | float) or not value > 0:
                continue
            pair = str(row.get("pair") or "").upper().replace("/", "")
            if len(pair) != 6:
                pair = f"{row.get('base_currency') or ''}{row.get('quote_currency') or ''}"
                pair = pair.upper()
            by_date.setdefault(day, {}).setdefault(pair, float(value))
        for day in sorted(by_date, reverse=True):
            rates = eur_rates_from_pairs(by_date[day])
            if currency in rates and rates[currency] > 0:
                return day, rates[currency]
        return None


@dataclass(frozen=True)
class FxResolution:
    """A conversion as :func:`_fx_rate` answers it: ``rate`` units of ``to_ccy`` per 1
    ``from_ccy`` (``None`` when no rate is held), where it came from and what was tried."""

    from_ccy: str
    to_ccy: str
    rate: float | None
    source: str | None
    label: str | None
    rate_date: str | None
    tried: tuple[str, ...] = ()
    simulated: bool = False
    entered: bool = False
    missing: str | None = None

    def apply(self, amount: float) -> float | None:
        return None if self.rate is None else amount * self.rate

    def text(self) -> str:
        if self.rate is None:
            return self.missing or f"no {self.from_ccy}/{self.to_ccy} rate held"
        when = f" of {self.rate_date}" if self.rate_date else ""
        flag = " (simulated demo rate)" if self.simulated else ""
        return f"{self.label}{when}: 1 {self.from_ccy} = {self.rate:,.6f} {self.to_ccy}{flag}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_ccy,
            "to": self.to_ccy,
            "rate": self.rate,
            "source": self.source,
            "label": self.label,
            "rate_date": self.rate_date,
            "tried": list(self.tried),
            "simulated": self.simulated,
            "entered_by_hand": self.entered,
            "missing": self.missing,
        }


def _tried(book: FxBook, currency: str) -> list[str]:
    choice = book.choice
    if currency == "EUR":
        return []
    if choice.manual:
        return [f"rate entered by hand ({choice.rate_currency})"]
    fixing = resolve_fixing(choice.source, choice.fixing)
    until = (choice.rate_date or book.on).isoformat()
    tried = [f"{fixing.label} for {currency} on or before {until}"]
    if fixing.source_system == "ECB" and book.allow_demo:
        tried.append(f"demo reference rate for {currency}")
    return tried


def _fx_rate(
    session, from_ccy: str, to_ccy: str, as_of: date, context: FxBook | FxChoice | None
) -> FxResolution:
    """The one conversion the LNG-4 valuation uses: 1 ``from_ccy`` in ``to_ccy`` on ``as_of``.

    The user's selectable source (``context``: an :class:`FxBook`, or an :class:`FxChoice`
    read against the fixes any reader may see), crossed through EUR. By default the firm's
    source order applies (:meth:`FxBook.rate`: a contracted or clearing bank's rate, then a
    published reference, then ECB); an explicit choice is used as chosen. Every caller gets the
    same answer shape (rate, source, rate date, the sources tried).
    """

    src, dst = (from_ccy or "").upper(), (to_ccy or "").upper()
    if src == dst:
        return FxResolution(src, dst, 1.0, "identity", "same currency", None)
    if isinstance(context, FxBook):
        book = context
    else:
        book = fx_book(session, context, on=as_of)
    tried = tuple(_tried(book, src) + _tried(book, dst))
    a, b = book.rate(src), book.rate(dst)
    if a is None or b is None:
        why = book.missing(src if a is None else dst)
        return FxResolution(src, dst, None, None, None, None, tried, missing=why)
    leg = b if src == "EUR" else a
    return FxResolution(
        src,
        dst,
        b.units_per_eur / a.units_per_eur,
        leg.source,
        leg.label,
        leg.value_date,
        tried,
        simulated=a.simulated or b.simulated,
        entered=a.entered or b.entered,
    )


def public_fx_rows(session) -> list[dict[str, Any]]:
    """The fixes any reader may use (ECB and the demo's simulated rows), for a run with no
    reader, such as the outbox consumer: licensed fixes stay with entitled principals."""

    from eurogas_nexus.application.projections.market_reads import fx_observations

    return [
        row
        for row in fx_observations(session)
        if row.get("source_system") in ("ECB", DEMO_FX_SOURCE)
    ]


def fx_book(
    session,
    choice: FxChoice | None,
    *,
    on: date,
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> FxBook:
    """The rates for one read. ``rows`` are the fixes the reader is entitled to (the route
    filters them); without them only ECB and demo rows are read."""

    from eurogas_nexus.core.config import demo_marks_allowed

    held = list(rows) if rows is not None else public_fx_rows(session)
    allowed: frozenset[str] | None = None
    if session is not None:
        from eurogas_nexus.application.source_precedence import (
            ECB_SYSTEMS,
            configured_institutions,
        )

        try:
            banks = {bank.source_system for bank in configured_institutions(session)}
        except Exception:  # noqa: BLE001 - no setting readable: no bank tier
            banks = set()
        seen = {str(row.get("source_system") or "") for row in held}
        allowed = frozenset(seen | set(ECB_SYSTEMS) | banks)
    return FxBook(
        choice or FxChoice(),
        on,
        held,
        allow_demo=demo_marks_allowed(),
        session=session,
        allowed_systems=allowed,
    )


# ------------------------------------------------------------------------- demurrage terms


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def demurrage_terms(held, contract, mspa: Mapping[str, Any] | None) -> dict[str, Any]:
    """Laytime and the demurrage rate in its own currency, and where each was read.

    ``held`` is the cargo's ``lng_voyage_terms`` row (or ``None``), ``contract`` the
    ``(contract_id, LngCargoTerms | None)`` of its Confirmation Notice (or ``None``), and
    ``mspa`` the master agreement's laytime and USD demurrage (or ``None``).
    """

    notice = contract[1] if contract is not None else None
    notice_id = contract[0] if contract is not None else None
    out: dict[str, Any] = {
        "rate_per_day": None,
        "currency": None,
        "source": None,
        "terms": None,
        "laytime_hours": None,
        "laytime_source": None,
    }
    notice_rate = _number(getattr(notice, "demurrage_rate_per_day", None))
    notice_currency = getattr(notice, "demurrage_currency", None)
    if notice_rate is not None and notice_currency:
        out.update(
            rate_per_day=notice_rate,
            currency=str(notice_currency).upper(),
            source=f"confirmation notice {notice_id}",
            terms=getattr(notice, "demurrage_terms", None),
        )
    elif held is not None and _number(getattr(held, "demurrage_rate_per_day", None)) is not None:
        currency = (getattr(held, "demurrage_currency", None) or "EUR").upper()
        out.update(
            rate_per_day=float(held.demurrage_rate_per_day),
            currency=currency,
            source=f"voyage terms ({held.source_reference})",
            terms=getattr(held, "demurrage_terms", None),
        )
    elif held is not None and held.demurrage_eur_per_day is not None:
        out.update(
            rate_per_day=float(held.demurrage_eur_per_day),
            currency="EUR",
            source=f"voyage terms ({held.source_reference})",
            terms=getattr(held, "demurrage_terms", None),
        )
    elif mspa and mspa.get("demurrage_usd_per_day") is not None:
        out.update(
            rate_per_day=float(mspa["demurrage_usd_per_day"]),
            currency="USD",
            source=f"master agreement {mspa['master_contract_id']}",
        )
    notice_laytime = _number(getattr(notice, "laytime_hours", None))
    if notice_laytime is not None:
        out.update(laytime_hours=notice_laytime, laytime_source=f"confirmation notice {notice_id}")
    elif held is not None and held.laytime_hours is not None:
        out.update(laytime_hours=float(held.laytime_hours), laytime_source="voyage terms")
    elif mspa and mspa.get("laytime_hours") is not None:
        out.update(
            laytime_hours=float(mspa["laytime_hours"]),
            laytime_source=f"master agreement {mspa['master_contract_id']}",
        )
    else:
        out.update(laytime_hours=36.0, laytime_source="desk standard 36 h (none recorded)")
    return out


def convert(terms: Mapping[str, Any], fx: FxBook, *, vessel: str) -> dict[str, Any]:
    """The demurrage block a reader sees: the rate as the contract states it, the rate used,
    its source and date, the EUR rate per day the valuation uses, and a warning when no rate
    could be applied (waiting is then costed at boil-off only)."""

    block: dict[str, Any] = {
        "rate_per_day": terms.get("rate_per_day"),
        "currency": terms.get("currency"),
        "source": terms.get("source"),
        "terms": terms.get("terms"),
        "laytime_hours": terms.get("laytime_hours"),
        "laytime_source": terms.get("laytime_source"),
        "eur_per_day": None,
        "fx": None,
        "note": "",
        "warning": None,
    }
    rate, currency = terms.get("rate_per_day"), terms.get("currency")
    if rate is None or not currency:
        block["warning"] = (
            f"{vessel}: no demurrage rate held in the confirmation notice, the voyage terms or "
            "the master agreement; waiting is costed at boil-off only"
        )
        return block
    if currency == "EUR":
        block["eur_per_day"] = float(rate)
        return block
    used = _fx_rate(None, currency, "EUR", fx.on, fx)
    if used.rate is None:
        block["warning"] = (
            f"{vessel}: demurrage {rate:,.0f} {currency}/day ({terms.get('source')}) is not "
            f"converted: {used.missing}; waiting is costed at boil-off only"
        )
        block["fx"] = used.as_dict()
        return block
    block["eur_per_day"] = round(used.apply(float(rate)), 2)
    block["fx"] = used.as_dict()
    block["note"] = f"{rate:,.0f} {currency}/day from {terms.get('source')}, at {used.text()}"
    return block


def amounts(block: Mapping[str, Any] | None, amount_eur: float) -> dict[str, Any] | None:
    """One demurrage amount in EUR shown with its original currency and the rate."""

    if not block or block.get("eur_per_day") in (None, 0):
        return None
    eur_per_day = float(block["eur_per_day"])
    days = amount_eur / eur_per_day
    return {
        "amount_eur": round(amount_eur, 2),
        "amount_original": round(days * float(block["rate_per_day"]), 2),
        "currency": block["currency"],
        "excess_days": round(days, 3),
        "rate_per_day": block["rate_per_day"],
        "eur_per_day": eur_per_day,
        "source": block["source"],
        "fx": block["fx"],
    }


def reporting(fx: FxBook, figures: Mapping[str, float]) -> dict[str, Any]:
    """EUR figures beside their value in the viewer's reporting currency, at the same fix."""

    currency = fx.choice.reporting_currency
    if currency == "EUR":
        return {"currency": "EUR", "fx": None, "figures": None}
    used = _fx_rate(None, "EUR", currency, fx.on, fx)
    if used.rate is None:
        return {
            "currency": currency,
            "fx": used.as_dict(),
            "figures": None,
            "warning": f"not shown in {currency}: {used.missing}",
        }
    return {
        "currency": currency,
        "fx": used.as_dict(),
        "figures": {name: round(value * used.rate, 2) for name, value in figures.items()},
    }


__all__ = [
    "FxResolution",
    "_fx_rate",
    "FX_SOURCES",
    "FxBook",
    "FxChoice",
    "FxChoiceError",
    "FxRate",
    "REPORTING_CURRENCIES",
    "amounts",
    "convert",
    "demurrage_terms",
    "fx_book",
    "public_fx_rows",
    "reporting",
]
