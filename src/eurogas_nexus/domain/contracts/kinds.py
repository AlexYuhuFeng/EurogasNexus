"""Contract kinds: the discriminator and each kind's typed terms (docs/product/CONTRACT_TYPES.md).

A firm holds several kinds of agreement whose terms, optionality and risks differ. Every
contract stays one row of ``upstream_resource_contracts``; ``contract_kind`` says which kind it
is and ``kind_terms`` holds the terms of that kind as one strictly validated JSON block (a
schema label inside, ``extra="forbid"``). For a typed kind the base columns every consumer
reads (point, period, MWh/d, price, tolerances) are *derived* here from the terms, so the
form never asks for a column the kind does not have and there is one authority for them.

- ``SUPPLY_GSA``: today's shape; no typed block (terms the form does not hold go to the
  unmodelled-terms text).
- ``UPSTREAM_TENDER``: producer gas sold by tender; DCQ with a min/max swing, index ± diff.
- ``LNG_MSPA``: an LNG master agreement; no volume or price of its own, so it feeds no book.
- ``LNG_CARGO``: a Confirmation Notice under an MSPA: one cargo, FOB or DES, in a window.

Other kinds are named (so the vocabulary is complete) but not authorable yet.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from eurogas_nexus.domain.ontology.quantity import convert, convert_price

SUPPLY_GSA = "SUPPLY_GSA"
UPSTREAM_TENDER = "UPSTREAM_TENDER"
LNG_MSPA = "LNG_MSPA"
LNG_CARGO = "LNG_CARGO"
LNG_TERM_SPA = "LNG_TERM_SPA"
HUB_TRADE = "HUB_TRADE"
TRANSPORT_CAPACITY = "TRANSPORT_CAPACITY"
LNG_TERMINAL_CAPACITY = "LNG_TERMINAL_CAPACITY"
STORAGE_CAPACITY = "STORAGE_CAPACITY"

#: Every kind the vocabulary names, in the order the design lists them.
CONTRACT_KINDS = (
    SUPPLY_GSA,
    UPSTREAM_TENDER,
    LNG_MSPA,
    LNG_CARGO,
    LNG_TERM_SPA,
    HUB_TRADE,
    TRANSPORT_CAPACITY,
    LNG_TERMINAL_CAPACITY,
    STORAGE_CAPACITY,
)
#: Kinds a person may create or edit in this release.
AUTHORABLE_KINDS = frozenset({SUPPLY_GSA, UPSTREAM_TENDER, LNG_MSPA, LNG_CARGO})
#: Kinds whose base columns are derived from typed terms.
TYPED_KINDS = frozenset({UPSTREAM_TENDER, LNG_MSPA, LNG_CARGO})
#: Kinds that frame other contracts and are never a position themselves.
MASTER_KINDS = frozenset({LNG_MSPA})
#: The kind a confirmation's master must be.
MASTER_OF = {LNG_CARGO: LNG_MSPA}
#: The default for a row written before kinds existed (migration 0072).
DEFAULT_KIND = SUPPLY_GSA

#: Native price units a typed contract may be quoted in.
PriceUnit = Literal["EUR/MWh", "GBP/MWh", "GBp/th", "USD/MMBtu"]
_UNIT_CURRENCY = {"EUR/MWh": "EUR", "GBP/MWh": "GBP", "GBp/th": "GBP", "USD/MMBtu": "USD"}
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_MAX_TERM_DAYS = 366 * 25


class ContractKindError(ValueError):
    """A kind or its terms are not acceptable; ``code`` is stable, ``detail`` says why."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


Text = Annotated[str, Field(min_length=1, max_length=256)]
ShortText = Annotated[str, Field(min_length=1, max_length=128)]


