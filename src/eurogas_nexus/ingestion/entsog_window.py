"""Explicit bounded ENTSOG window policy; no fetching or source authority.

Provider date envelopes are not guaranteed UTC interval filters. The official
v3.0 manual warns that timezone conversion may be ignored except for WET.
Reuse the existing EU calendar to select date labels; never relabel provider
timestamps or infer an atomic snapshot, full history or revision history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.market.gas_day import (
    EU_CAM_UTC_CALENDAR,
    gas_day_label,
    gas_day_start_for_date,
)
from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError, validate_entsog_window


class EntsogWindowPolicyError(EntsogWindowError):
    code = "entsog_window_policy_invalid"


class EntsogWindowAnchorError(EntsogWindowError):
    code = "entsog_window_anchor_invalid"


def require_aware_anchor(value: Any) -> datetime:
    """Accept ISO offset timestamps or aware datetimes; never guess naive UTC."""
    try:
        anchor = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(anchor, datetime) or anchor.tzinfo is None or anchor.utcoffset() is None:
            raise ValueError
        return anchor.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        raise EntsogWindowAnchorError("ENTSOG run anchor must be an aware timestamp.") from None


@dataclass(frozen=True)
class EntsogSelectedWindow:
    from_date: str
    to_date: str
    anchor_utc: datetime | None = None
    target_start_utc: datetime | None = None
    target_end_utc: datetime | None = None
    open_gas_day_label: str | None = None
    lookback_gas_days: int | None = None

    @property
    def rolling(self) -> bool:
        return self.lookback_gas_days is not None

    @property
    def reference(self) -> str:
        return (
            f"entsog-window/1;mode={'rolling-gas-day' if self.rolling else 'explicit'};"
            f"from={self.from_date};to={self.to_date}"
            + (
                f";calendar={EU_CAM_UTC_CALENDAR};anchor={self.anchor_utc.isoformat()}"
                f";open_at_anchor={self.open_gas_day_label}"
                if self.rolling
                else ""
            )
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "mode": "rolling-gas-day" if self.rolling else "explicit",
            "from": self.from_date,
            "to": self.to_date,
            "anchor_utc": self.anchor_utc.isoformat() if self.anchor_utc else None,
            "calendar": EU_CAM_UTC_CALENDAR if self.rolling else None,
            "lookback_gas_days": self.lookback_gas_days,
            "target_start_utc": self.target_start_utc.isoformat()
            if self.target_start_utc
            else None,
            "target_end_utc": self.target_end_utc.isoformat() if self.target_end_utc else None,
            "open_gas_day_at_anchor": self.open_gas_day_label,
            "provider_date_envelope_is_exact_utc_filter": False,
            "snapshot_consistent": False,
        }


@dataclass(frozen=True)
class EntsogWindowPolicy:
    from_date: str | None = None
    to_date: str | None = None
    lookback_gas_days: int | None = None

    def __post_init__(self) -> None:
        if self.lookback_gas_days is None:
            validate_entsog_window(self.from_date, self.to_date)
        elif (
            self.from_date is not None
            or self.to_date is not None
            or type(self.lookback_gas_days) is not int
            or not 1 <= self.lookback_gas_days <= 30
        ):
            raise EntsogWindowPolicyError(
                "ENTSOG rolling lookback must be 1..30 gas days and cannot mix with explicit dates."
            )

    def select(self, anchor: datetime | None = None) -> EntsogSelectedWindow:
        if self.lookback_gas_days is None:
            if anchor is not None:
                raise EntsogWindowPolicyError(
                    "ENTSOG explicit dates cannot mix with a rolling anchor."
                )
            return EntsogSelectedWindow(self.from_date, self.to_date)
        instant = require_aware_anchor(anchor)
        current = date.fromisoformat(gas_day_label(instant, EU_CAM_UTC_CALENDAR))
        start = current - timedelta(days=self.lookback_gas_days)
        end = current + timedelta(days=1)
        window = validate_entsog_window(start.isoformat(), end.isoformat())
        return EntsogSelectedWindow(
            window["from"],
            window["to"],
            instant,
            gas_day_start_for_date(start, EU_CAM_UTC_CALENDAR),
            gas_day_start_for_date(end, EU_CAM_UTC_CALENDAR),
            current.isoformat(),
            self.lookback_gas_days,
        )
