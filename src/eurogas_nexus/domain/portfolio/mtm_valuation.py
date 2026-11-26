"""Forward FX and discounting for the ladder's mark-to-market (quant review 2026-11-26, 3.3).

A month's value ``(mark - price) x MWh`` is a cash flow paid after delivery, in the hub's
currency. Its value today, in the reporting currency, is that cash flow converted at the forward
FX for the delivery month and discounted to its payment date:

- **Payment date**: the 20th of the month after delivery (the EFET general agreement's default).
- **Forward FX**: ``domain.market.fx_forward.conversion_rate`` for the delivery month: a licensed
  forward when held, else covered interest parity from the ECB reference rates and the overnight
  benchmarks (SONIA, €STR, SOFR); a contract price in a third currency is converted the same way.
- **Discount factor**: ``1 / (1 + r·τ)`` up to a year, ``(1 + r)^-τ`` beyond, with ``r`` the
  reporting currency's overnight benchmark fixing (a flat rate, not a term curve) on its own day
  count.

Nothing is guessed: where a forward cannot be derived (beyond 24 months, no benchmark held) the
spot reference rate converts, and where no benchmark is held the month is not discounted; each
such fallback is counted in :attr:`ForwardValuation.fallbacks` so the read says it.

本模块为头寸阶梯盯市提供按交割月的远期汇率与按付款日（交割次月 20 日）的贴现因子。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from eurogas_nexus.domain.market.fx_forward import (
    Delivery,
    FxForwardError,
    FxHoldings,
    conversion_rate,
    discount_factor,
)

#: Day of the month after delivery on which a month's gas is paid (EFET default).
PAYMENT_DAY = 20


def payment_date(month: str) -> date:
    """The payment date of a delivery month ``YYYY-MM``: the 20th of the month after."""

    first = date(int(month[:4]), int(month[5:7]), 1)
    return (first + timedelta(days=32)).replace(day=PAYMENT_DAY)


def _delivery(month: str) -> Delivery:
    first = date(int(month[:4]), int(month[5:7]), 1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return Delivery(first, last, "month", f"{first:%b-%y}")


@dataclass
class ForwardValuation:
    """Forward FX and discount factors for one valuation, cached per month."""

    holdings: FxHoldings
    reporting_currency: str
    as_of: date
    #: Fallbacks taken, by kind: ``spot_fx`` (no forward), ``undiscounted`` (no benchmark).
    fallbacks: dict[str, set[str]] = field(default_factory=dict)
    _fx: dict[tuple[str, str, str], float | None] = field(default_factory=dict, repr=False)
    _df: dict[str, float] = field(default_factory=dict, repr=False)

    def fx(self, base: str, quote: str, month: str) -> float | None:
        """Units of ``quote`` per ``base`` for delivery in ``month``: forward, else spot."""

        key = (base.upper(), quote.upper(), month)
        if key not in self._fx:
            try:
                rate = conversion_rate(
                    self.holdings, key[0], key[1], as_of=self.as_of, delivery=_delivery(month)
                ).rate
            except FxForwardError:
                try:
                    rate = conversion_rate(self.holdings, key[0], key[1], as_of=self.as_of).rate
                    self.fallbacks.setdefault("spot_fx", set()).add(month)
                except FxForwardError:
                    rate = None
            self._fx[key] = rate
        return self._fx[key]

    def discount(self, month: str) -> float:
        """The discount factor of the month's payment date in the reporting currency."""

        if month not in self._df:
            try:
                factor = discount_factor(
                    self.holdings, self.reporting_currency, self.as_of, payment_date(month)
                )
            except FxForwardError:
                factor = 1.0
                self.fallbacks.setdefault("undiscounted", set()).add(month)
            self._df[month] = factor
        return self._df[month]

    def notes(self) -> list[str]:
        """What the valuation could not do as stated, in words."""

        out = []
        if self.fallbacks.get("spot_fx"):
            out.append(
                f"{len(self.fallbacks['spot_fx'])} delivery month(s) converted at the spot "
                "reference rate: no forward FX could be derived"
            )
        if self.fallbacks.get("undiscounted"):
            out.append(
                f"{len(self.fallbacks['undiscounted'])} delivery month(s) not discounted: no "
                f"{self.reporting_currency} benchmark fixing held"
            )
        return out