class _Terms(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class UpstreamTenderTerms(_Terms):
    """Producer offtake sold by tender: what the desk bid for and must lift."""

    schema_: Literal["upstream-tender/v1"] = Field("upstream-tender/v1", alias="schema")
    # Parties
    counterparty_id: ShortText | None = None
    seller_name: ShortText
    field_name: ShortText | None = None
    tender_reference: ShortText | None = None
    # Delivery
    delivery_point: Text
    period_start: date
    period_end: date
    nomination: Literal["day_ahead", "within_day"] = "day_ahead"
    allowed_exit_points: list[ShortText] = Field(default_factory=list, max_length=20)
    # Quantity and flexibility
    dcq_mwh_per_day: float = Field(gt=0, le=1_000_000)
    min_dcq_mwh_per_day: float = Field(ge=0, le=1_000_000)
    max_dcq_mwh_per_day: float = Field(gt=0, le=1_000_000)
    offtake_obligation_pct: float | None = Field(default=None, ge=0, le=100)
    field_outage_force_majeure: bool = True
    # Price
    price_type: Literal["index", "fixed"] = "index"
    index: ShortText | None = None
    differential: float = Field(default=0.0, ge=-1_000, le=1_000)
    fixed_price: float | None = Field(default=None, ge=0, le=10_000)
    price_unit: PriceUnit
    entry_cost_per_mwh: float | None = Field(default=None, ge=0, le=1_000)
    # Payment and credit
    payment_lag_days: int = Field(default=20, ge=0, le=180)
    financing_rate_pct: float = Field(ge=0, le=50)

    @model_validator(mode="after")
    def _consistent(self) -> UpstreamTenderTerms:
        if self.period_end < self.period_start:
            raise ValueError("period_end is before period_start")
        if (self.period_end - self.period_start).days > _MAX_TERM_DAYS:
            raise ValueError("the tender period is longer than 25 years")
        if not self.min_dcq_mwh_per_day <= self.dcq_mwh_per_day <= self.max_dcq_mwh_per_day:
            raise ValueError("the swing must read min DCQ <= DCQ <= max DCQ")
        if self.price_type == "index" and not self.index:
            raise ValueError("an index-priced tender names its index")
        if self.price_type == "fixed" and self.fixed_price is None:
            raise ValueError("a fixed-price tender states its price")
        return self


class LngMspaTerms(_Terms):
    """An LNG master sale and purchase agreement: the frame cargoes are confirmed under."""

    schema_: Literal["lng-mspa/v1"] = Field("lng-mspa/v1", alias="schema")
    counterparty_id: ShortText | None = None
    counterparty_name: ShortText
    our_side: Literal["buyer", "seller"]
    master_reference: ShortText | None = None
    signed_on: date | None = None
    governing_law: ShortText | None = None
    term_start: date
    term_end: date | None = None  # None: evergreen until terminated
    delivery_terms: list[Literal["FOB", "DES"]] = Field(min_length=1, max_length=2)
    laytime_hours: float | None = Field(default=None, ge=0, le=480)
    demurrage_usd_per_day: float | None = Field(default=None, ge=0, le=2_000_000)
    gcv_min_mj_m3: float | None = Field(default=None, ge=30, le=50)
    gcv_max_mj_m3: float | None = Field(default=None, ge=30, le=50)
    diversion_allowed: bool = False
    credit_support: Literal["none", "parent_guarantee", "letter_of_credit", "cash"] = "none"
    credit_support_amount: float | None = Field(default=None, ge=0, le=10_000_000_000)
    credit_support_currency: Literal["USD", "EUR", "GBP"] | None = None
    payment_lag_days: int = Field(default=20, ge=0, le=180)

    @model_validator(mode="after")
    def _consistent(self) -> LngMspaTerms:
        if self.term_end is not None and self.term_end < self.term_start:
            raise ValueError("term_end is before term_start")
        if len(set(self.delivery_terms)) != len(self.delivery_terms):
            raise ValueError("a delivery term is listed twice")
        if (
            self.gcv_min_mj_m3 is not None
            and self.gcv_max_mj_m3 is not None
            and self.gcv_min_mj_m3 > self.gcv_max_mj_m3
        ):
            raise ValueError("the quality range reads min > max")
        if (self.credit_support_amount is None) != (self.credit_support_currency is None):
            raise ValueError("a credit support amount needs its currency, and the reverse")
        if self.credit_support == "none" and self.credit_support_amount:
            raise ValueError("credit support 'none' carries no amount")
        return self


class LngCargoTerms(_Terms):
    """A Confirmation Notice: one cargo under an MSPA."""

    schema_: Literal["lng-cargo/v1"] = Field("lng-cargo/v1", alias="schema")
    cargo_reference: ShortText | None = None
    delivery_term: Literal["FOB", "DES"]
    load_port: ShortText | None = None
    discharge_terminal: ShortText | None = None
    #: The hub the discharge terminal sends out into (from the terminal register).
    terminal_hub: Annotated[str, Field(min_length=2, max_length=16)] | None = None
    window_start: date
    window_end: date
    narrowed_start: date | None = None
    narrowed_end: date | None = None
    quantity_mmbtu: float = Field(gt=0, le=6_000_000)
    tolerance_pct: float = Field(ge=0, le=10)
    price_formula: Literal["hh", "brent", "hub", "fixed"]
    slope: float | None = Field(default=None, ge=0, le=3)
    constant: float | None = Field(default=None, ge=-50, le=100)
    hub_index: ShortText | None = None
    fixed_price: float | None = Field(default=None, ge=0, le=1_000)
    price_unit: PriceUnit
    pricing_month: Annotated[str, Field(pattern=_MONTH.pattern)]
    boil_off_pct_per_day: float | None = Field(default=None, ge=0, le=1)
    vessel_name: ShortText | None = None
    #: The own cargo in the vessel feed / ETRM (``lng_cargoes``), once a vessel is named.
    lng_cargo_id: Annotated[str, Field(min_length=1, max_length=96)] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> LngCargoTerms:
        if self.window_end < self.window_start:
            raise ValueError("window_end is before window_start")
        if (self.window_end - self.window_start).days > 62:
            raise ValueError("a cargo window is at most two months")
        if (self.narrowed_start is None) != (self.narrowed_end is None):
            raise ValueError("a narrowed window has a start and an end")
        if self.narrowed_start is not None and self.narrowed_end is not None:
            inside = self.window_start <= self.narrowed_start <= self.narrowed_end
            if not (inside and self.narrowed_end <= self.window_end):
                raise ValueError("the narrowed window lies inside the delivery window")
        if self.delivery_term == "FOB" and not self.load_port:
            raise ValueError("an FOB cargo names its load port")
        if self.delivery_term == "DES" and not (self.discharge_terminal and self.terminal_hub):
            raise ValueError("a DES cargo names its discharge terminal and the terminal's hub")
        if self.price_formula in {"hh", "brent"} and (self.slope is None or self.constant is None):
            raise ValueError("a slope formula states its slope and constant")
        if self.price_formula == "hub" and not self.hub_index:
            raise ValueError("a hub-indexed cargo names its index")
        if self.price_formula == "fixed" and self.fixed_price is None:
            raise ValueError("a fixed-price cargo states its price")
        return self

    def delivery_days(self) -> tuple[date, date]:
        """The window that applies now: the narrowed one once agreed."""

        if self.narrowed_start is not None and self.narrowed_end is not None:
            return self.narrowed_start, self.narrowed_end
        return self.window_start, self.window_end

    def energy_mwh(self) -> float:
        return convert(self.quantity_mmbtu, "MMBtu", "MWh")


_TERMS_MODEL: dict[str, type[_Terms]] = {
    UPSTREAM_TENDER: UpstreamTenderTerms,
    LNG_MSPA: LngMspaTerms,
    LNG_CARGO: LngCargoTerms,
}


def validate_kind(kind: object) -> str:
    """Return the kind, refusing a code the vocabulary does not name."""

    text = str(kind or "").strip().upper()
    if text not in CONTRACT_KINDS:
        raise ContractKindError("contract_kind_unknown", f"{kind!r} is not a contract kind")
    return text


def parse_terms(kind: str, terms: object) -> _Terms | None:
    """Validate one kind's terms; ``None`` for a kind without a typed block.

    Raises:
        ContractKindError: ``contract_kind_terms_invalid`` with the first problem in words,
            or ``contract_kind_terms_unexpected`` for terms on a kind that has none.
    """

    model = _TERMS_MODEL.get(kind)
    if model is None:
        if terms not in (None, {}):
            raise ContractKindError(
                "contract_kind_terms_unexpected", f"{kind} has no typed terms in this release"
            )
        return None
    if not isinstance(terms, dict):
        raise ContractKindError("contract_kind_terms_invalid", f"{kind} needs its terms")
    try:
        return model.model_validate(terms)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ()))
        message = str(first.get("msg", "invalid")).removeprefix("Value error, ")
        raise ContractKindError(
            "contract_kind_terms_invalid", f"{where}: {message}" if where else message
        ) from None


