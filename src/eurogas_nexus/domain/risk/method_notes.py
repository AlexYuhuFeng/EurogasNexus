"""Method notes behind the risk figures: what each figure is, includes and leaves out (NUM-05).

Every risk figure the API returns (the VaR proxy, mark-to-market, tenor exposure and the tenor
shock scenario on the position ladder; credit exposure; mandate usage; imported P&L; the
Today read's day P&L change) carries a ``method`` object built here, so the wording a risk
officer reviews lives in one place and a figure cannot be shown without saying what it
leaves out. The text is English; the client translates by ``i18n`` keys
(``risk.method.<key>.summary`` and ``risk.method.<key>.<includes|excludes>.<item>``, en and
zh in ``clients/web/src/i18n``). A summary may name parameters in braces (``{observations}``);
:func:`method_note` fills them from the response, and the client's strings use the same
names as ``{{observations}}``.

Pure: no database, no HTTP. Changing a note changes no number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Wording status: drafted from the code's own documented method, awaiting risk review.
REVIEW_STATUS = "drafted; awaiting risk review"


@dataclass(frozen=True)
class MethodNote:
    """What one risk figure is, what it includes and what it leaves out."""

    key: str
    summary: str
    #: (item key, text): what the figure is built from.
    includes: tuple[tuple[str, str], ...]
    #: (item key, text): what it does not cover, so nobody over-reads it.
    excludes: tuple[tuple[str, str], ...]


_NOTES: tuple[MethodNote, ...] = (
    MethodNote(
        "var_proxy",
        "One-day 95% historical-simulation proxy over {observations} one-day changes of "
        "daily closes: the net open position per hub times each day's change in that hub's "
        "close, summed across hubs, and the loss at the 5th percentile. Given only with at "
        "least 250 changes (one year of trading days); with fewer it says not enough history.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the books you can see"),
            ("index", "Index-priced contracts by their flat-price exposure: on their index, "
                      "not long or short the hub's flat price"),
            ("closes", "One series per hub: its month-ahead closes from one source, or its "
                       "day-ahead closes where no month-ahead history is held; a missing day "
                       "is a gap, never filled with another product"),
            ("rolls", "Moves within one contract only: the day a rolling series changes "
                      "contract, and a gap of more than four days, are not scenarios"),
        ),
        excludes=(
            ("basis", "Basis between delivery months: one price series per hub"),
            ("optionality", "Optionality and volume flexibility in contracts"),
            ("shape_volume_credit", "Shape, volume and credit risk"),
            ("offsetting", "Hubs long in one delivery month and short in another: not computed"),
        ),
    ),
    MethodNote(
        "mark_to_market",
        "Each leg valued as (mark minus contract price) times its remaining MWh, month by "
        "month, at the forward-curve mark for its hub and month, converted into the reporting "
        "currency at the forward FX for the delivery month and discounted to the month's "
        "payment date (the 20th of the month after) at that currency's overnight benchmark.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the books you can see"),
            ("curve", "Forward curve from one snapshot of entitled quotes per hub: one "
                      "as-of, settlements first, then the hub's main source, each quote no "
                      "older than its tenor allows; a season or year is shaped by the quoted "
                      "quarters; a month no quote prices is not available, never filled with "
                      "another product's close"),
            ("index", "Index-priced contracts valued on their premium over the index's mark, "
                      "and on the basis when the index is another hub's"),
            ("rates", "Forward FX derived from the ECB reference rates and SONIA, €STR and "
                      "SOFR (a licensed forward first); where none can be derived, the spot "
                      "rate, and where no benchmark is held, undiscounted, as the read says"),
        ),
        excludes=(
            ("unpriced", "Legs without a mark, a contract price or an FX rate: counted as "
                         "unvalued, not as zero"),
            ("realised", "Realised P&L on gas already delivered"),
            ("costs", "Transport, storage and fees"),
        ),
    ),
    MethodNote(
        "tenor_exposure",
        "Net and gross position per hub over the delivery months held; gross is the sum of "
        "each month's absolute net position, what a curve shock acts on.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the books you can see"),
            ("index", "Flat-price exposure: an index-priced contract is on its index, so a "
                      "contract priced at its own hub's index adds volume but no exposure"),
        ),
        excludes=(
            ("price", "Prices: a volume figure, not a value"),
            ("flex", "Contract flexibility and optional volumes"),
        ),
    ),
    MethodNote(
        "tenor_shock",
        "Profit or loss if each named hub and month moved by the shock you entered, with "
        "everything else unchanged: net MWh times the shock, in the reporting currency.",
        includes=(
            ("shocks", "Only the hub-months you named"),
        ),
        excludes=(
            ("correlation", "Moves in months you did not name"),
            ("no_fx", "Hubs without an ECB rate to the reporting currency"),
        ),
    ),
    MethodNote(
        "credit_exposure",
        "Replacement exposure (undelivered volume at mark minus contract price, netted "
        "across the counterparty and floored at zero) plus receivables for the last "
        "receivable days of sales, minus collateral held; utilisation is that over the limit.",
        includes=(
            ("legs", "The counterparty's supply contracts and ETRM trades in the books you "
                     "can see, marked as the position ladder marks them"),
            ("evergreen", "Evergreen contracts only to the end of the current gas year"),
            ("rates", "Replacement value at the forward FX for each delivery month, discounted "
                      "to its payment date, as the ladder's mark-to-market"),
        ),
        excludes=(
            ("pfe", "Potential future exposure: today's exposure only"),
            ("cleared", "Exchange-cleared trades (clearing-house risk)"),
            ("payables", "Payables netted against receivables"),
            ("unvalued", "Legs without a mark, a price or an FX rate: counted as unvalued"),
        ),
    ),
    MethodNote(
        "mandate_usage",
        "Largest net hub-month position in the mandate's books and on the trader's own "
        "account against the mandate's size limit, with its hubs, tenor, products and hedge "
        "band checked.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the mandate's books"),
            ("evergreen", "Evergreen contracts only to the end of the current gas year"),
            ("index", "Net size and hedge cover in flat-price exposure: an index-priced "
                      "contract is on its index and needs no hedge"),
        ),
        excludes=(
            ("value", "Prices and P&L: a volume limit, not a loss limit"),
            ("other_books", "Positions the trader holds in books outside this mandate"),
        ),
    ),
    MethodNote(
        "pnl_snapshot",
        "Indicative P&L as the valuation snapshot states it, imported from its source and "
        "not recomputed here.",
        includes=(
            ("source", "The snapshot's own realised and unrealised components"),
        ),
        excludes=(
            ("recompute", "Any check against current marks"),
            ("costs", "Costs the source does not include"),
        ),
    ),
    MethodNote(
        "live_summary_pnl",
        "Sum of the latest P&L snapshots you can see, as imported; unknown, not zero, when "
        "no snapshot exists.",
        includes=(
            ("snapshots", "Imported valuation snapshots you can see"),
        ),
        excludes=(
            ("recompute", "Any check against current marks"),
            ("book_scope", "Snapshots carry no book: with book isolation only head office "
                           "sees them"),
        ),
    ),
    MethodNote(
        "day_pnl_change",
        "Net open position at the hub over the next 12 months times the change between its "
        "last two daily closes: the position ladder's flat-curve move, not a revaluation.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the books you can see"),
            ("closes", "The hub's last two daily closes of one series (month-ahead, or "
                       "day-ahead where no month-ahead history is held) and of one contract: "
                       "no figure across a roll"),
        ),
        excludes=(
            ("basis", "Moves that differ between delivery months"),
            ("new_trades", "The prices of trades done since the previous close: they count as "
                           "if held at that close"),
            ("offsetting", "Hubs long in one delivery month and short in another: not computed"),
        ),
    ),
    MethodNote(
        "net_position",
        "Net MWh per gas day: long positive, contracts at their daily quantity and screen "
        "trades spread over their delivery days.",
        includes=(
            ("legs", "Physical contracts and filled screen trades in the books you can see"),
        ),
        excludes=(
            ("flex", "Contract flexibility and nominations"),
        ),
    ),
)

METHOD_NOTES: Mapping[str, MethodNote] = {note.key: note for note in _NOTES}


class _Keep(dict):
    """Leaves a placeholder without a value as written, so a summary never fails to render."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def method_note(
    key: str,
    *,
    inputs_as_of: Mapping[str, str | None] | None = None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The ``method`` object for one figure: key, summary, includes, excludes, i18n keys.

    ``inputs_as_of`` names the inputs' as-of times (ISO strings, ``None`` when unknown);
    ``params`` fills the summary's placeholders. Raises ``KeyError`` for an unknown key.
    """

    note = METHOD_NOTES[key]
    values = dict(params or {})
    base = f"risk.method.{key}"
    return {
        "key": key,
        "summary": note.summary.format_map(_Keep(values)),
        "includes": [text for _, text in note.includes],
        "excludes": [text for _, text in note.excludes],
        "params": values,
        "inputs_as_of": dict(inputs_as_of or {}),
        "i18n": {
            "summary": f"{base}.summary",
            "includes": [f"{base}.includes.{item}" for item, _ in note.includes],
            "excludes": [f"{base}.excludes.{item}" for item, _ in note.excludes],
        },
        "review_status": REVIEW_STATUS,
    }


def i18n_entries() -> dict[str, str]:
    """Every English string the notes need, keyed as the client looks them up."""

    entries: dict[str, str] = {}
    for note in _NOTES:
        base = f"risk.method.{note.key}"
        summary = note.summary
        for name in ("observations",):
            summary = summary.replace("{" + name + "}", "{{" + name + "}}")
        entries[f"{base}.summary"] = summary
        for kind, items in (("includes", note.includes), ("excludes", note.excludes)):
            for item, text in items:
                entries[f"{base}.{kind}.{item}"] = text
    return entries
