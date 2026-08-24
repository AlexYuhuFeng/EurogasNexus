"""R34A runtime composition for storage and nomination assessment.

This module reads PostgreSQL master/observation rows and produces the validated
optimizer inputs. It performs no provider calls and never fabricates missing
facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from eurogas_nexus.db.models.storage_nomination import (
    NominationWindowMasterRecord,
    StorageFacilityMasterRecord,
    StorageInventoryObservationRecord,
)
from eurogas_nexus.domain.market_intelligence.normalized_view import (
    FxRateInput,
    convert_currency,
)
from eurogas_nexus.optimization.nomination import NominationWindow
from eurogas_nexus.optimization.storage import StorageFacility, StoragePeriod


@dataclass(frozen=True, slots=True)
class ComposedStorageDispatch:
    """DB-composed storage dispatch inputs (or blockers)."""

    facility: StorageFacility | None = None
    periods: tuple[StoragePeriod, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.facility is not None and bool(self.periods) and not self.blockers


@dataclass(frozen=True, slots=True)
class ComposedNominationWindows:
    """DB-composed nomination window rules (or blockers)."""

    windows: tuple[NominationWindow, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return bool(self.windows) and not self.blockers


def compose_storage_dispatch(
    *,
    facility: StorageFacilityMasterRecord | None,
    inventory: StorageInventoryObservationRecord | None,
    market_rows: list,
    fx_rows: list,
    gas_day: date,
    max_periods: int,
) -> ComposedStorageDispatch:
    """Compose a facility, initial inventory, and market-price periods."""

    blockers: list[str] = []
    warnings: list[str] = []
    source_refs: list[str] = []
    if facility is None:
        blockers.append("STORAGE_FACILITY_MISSING")
        return ComposedStorageDispatch(blockers=tuple(blockers))
    if inventory is None:
        blockers.append(f"STORAGE_INVENTORY_MISSING:{facility.facility_id}")
    else:
        source_refs.append(f"storage_inventory_observation:{inventory.observation_id}")

    source_refs.append(f"storage_facility_master:{facility.facility_id}")
    periods = _market_periods_for_hub(
        facility.market_hub,
        market_rows=market_rows,
        fx_rows=fx_rows,
        gas_day=gas_day,
        max_periods=max_periods,
        blockers=blockers,
        warnings=warnings,
        source_refs=source_refs,
    )
    if not periods:
        blockers.append(f"STORAGE_PRICE_PERIODS_MISSING:{facility.market_hub}")

    if blockers:
        return ComposedStorageDispatch(
            facility=None,
            periods=(),
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            source_refs=tuple(dict.fromkeys(source_refs)),
        )

    facility_input = StorageFacility(
        initial_inventory_mwh=inventory.inventory_mwh if inventory else 0.0,
        minimum_inventory_mwh=facility.minimum_inventory_mwh,
        maximum_inventory_mwh=facility.maximum_inventory_mwh,
        maximum_injection_mwh=facility.maximum_injection_mwh,
        maximum_withdrawal_mwh=facility.maximum_withdrawal_mwh,
        injection_efficiency=facility.injection_efficiency,
        withdrawal_efficiency=facility.withdrawal_efficiency,
        injection_cost_gbp_mwh=facility.injection_cost_gbp_mwh,
        withdrawal_cost_gbp_mwh=facility.withdrawal_cost_gbp_mwh,
        terminal_inventory_mwh=facility.terminal_inventory_mwh,
    )
    return ComposedStorageDispatch(
        facility=facility_input,
        periods=tuple(periods),
        warnings=tuple(dict.fromkeys(warnings)),
        source_refs=tuple(dict.fromkeys(source_refs)),
    )


def compose_nomination_windows(
    *,
    window_rows: list[NominationWindowMasterRecord],
) -> ComposedNominationWindows:
    """Map DB-owned window masters into optimizer rules."""

    blockers: list[str] = []
    if not window_rows:
        blockers.append("NOMINATION_WINDOWS_MISSING")
        return ComposedNominationWindows(blockers=tuple(blockers))

    windows = tuple(
        NominationWindow(
            window_id=row.window_id,
            opens_at=row.opens_at,
            closes_at=row.closes_at,
            maximum_change_mwh=row.maximum_change_mwh,
            maximum_change_pct=row.maximum_change_pct,
        )
        for row in sorted(window_rows, key=lambda item: item.window_id)
    )
    source_refs = tuple(
        f"nomination_window_master:{row.window_id}" for row in sorted(
            window_rows, key=lambda item: item.window_id
        )
    )
    return ComposedNominationWindows(windows=windows, source_refs=source_refs)


def _market_periods_for_hub(
    hub: str,
    *,
    market_rows: list,
    fx_rows: list,
    gas_day: date,
    max_periods: int,
    blockers: list[str],
    warnings: list[str],
    source_refs: list[str],
) -> list[StoragePeriod]:
    candidates: list[tuple[datetime, object]] = []
    target = _normalise(hub)
    for row in market_rows:
        if target not in _row_keys(row):
            continue
        if not _row_covers_day(row, gas_day):
            continue
        period_start = _as_utc(row.period_start_utc)
        candidates.append((period_start, row))
    candidates.sort(key=lambda item: item[0])
    periods: list[StoragePeriod] = []
    for index, (_, row) in enumerate(candidates[:max_periods]):
        price = _price_gbp_mwh(row, fx_rows, gas_day, blockers)
        if price is None:
            continue
        periods.append(
            StoragePeriod(
                period_id=f"{row.observation_id}:{index}",
                market_price_gbp_mwh=price,
            )
        )
        source_refs.append(f"market_observation:{row.observation_id}")
        if row.source_system.endswith("_Sim"):
            warnings.append(f"storage_price_simulated:{row.source_system}")
    return periods


def _row_keys(row) -> set[str]:
    metadata = row.metadata_json or {}
    values = [
        row.market_venue,
        row.product.split()[0] if row.product.strip() else "",
        metadata.get("hub"),
        metadata.get("point_name"),
        metadata.get("market_area"),
    ]
    return {_normalise(value) for value in values if isinstance(value, str) and value.strip()}


def _row_covers_day(row, gas_day: date) -> bool:
    start = _as_utc(row.period_start_utc).date()
    end = _as_utc(row.period_end_utc).date()
    return start <= gas_day <= end


def _price_gbp_mwh(row, fx_rows: list, gas_day: date, blockers: list[str]) -> float | None:
    currency = (row.currency or "").strip().upper()
    unit = re.sub(r"\s+", "", (row.unit or "")).upper()
    if not unit.endswith("/MWH"):
        blockers.append(f"STORAGE_PRICE_UNIT_UNSUPPORTED:{row.observation_id}")
        return None
    if currency == "GBP":
        return round(float(row.price), 4)
    rates = [
        FxRateInput(
            pair=fx.pair,
            base_currency=fx.base_currency,
            quote_currency=fx.quote_currency,
            rate=fx.rate,
            observed_at_utc=f"{fx.value_date}T00:00:00+00:00",
        )
        for fx in fx_rows
        if fx.value_date <= gas_day.isoformat() and fx.rate > 0
    ]
    converted = convert_currency(float(row.price), currency, "GBP", rates)
    if converted is None:
        blockers.append(f"STORAGE_PRICE_FX_MISSING:{row.observation_id}:{currency}->GBP")
        return None
    return round(converted, 4)


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