def canonical_terms(parsed: _Terms | None) -> dict[str, Any] | None:
    """The stored (and hashed) form of validated terms: JSON-ready, with the schema label."""

    if parsed is None:
        return None
    return parsed.model_dump(mode="json", by_alias=True)


def terms_of(kind: str | None, stored: object) -> _Terms | None:
    """Read stored terms back as their model; ``None`` when absent or no longer valid."""

    if not kind or not isinstance(stored, dict) or kind not in _TERMS_MODEL:
        return None
    try:
        return _TERMS_MODEL[kind].model_validate(stored)
    except ValidationError:
        return None


# ------------------------------------------------------------------ prices and base columns


def price_per_mwh(value: float, unit: str) -> tuple[float, str]:
    """A native price as money per MWh in its own currency (p/th -> GBP/MWh)."""

    currency = _UNIT_CURRENCY[unit]
    return convert_price(value, unit, f"{currency}/MWh"), currency


def price_basis(kind: str, terms: _Terms | None) -> dict[str, Any]:
    """How a typed contract is priced, for every consumer that needs to know.

    ``{"basis": "fixed", "price_mwh", "currency"}``, ``{"basis": "index", "index",
    "differential_mwh", "currency"}`` or ``{"basis": "formula", "label"}`` (a slope on HH or
    Brent: no hub price can stand in for it). ``{"basis": "none"}`` for a master.
    """

    if isinstance(terms, UpstreamTenderTerms):
        if terms.price_type == "fixed" and terms.fixed_price is not None:
            price, currency = price_per_mwh(terms.fixed_price, terms.price_unit)
            return {"basis": "fixed", "price_mwh": price, "currency": currency}
        diff, currency = price_per_mwh(terms.differential, terms.price_unit)
        return {
            "basis": "index",
            "index": terms.index,
            "differential_mwh": diff,
            "currency": currency,
        }
    if isinstance(terms, LngCargoTerms):
        if terms.price_formula == "fixed" and terms.fixed_price is not None:
            price, currency = price_per_mwh(terms.fixed_price, terms.price_unit)
            return {"basis": "fixed", "price_mwh": price, "currency": currency}
        if terms.price_formula == "hub":
            diff, currency = price_per_mwh(terms.constant or 0.0, terms.price_unit)
            return {
                "basis": "index",
                "index": terms.hub_index,
                "differential_mwh": diff,
                "currency": currency,
            }
        driver = "HH" if terms.price_formula == "hh" else "Brent"
        return {
            "basis": "formula",
            "label": f"{terms.slope:g} x {driver} + {terms.constant:g} {terms.price_unit}",
            "currency": _UNIT_CURRENCY[terms.price_unit],
        }
    return {"basis": "none"}


