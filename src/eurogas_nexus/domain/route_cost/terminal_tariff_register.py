"""What landing one cargo at a terminal costs, and on which basis (CP-11, design C.5).

Resolution order when pricing a terminal for an arrival month and a cargo size:

1. the firm's own terms for that terminal (``TerminalTerms``: what the firm pays under its
   contracts);
2. the **reviewed** public tariff in force for the arrival month;
3. a **candidate** public tariff in force (not yet reviewed): priced, marked indicative;
4. nothing: left out, with the reason.

A public tariff at one terminal can be several figures of one product (a fixed charge per
cargo and a charge per MWh unloaded, or one total per cargo class); the charge for a cargo is
the per-class total of the smallest class that holds it, else the sum of the per-cargo figures
and the per-MWh figures times the cargo. Gas retained in kind and anything the figure excludes
(port fees, entry tariff) are reported, not added. Pure and DB-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from eurogas_nexus.domain.portfolio.lng_bid import CARGO_CLASSES, TerminalTerms, regas_charge

REVIEWED = "REVIEWED"
CANDIDATE = "CANDIDATE"
#: Per-cargo charge bases a cargo's regas charge is built from (others are reported).
_PER_CARGO = {"per_cargo"}
_PER_MWH = {"per_mwh_unloaded"}


@dataclass(frozen=True)
class PublicTariff:
    """One published figure, as the register holds it (only the fields pricing reads)."""

    tariff_id: str
    terminal_id: str
    product: str
    charge_basis: str
    amount: float | None
    currency: str
    review_status: str
    valid_from: date | None = None
    valid_to: date | None = None
    by_cargo_class: dict[str, float] | None = None
    excludes: tuple[str, ...] = ()
    source_url: str = ""


@dataclass(frozen=True)
class TerminalCharge:
    """The regas charge for one cargo and where it came from."""

    terminal_id: str
    basis: str  # firm_terms | reviewed_public | candidate_public | missing
    charge: float | None
    currency: str | None
    indicative: bool
    reason: str | None = None
    tariff_ids: tuple[str, ...] = ()
    excludes: tuple[str, ...] = field(default_factory=tuple)


def in_force(tariff: PublicTariff, day: date) -> bool:
    if tariff.valid_from is not None and day < tariff.valid_from:
        return False
    return tariff.valid_to is None or day <= tariff.valid_to


def _month_start(arrival_month: str) -> date:
    year, month = arrival_month.split("-")
    return date(int(year), int(month), 1)


def public_charge(rows: list[PublicTariff], cargo_mwh: float) -> float | None:
    """The charge for one cargo from the figures of one product, or None if it cannot land."""

    by_class = [row for row in rows if row.charge_basis == "per_cargo_class" and row.by_cargo_class]
    if by_class:
        totals = by_class[0].by_cargo_class or {}
        for name, energy in CARGO_CLASSES:
            if cargo_mwh <= energy * 1.05:
                total = totals.get(name)
                return None if total is None else float(total)
        return None
    priced = [row for row in rows if row.charge_basis in _PER_CARGO | _PER_MWH and row.amount is not None]
    if not priced:
        return None
    return sum(
        row.amount if row.charge_basis in _PER_CARGO else row.amount * cargo_mwh
        for row in priced
    )


def resolve_terminal_charge(
    terminal_id: str,
    *,
    arrival_month: str,
    cargo_mwh: float,
    firm_terms: TerminalTerms | None,
    public: list[PublicTariff],
    product: str = "spot",
    operator_needs_terms: bool = False,
) -> TerminalCharge:
    """Price one cargo at one terminal in the order of design C.5."""

    if firm_terms is not None:
        charge = regas_charge(firm_terms, cargo_mwh)
        if charge is not None:
            return TerminalCharge(
                terminal_id, "firm_terms", charge, firm_terms.currency, False,
                tariff_ids=(),
            )
    day = _month_start(arrival_month)
    rows = [row for row in public if row.terminal_id == terminal_id and in_force(row, day)]
    for status, basis, indicative in (
        (REVIEWED, "reviewed_public", False),
        (CANDIDATE, "candidate_public", True),
    ):
        for wanted in (product, "term", "spot"):
            chosen = [row for row in rows if row.review_status == status and row.product == wanted]
            if not chosen:
                continue
            charge = public_charge(chosen, cargo_mwh)
            if charge is None:
                continue
            excludes = tuple(sorted({item for row in chosen for item in row.excludes}))
            return TerminalCharge(
                terminal_id, basis, charge, chosen[0].currency, indicative,
                tariff_ids=tuple(row.tariff_id for row in chosen), excludes=excludes,
            )
    if operator_needs_terms and not rows:
        reason = "needs_firm_terms"
    elif not rows:
        reason = "no_tariff_in_force"
    else:
        reason = "cargo_class_not_offered"
    return TerminalCharge(terminal_id, "missing", None, None, False, reason=reason)