def period_label(start: date, end: date) -> str:
    """``2026-12..2027-02`` (16 characters, the base ``gas_year`` column's width)."""

    return f"{start:%Y-%m}..{end:%Y-%m}"


def derive_base_fields(
    kind: str, terms: _Terms | None, *, master: _Terms | None = None
) -> dict[str, Any]:
    """The base columns of a typed contract, derived from its terms (one authority).

    For ``SUPPLY_GSA`` (no typed block) nothing is derived and the caller keeps the columns the
    person entered. ``notes_fields`` are merged into the row's notes JSON (counterparty, index
    basis) so the existing readers of those keys see the typed values.
    """

    if isinstance(terms, UpstreamTenderTerms):
        basis = price_basis(kind, terms)
        dcq = terms.dcq_mwh_per_day
        up = (terms.max_dcq_mwh_per_day - dcq) / dcq * 100
        down = (dcq - terms.min_dcq_mwh_per_day) / dcq * 100
        price = basis.get("price_mwh", basis.get("differential_mwh", 0.0))
        return {
            "resource_type": "BEACH_DELIVERY",
            "delivery_point_name": terms.delivery_point,
            "gas_year": period_label(terms.period_start, terms.period_end),
            "delivery_quantity_mwh_per_day": dcq,
            "contract_price_gbp_mwh": round(price, 6),
            "contract_price_currency": basis["currency"],
            "settlement_frequency": "monthly",
            "upstream_payment_lag_days": terms.payment_lag_days,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": round(down, 4),
            "nomination_tolerance_pct": round(up, 4),
            "annual_financing_rate_pct": terms.financing_rate_pct,
            "allowed_exit_points": list(terms.allowed_exit_points) or [terms.delivery_point],
            "eligible_sale_modes": ["LOCAL_MARKET_SALE", "TARGET_MARKET_SALE", "REROUTE_SALE"],
            # Entry/lifting cost is stated per MWh in the price's currency.
            "variable_cost_gbp_mwh": terms.entry_cost_per_mwh,
            "notes_fields": {
                "counterparty": terms.seller_name,
                "index_basis": terms.index if basis["basis"] == "index" else "fixed",
                "price_basis": basis["basis"],
            },
        }
    if isinstance(terms, LngMspaTerms):
        end = terms.term_end
        return {
            "resource_type": "LNG_REGAS",
            "delivery_point_name": "LNG master agreement",
            "gas_year": (
                period_label(terms.term_start, end) if end else f"{terms.term_start:%Y}+"
            ),
            "delivery_quantity_mwh_per_day": 0.0,
            "contract_price_gbp_mwh": 0.0,
            "contract_price_currency": "USD",
            "settlement_frequency": "per_cargo",
            "upstream_payment_lag_days": terms.payment_lag_days,
            "screen_sale_cash_lag_days": 0,
            "delivery_tolerance_pct": 0.0,
            "nomination_tolerance_pct": 0.0,
            "annual_financing_rate_pct": 0.0,
            "allowed_exit_points": [],
            "eligible_sale_modes": [],
            "notes_fields": {
                "counterparty": terms.counterparty_name,
                "price_basis": "none",
            },
        }
    if isinstance(terms, LngCargoTerms):
        basis = price_basis(kind, terms)
        first, last = terms.delivery_days()
        days = (last - first).days + 1
        lag = master.payment_lag_days if isinstance(master, LngMspaTerms) else 20
        point = (
            terms.discharge_terminal if terms.delivery_term == "DES" else terms.load_port
        ) or "LNG cargo"
        price = basis.get("price_mwh", basis.get("differential_mwh", 0.0))
        return {
            "resource_type": "LNG_REGAS",
            "delivery_point_name": point,
            "gas_year": period_label(first, last),
            "delivery_quantity_mwh_per_day": round(terms.energy_mwh() / days, 3),
            "contract_price_gbp_mwh": round(price, 6),
            "contract_price_currency": basis.get("currency", "USD"),
            "settlement_frequency": "per_cargo",
            "upstream_payment_lag_days": lag,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": terms.tolerance_pct,
            "nomination_tolerance_pct": 0.0,
            "annual_financing_rate_pct": 0.0,
            "allowed_exit_points": [terms.terminal_hub] if terms.terminal_hub else [],
            "eligible_sale_modes": ["LOCAL_MARKET_SALE"] if terms.delivery_term == "DES" else [],
            "notes_fields": {
                "counterparty": (
                    master.counterparty_name if isinstance(master, LngMspaTerms) else None
                ),
                "index_basis": basis.get("index") or basis.get("label") or "fixed",
                "price_basis": basis["basis"],
            },
        }
    return {}


# --------------------------------------------------------------------------- consumers


def feeds_book(kind: str | None, terms: _Terms | None) -> bool:
    """Whether a contract is a physical position at a European hub.

    A master never is; an FOB cargo is not until it is sold or discharged (it is exposure to
    the formula, not to a hub). Everything else is.
    """

    if kind in MASTER_KINDS:
        return False
    if kind == LNG_CARGO:
        return isinstance(terms, LngCargoTerms) and terms.delivery_term == "DES"
    return True


def position_window(
    kind: str | None, terms: _Terms | None
) -> tuple[date, date] | None:
    """The first and last gas day of a typed contract, or ``None`` to read the gas year."""

    if isinstance(terms, UpstreamTenderTerms):
        return terms.period_start, terms.period_end
    if isinstance(terms, LngCargoTerms):
        return terms.delivery_days()
    return None


def position_hub_text(kind: str | None, terms: _Terms | None, delivery_point: str) -> str:
    """The text the identity resolver maps to a hub: the terminal's hub for a DES cargo."""

    if isinstance(terms, LngCargoTerms) and terms.terminal_hub:
        return terms.terminal_hub
    return delivery_point


def counterparty_id_of(terms: _Terms | None, master: _Terms | None = None) -> str | None:
    """The credit line a typed contract faces: its own, or (a cargo) its master's."""

    own = getattr(terms, "counterparty_id", None)
    if own:
        return str(own)
    return getattr(master, "counterparty_id", None) if master is not None else None


def check_confirmation(
    kind: str, terms: _Terms | None, master_kind: str | None, master: _Terms | None
) -> None:
    """A confirmation names an MSPA that allows its delivery term.

    Raises:
        ContractKindError: ``contract_master_required``, ``contract_master_kind`` or
            ``contract_master_term`` in words.
    """

    expected = MASTER_OF.get(kind)
    if expected is None:
        if master_kind is not None:
            raise ContractKindError(
                "contract_master_unexpected", f"a {kind} is not confirmed under a master"
            )
        return
    if master_kind is None:
        raise ContractKindError(
            "contract_master_required", "a cargo confirmation names its master agreement"
        )
    if master_kind != expected:
        raise ContractKindError(
            "contract_master_kind", f"the master of a {kind} is an {expected}, not {master_kind}"
        )
    if (
        isinstance(terms, LngCargoTerms)
        and isinstance(master, LngMspaTerms)
        and terms.delivery_term not in master.delivery_terms
    ):
        raise ContractKindError(
            "contract_master_term",
            f"the master agreement allows {', '.join(master.delivery_terms)}, "
            f"not {terms.delivery_term}",
        )


def headline(kind: str | None, terms: _Terms | None) -> dict[str, Any] | None:
    """The one figure that matters for the kind, for the list view (native units)."""

    if isinstance(terms, UpstreamTenderTerms):
        return {
            "key": "swing",
            "value": terms.dcq_mwh_per_day,
            "min": terms.min_dcq_mwh_per_day,
            "max": terms.max_dcq_mwh_per_day,
            "unit": "MWh/d",
        }
    if isinstance(terms, LngCargoTerms):
        first, last = terms.delivery_days()
        return {
            "key": "cargo",
            "value": round(terms.quantity_mmbtu / 1_000_000, 3),
            "unit": "TBtu",
            "term": terms.delivery_term,
            "window": [first.isoformat(), last.isoformat()],
        }
    return None


def infer_kind(resource_type: str | None, notes: dict | None) -> str:
    """The kind a row written before kinds existed is given (migration 0072).

    Every such row was entered in the supply-contract shape and keeps feeding the book exactly
    as before, so it is a ``SUPPLY_GSA`` until a person confirms or changes the kind; no
    other kind is guessed (a guessed master would silently leave the book).
    """

    return DEFAULT_KIND

