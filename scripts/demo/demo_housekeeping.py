#!/usr/bin/env python
"""Keep the hosted demo server's small disk from filling up.

The product's retention job (``application/retention.py``) never removes a row without a
verified archive in object storage and keeps seven-year floors, so on the demo - which has no
object store - it removes nothing. This script is the demo's own housekeeping instead: the
demo store holds only fictional data and a simulated feed writes about 22 quotes a second, so
older rows are disposable. It is **demo profile only** and refuses to run anywhere else
(``security/local_accounts_policy.demo_profile_active``: the same boundary the demo start-up
and the demo test accounts use).

What it removes, by rule (never simply "everything older than"):

* **The simulated feed's own rows** - quotes and prints, feed status runs, booked simulated
  trades and nominations - older than the feed's horizon (default 48 hours, the feed's own
  ``RETENTION``). The feed already prunes them; this is the backstop for a feed that was
  stopped or wedged. The seed/feed advisory lock is held while they go, so a live feed pauses
  rather than writing into the tables being cleared.
* **Public-source data the demo ingests live** - ENTSOG flows and capacity, GIE and National
  Gas storage and LNG, REMIT messages, ECB/EIA prices and rates, demand, power, news - older
  than a rolling window (default 120 days). Only non-simulated sources are touched: the
  demo's simulated daily history (400 days of closes, six gas years of storage) is what its
  screens and risk read and is deliberately kept.
* **Operational tables that only grow** - ingestion runs and their issues, raw source page
  bytes (the demo has no object store; the digest receipt stays), closed/acknowledged
  monitoring alerts, finished background jobs, expired sessions and OIDC states, delivered
  notification and market-event outbox rows, and the licensed-use meter.
* **The audit trail is left alone.** Its one prune path is dual-controlled (an approved
  ``audit_prune`` privileged change; ``application/audit_retention.py``) and cannot run
  unattended on the demo. Pruning it outside that path would break the hash chain.

After deleting, VACUUM (ANALYZE) runs on the affected tables (plain VACUUM only - never
VACUUM FULL while the server is serving), and the report carries table and database sizes
before and after. A disk guard reads the free space of the database volume and the system
disk; below the threshold (default 20 %) every window is halved down to a floor, and one
monitoring alert (updated, never duplicated) says so on the Runtime page.

Every run writes one audit event with what was removed per table and one structured log line.
``--dry-run`` prints the plan and deletes nothing.

    python scripts/demo/demo_housekeeping.py --dry-run
    python scripts/demo/demo_housekeeping.py

The demo start-up runs it once after the seed and first catch-up, then every six hours
(``scripts/demo/start_public_demo.py``). The host-level clean-up of images, build cache and
container logs is a separate daily cron (``deploy/demo/host_housekeeping.sh``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

#: One housekeeping run at a time ("EGNH"); a manual run never overlaps the scheduled loop.
HOUSEKEEPING_LOCK = 0x45474E48
#: The demo's high-frequency quote/trade horizon is the feed's own; a run removes anything
#: older as a backstop.
FEED_RETENTION_HOURS = 48
#: Batches per statement: bounded so a batch stays inside a small instance's socket timeout
#: and releases its row locks at each commit (the seed's measured 5,000-row batch).
BATCH_ROWS = 5_000
#: The monitoring alert this job owns; updated in place, never duplicated.
DISK_ALERT_FINGERPRINT = "demo.housekeeping.disk_low"
DISK_ALERT_TITLE = "Demo server disk space is low"
DISK_ALERT_TITLE_ZH = "演示服务器磁盘空间不足"

SIMULATED_HOURS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_SIMULATED_HOURS"
PUBLIC_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_PUBLIC_DAYS"
INGESTION_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_INGESTION_DAYS"
RAW_PAGE_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_RAW_PAGE_DAYS"
ALERT_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_ALERT_DAYS"
JOB_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_JOB_DAYS"
SESSION_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_SESSION_DAYS"
OUTBOX_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_OUTBOX_DAYS"
METER_DAYS_ENV = "EUROGAS_NEXUS_DEMO_KEEP_METER_DAYS"
DISK_MIN_FREE_PCT_ENV = "EUROGAS_NEXUS_DEMO_DISK_MIN_FREE_PCT"
DISK_DATABASE_PATH_ENV = "EUROGAS_NEXUS_DEMO_DISK_DATABASE_PATH"
DISK_SYSTEM_PATH_ENV = "EUROGAS_NEXUS_DEMO_DISK_SYSTEM_PATH"

#: The low-disk floors: a halved window never goes below these.
FLOORS = {
    "simulated_hours": 24,
    "public_days": 30,
    "ingestion_days": 7,
    "raw_page_days": 7,
    "alert_days": 14,
    "job_days": 7,
    "session_days": 0,
    "outbox_days": 7,
    "meter_days": 30,
}

#: Table names whose temporal metadata belongs to public-source observations.
PUBLIC_OBSERVATION_TABLES = (
    "market_observations",
    "flow_observations",
    "capacity_observations",
    "storage_observations",
    "storage_inventory_observations",
    "lng_observations",
    "power_observations",
    "fx_observations",
    "interest_rate_observations",
    "national_gas_actual_demand",
    "remit_umm_messages",
    "forecast_observations",
)


def _log(message: str) -> None:
    print(f"[demo-housekeeping] {message}", file=sys.stderr, flush=True)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- settings ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """The operator's windows and the disk guard's paths (all with safe defaults)."""

    simulated_hours: int = FEED_RETENTION_HOURS
    public_days: int = 120
    ingestion_days: int = 14
    raw_page_days: int = 14
    alert_days: int = 30
    job_days: int = 14
    session_days: int = 0
    outbox_days: int = 14
    meter_days: int = 90
    disk_min_free_pct: float = 20.0
    disk_database_path: str = "/var/lib/postgresql/data"
    disk_system_path: str = "/"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        def days(raw: str | None, default: int) -> int:
            text = (raw or "").strip()
            try:
                value = int(text) if text else default
            except ValueError:
                return default
            return max(0, min(value, 3650))

        raw_pct = (env.get(DISK_MIN_FREE_PCT_ENV) or "").strip()
        try:
            pct = float(raw_pct) if raw_pct else 20.0
        except ValueError:
            pct = 20.0
        return cls(
            simulated_hours=days(
                env.get(SIMULATED_HOURS_ENV), FEED_RETENTION_HOURS
            ),
            public_days=days(env.get(PUBLIC_DAYS_ENV), 120),
            ingestion_days=days(env.get(INGESTION_DAYS_ENV), 14),
            raw_page_days=days(env.get(RAW_PAGE_DAYS_ENV), 14),
            alert_days=days(env.get(ALERT_DAYS_ENV), 30),
            job_days=days(env.get(JOB_DAYS_ENV), 14),
            session_days=days(env.get(SESSION_DAYS_ENV), 0),
            outbox_days=days(env.get(OUTBOX_DAYS_ENV), 14),
            meter_days=days(env.get(METER_DAYS_ENV), 90),
            disk_min_free_pct=max(0.0, min(pct, 100.0)),
            disk_database_path=(
                (env.get(DISK_DATABASE_PATH_ENV) or "").strip()
                or "/var/lib/postgresql/data"
            ),
            disk_system_path=(env.get(DISK_SYSTEM_PATH_ENV) or "").strip() or "/",
        )

    def tightened(self) -> Settings:
        """Every window halved, never below its floor (the disk guard's tighter mode)."""

        def half(value: int, key: str) -> int:
            return max(FLOORS[key], value // 2)

        return Settings(
            simulated_hours=half(self.simulated_hours, "simulated_hours"),
            public_days=half(self.public_days, "public_days"),
            ingestion_days=half(self.ingestion_days, "ingestion_days"),
            raw_page_days=half(self.raw_page_days, "raw_page_days"),
            alert_days=half(self.alert_days, "alert_days"),
            job_days=half(self.job_days, "job_days"),
            session_days=half(self.session_days, "session_days"),
            outbox_days=half(self.outbox_days, "outbox_days"),
            meter_days=half(self.meter_days, "meter_days"),
            disk_min_free_pct=self.disk_min_free_pct,
            disk_database_path=self.disk_database_path,
            disk_system_path=self.disk_system_path,
        )

    def windows(self, now: datetime) -> dict[str, timedelta]:
        return {
            "simulated": timedelta(hours=self.simulated_hours),
            "public": timedelta(days=self.public_days),
            "ingestion": timedelta(days=self.ingestion_days),
            "raw_page": timedelta(days=self.raw_page_days),
            "alert": timedelta(days=self.alert_days),
            "job": timedelta(days=self.job_days),
            "session": timedelta(days=self.session_days),
            "outbox": timedelta(days=self.outbox_days),
            "meter": timedelta(days=self.meter_days),
        }

    def window_report(self) -> dict[str, int | float]:
        return {
            "simulated_hours": self.simulated_hours,
            "public_days": self.public_days,
            "ingestion_days": self.ingestion_days,
            "raw_page_days": self.raw_page_days,
            "alert_days": self.alert_days,
            "job_days": self.job_days,
            "session_days": self.session_days,
            "outbox_days": self.outbox_days,
            "meter_days": self.meter_days,
        }


# --- disk guard -------------------------------------------------------------------------


@dataclass(frozen=True)
class DiskPath:
    label: str
    path: str
    visible: bool
    total_bytes: int | None = None
    free_bytes: int | None = None
    free_pct: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "path": self.path,
            "visible": self.visible,
            "total_bytes": self.total_bytes,
            "free_bytes": self.free_bytes,
            "free_pct": self.free_pct,
            "error": self.error,
        }


@dataclass(frozen=True)
class DiskState:
    paths: tuple[DiskPath, ...]
    threshold_pct: float
    low: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "paths": [path.as_dict() for path in self.paths],
            "threshold_pct": self.threshold_pct,
            "low": self.low,
        }


def read_disk_state(
    settings: Settings, reader: Callable[[str], Any] | None = None
) -> DiskState:
    """Free space of the database volume and the system disk; a missing path is "not visible"."""

    usage = shutil.disk_usage if reader is None else reader
    paths: list[DiskPath] = []
    for label, path in (
        ("database", settings.disk_database_path),
        ("system", settings.disk_system_path),
    ):
        if not path:
            paths.append(DiskPath(label, path, False, error="no path configured"))
            continue
        try:
            stat = usage(path)
        except (OSError, ValueError, TypeError) as exc:
            paths.append(DiskPath(label, path, False, error=exc.__class__.__name__))
            continue
        total = int(getattr(stat, "total", 0) or 0)
        free = int(getattr(stat, "free", 0) or 0)
        if total <= 0:
            paths.append(DiskPath(label, path, False, error="no total size"))
            continue
        paths.append(
            DiskPath(
                label,
                path,
                True,
                total_bytes=total,
                free_bytes=free,
                free_pct=round(free * 100.0 / total, 2),
            )
        )
    visible = [path for path in paths if path.visible and path.free_pct is not None]
    low = any(path.free_pct is not None and path.free_pct < settings.disk_min_free_pct
              for path in visible)
    return DiskState(tuple(paths), settings.disk_min_free_pct, low)


# --- rules ------------------------------------------------------------------------------


@dataclass
class Rule:
    """One scoped delete (or update) with the window that decides its cutoff."""

    group: str
    table: str
    model: Any
    condition: Any
    window: str
    reason: str
    action: str = "delete"
    values: dict[str, Any] | None = None
    window_key: str = "public"

    def as_dict(self, cutoff: datetime) -> dict[str, Any]:
        return {
            "group": self.group,
            "table": self.table,
            "window": self.window,
            "cutoff_utc": cutoff.isoformat(),
            "rule": self.reason,
            "action": self.action,
        }


def _simulated(column: Any) -> Any:
    """A simulated source family: ``DEMO_Sim``, ``EEX_Sim``, ``ETRM_Sim``, ..."""

    return column.like("%\\_Sim", escape="\\")


def _not_simulated(column: Any) -> Any:
    return ~_simulated(column)


def _public_rules(now: datetime, windows: Mapping[str, timedelta]) -> list[Rule]:
    """Public-source observations, scoped to real sources only (simulated history stays)."""

    from sqlalchemy import and_

    from eurogas_nexus.db.models import (
        CapacityObservationRecord,
        FlowObservationRecord,
        FxObservationRecord,
        InterestRateObservationRecord,
        LngObservationRecord,
        MarketObservationRecord,
        NationalGasActualDemandRecord,
        NewsItemRecord,
        ObservationRevisionRecord,
        ObservationTemporalMetadataRecord,
        PowerObservationRecord,
        RemitUmmRecord,
        StorageInventoryObservationRecord,
        StorageObservationRecord,
    )
    from eurogas_nexus.db.models.research import ForecastObservationRecord

    cutoff = now - windows["public"]
    label = f"public {windows['public'].days} days"

    def public(model: Any, column: str) -> Any:
        field = getattr(model, column)
        condition = field < cutoff
        if hasattr(model, "source_system"):
            condition = and_(condition, _not_simulated(model.source_system))
        return condition

    rows = [
        (MarketObservationRecord, "observed_at_utc"),
        (FlowObservationRecord, "observed_at_utc"),
        (CapacityObservationRecord, "observed_at_utc"),
        (StorageObservationRecord, "observed_at_utc"),
        (StorageInventoryObservationRecord, "observed_at_utc"),
        (LngObservationRecord, "observed_at_utc"),
        (PowerObservationRecord, "ingested_at_utc"),
        (FxObservationRecord, "observed_at_utc"),
        (InterestRateObservationRecord, "ingested_at_utc"),
        (NationalGasActualDemandRecord, "received_at_utc"),
        (RemitUmmRecord, "ingested_at_utc"),
        (NewsItemRecord, "retrieved_at_utc"),
        (ForecastObservationRecord, "ingested_at_utc"),
        (ObservationRevisionRecord, "recorded_at_utc"),
    ]
    rules = [
        Rule(
            "public",
            model.__tablename__,
            model,
            public(model, column),
            label,
            f"non-simulated rows older than {window_label(windows['public'])}",
            window_key="public",
        )
        for model, column in rows
    ]
    rules.append(
        Rule(
            "public",
            ObservationTemporalMetadataRecord.__tablename__,
            ObservationTemporalMetadataRecord,
            and_(
                ObservationTemporalMetadataRecord.ingested_at_utc < cutoff,
                ObservationTemporalMetadataRecord.observation_table.in_(
                    PUBLIC_OBSERVATION_TABLES
                ),
            ),
            label,
            "temporal metadata of public-source observations older than the window",
            window_key="public",
        )
    )
    return rules


def window_label(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds % 86400 == 0:
        return f"{seconds // 86400} days"
    return f"{seconds // 3600} hours"


def _simulated_rules(now: datetime, windows: Mapping[str, timedelta]) -> list[Rule]:
    """The feed's own high-frequency rows, its retention horizon applied as a backstop."""

    from sqlalchemy import and_

    from eurogas_nexus.db.models import (
        GasDayNominationEventRecord,
        IngestionRunRecord,
        MarketQuoteRecord,
        MarketTradeRecord,
        ScreenOrderObservationRecord,
    )

    def feed() -> Any:
        return _feed_module().FEED_SOURCE_ID

    cutoff = now - windows["simulated"]
    label = f"simulated {window_label(windows['simulated'])}"
    return [
        Rule(
            "simulated",
            MarketQuoteRecord.__tablename__,
            MarketQuoteRecord,
            and_(
                MarketQuoteRecord.observed_at_utc < cutoff,
                _simulated(MarketQuoteRecord.source_system),
            ),
            label,
            "simulated quotes older than the feed's retention",
            window_key="simulated",
        ),
        Rule(
            "simulated",
            MarketTradeRecord.__tablename__,
            MarketTradeRecord,
            and_(
                MarketTradeRecord.traded_at_utc < cutoff,
                _simulated(MarketTradeRecord.source_system),
            ),
            label,
            "simulated prints older than the feed's retention",
            window_key="simulated",
        ),
        Rule(
            "simulated",
            IngestionRunRecord.__tablename__,
            IngestionRunRecord,
            and_(
                IngestionRunRecord.started_at_utc < cutoff,
                IngestionRunRecord.source_id == feed(),
            ),
            label,
            "the simulated feed's own status runs",
            window_key="simulated",
        ),
        Rule(
            "simulated",
            ScreenOrderObservationRecord.__tablename__,
            ScreenOrderObservationRecord,
            and_(
                ScreenOrderObservationRecord.observed_at_utc < cutoff,
                ScreenOrderObservationRecord.source_system == "ETRM_Sim",
            ),
            label,
            "simulated booked order observations older than the feed's retention",
            window_key="simulated",
        ),
        Rule(
            "simulated",
            GasDayNominationEventRecord.__tablename__,
            GasDayNominationEventRecord,
            and_(
                GasDayNominationEventRecord.recorded_at_utc < cutoff,
                GasDayNominationEventRecord.source_system == "ETRM_Sim",
            ),
            label,
            "simulated nomination events older than the feed's retention",
            window_key="simulated",
        ),
    ]


def _operational_rules(now: datetime, windows: Mapping[str, timedelta]) -> list[Rule]:
    """Tables that only grow: runs, pages, alerts, jobs, sessions, outboxes and the meter."""

    from sqlalchemy import and_, or_, select

    from eurogas_nexus.db.models import (
        IngestionRunIssueRecord,
        IngestionRunRecord,
        LicensedDataUseRecord,
        MarketEventDeliveryRecord,
        MarketEventRecord,
        MonitoringAlertReaderStateRecord,
        MonitoringAlertRecord,
        NotificationDeliveryRecord,
        NotificationOutboxRecord,
        OidcAuthorizationStateRecord,
        RawPayloadArchiveRecord,
        RawPayloadContentRecord,
        UserSessionRecord,
    )
    from eurogas_nexus.domain.dataops.contracts import IngestionRunStatus
    from eurogas_nexus.domain.dataops.run_status import stored_statuses_for

    rules: list[Rule] = []
    pending = stored_statuses_for(IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING)
    ingestion_cutoff = now - windows["ingestion"]
    rules.append(
        Rule(
            "operations",
            IngestionRunRecord.__tablename__,
            IngestionRunRecord,
            and_(
                IngestionRunRecord.started_at_utc < ingestion_cutoff,
                IngestionRunRecord.status.notin_(pending),
            ),
            f"ingestion {windows['ingestion'].days} days",
            "finished ingestion runs (a queued or running run is never touched)",
            window_key="ingestion",
        )
    )
    rules.append(
        Rule(
            "operations",
            IngestionRunIssueRecord.__tablename__,
            IngestionRunIssueRecord,
            IngestionRunIssueRecord.created_at_utc < ingestion_cutoff,
            f"ingestion {windows['ingestion'].days} days",
            "issues of old ingestion runs",
            window_key="ingestion",
        )
    )

    raw_cutoff = now - windows["raw_page"]
    rules.append(
        Rule(
            "operations",
            RawPayloadContentRecord.__tablename__,
            RawPayloadContentRecord,
            RawPayloadContentRecord.last_received_at_utc < raw_cutoff,
            f"raw pages {windows['raw_page'].days} days",
            "raw page bytes (the demo has no object store; the digest receipt stays)",
            window_key="raw_page",
        )
    )
    rules.append(
        Rule(
            "operations",
            RawPayloadArchiveRecord.__tablename__,
            RawPayloadArchiveRecord,
            and_(
                RawPayloadArchiveRecord.received_at_utc < raw_cutoff,
                or_(
                    RawPayloadArchiveRecord.payload_text.isnot(None),
                    RawPayloadArchiveRecord.payload_json.isnot(None),
                ),
            ),
            f"raw pages {windows['raw_page'].days} days",
            "inline page bytes on old receipts are cleared; the digest row is kept",
            action="update",
            values={"payload_text": None, "payload_json": None},
            window_key="raw_page",
        )
    )

    alert_cutoff = now - windows["alert"]
    closed = MonitoringAlertRecord.status.in_(("acknowledged", "resolved"))
    alert_condition = and_(
        MonitoringAlertRecord.updated_at_utc < alert_cutoff,
        closed,
    )
    rules.append(
        Rule(
            "operations",
            MonitoringAlertReaderStateRecord.__tablename__,
            MonitoringAlertReaderStateRecord,
            MonitoringAlertReaderStateRecord.alert_id.in_(
                select(MonitoringAlertRecord.alert_id).where(alert_condition)
            ),
            f"alerts {windows['alert'].days} days",
            "per-person marks of the alerts about to be removed",
            window_key="alert",
        )
    )
    rules.append(
        Rule(
            "operations",
            MonitoringAlertRecord.__tablename__,
            MonitoringAlertRecord,
            alert_condition,
            f"alerts {windows['alert'].days} days",
            "acknowledged or resolved alerts older than the window (open ones stay)",
            window_key="alert",
        )
    )

    session_cutoff = now - windows["session"]
    rules.append(
        Rule(
            "operations",
            UserSessionRecord.__tablename__,
            UserSessionRecord,
            or_(
                UserSessionRecord.expires_at_utc < now,
                and_(
                    UserSessionRecord.revoked_at_utc.isnot(None),
                    UserSessionRecord.revoked_at_utc < session_cutoff,
                ),
            ),
            f"sessions {windows['session'].days} days",
            "expired or revoked sessions",
            window_key="session",
        )
    )
    rules.append(
        Rule(
            "operations",
            OidcAuthorizationStateRecord.__tablename__,
            OidcAuthorizationStateRecord,
            or_(
                OidcAuthorizationStateRecord.expires_at_utc < now,
                and_(
                    OidcAuthorizationStateRecord.consumed_at_utc.isnot(None),
                    OidcAuthorizationStateRecord.consumed_at_utc < session_cutoff,
                ),
            ),
            f"sessions {windows['session'].days} days",
            "expired or consumed OIDC login states",
            window_key="session",
        )
    )

    outbox_cutoff = now - windows["outbox"]
    rules.append(
        Rule(
            "operations",
            NotificationDeliveryRecord.__tablename__,
            NotificationDeliveryRecord,
            NotificationDeliveryRecord.attempted_at_utc < outbox_cutoff,
            f"outbox {windows['outbox'].days} days",
            "notification delivery attempts",
            window_key="outbox",
        )
    )
    rules.append(
        Rule(
            "operations",
            NotificationOutboxRecord.__tablename__,
            NotificationOutboxRecord,
            and_(
                NotificationOutboxRecord.dispatched_at_utc.isnot(None),
                NotificationOutboxRecord.created_at_utc < outbox_cutoff,
            ),
            f"outbox {windows['outbox'].days} days",
            "notification outbox rows already dispatched",
            window_key="outbox",
        )
    )
    rules.append(
        Rule(
            "operations",
            MarketEventDeliveryRecord.__tablename__,
            MarketEventDeliveryRecord,
            and_(
                MarketEventDeliveryRecord.status.in_(("processed", "superseded", "dead")),
                MarketEventDeliveryRecord.available_at_utc < outbox_cutoff,
            ),
            f"outbox {windows['outbox'].days} days",
            "market-event deliveries that reached a terminal state",
            window_key="outbox",
        )
    )
    rules.append(
        Rule(
            "operations",
            MarketEventRecord.__tablename__,
            MarketEventRecord,
            and_(
                MarketEventRecord.ingested_at_utc < outbox_cutoff,
                ~MarketEventRecord.seq.in_(
                    select(MarketEventDeliveryRecord.event_seq)
                ),
            ),
            f"outbox {windows['outbox'].days} days",
            "market events no undelivered consumer still needs",
            window_key="outbox",
        )
    )

    meter_cutoff = (now - windows["meter"]).date()
    rules.append(
        Rule(
            "operations",
            LicensedDataUseRecord.__tablename__,
            LicensedDataUseRecord,
            LicensedDataUseRecord.usage_day < meter_cutoff,
            f"meter {windows['meter'].days} days",
            "licensed-use meter days older than the vendor-declaration window",
            window_key="meter",
        )
    )
    rules.append(
        Rule(
            "operations",
            "job_records",
            None,
            None,
            f"jobs {windows['job'].days} days",
            "terminal job records (active work is never touched; the product's prune path)",
            action="prune_jobs",
            values={"now_utc": now, "retention_days": windows["job"].days},
            window_key="job",
        )
    )
    return rules


# --- deleting ---------------------------------------------------------------------------


_SEED_MODULE: Any = None
_FEED_MODULE: Any = None


def _seed_module():
    """The demo seed's shared batched-delete helper and its advisory lock."""

    global _SEED_MODULE
    if _SEED_MODULE is None:
        path = Path(__file__).with_name("seed_demo_desk.py")
        spec = importlib.util.spec_from_file_location("demo_housekeeping_seed", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _SEED_MODULE = module
    return _SEED_MODULE


def _feed_module():
    global _FEED_MODULE
    if _FEED_MODULE is None:
        path = Path(__file__).with_name("exchange_feed.py")
        spec = importlib.util.spec_from_file_location("demo_housekeeping_feed", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _FEED_MODULE = module
    return _FEED_MODULE


def _delete_rule(session, rule: Rule) -> int:
    """Remove (or update) the rows of one rule, in bounded committed batches."""

    if rule.action == "prune_jobs":
        from eurogas_nexus.application.job_retention import prune_expired_job_records

        values = rule.values or {}
        result = prune_expired_job_records(
            session,
            retention_days=int(values["retention_days"]),
            now_utc=values["now_utc"],
            dry_run=False,
        )
        session.commit()
        return int(result["jobs_deleted"])
    if rule.action == "update":
        return _update_in_batches(
            session, rule.model, rule.condition, rule.values or {}, log=_log
        )
    seed = _seed_module()
    table = rule.model.__table__
    if rule.action == "update":
        return _update_in_batches(
            session, rule.model, rule.condition, rule.values or {}, log=_log
        )
    if (
        session.get_bind().dialect.name != "postgresql"
        and len(table.primary_key.columns) != 1
    ):
        # A composite-key table has no single-column range to walk on SQLite; the rows are
        # a meter or a delivery record, small next to the quote tables.
        removed = session.query(rule.model).filter(rule.condition).delete(
            synchronize_session=False
        )
        session.commit()
        return removed
    return seed._delete_in_batches(session, rule.model, rule.condition, log=_log)


def _update_in_batches(session, model, condition, values, *, log) -> int:
    """Set ``values`` on the rows matching ``condition``, in bounded committed batches."""

    from sqlalchemy import and_, literal_column, select

    table = model.__table__
    started = time.monotonic()
    total = batches = 0
    if session.get_bind().dialect.name == "postgresql":
        while True:
            batch = (
                select(literal_column("ctid"))
                .select_from(table)
                .where(condition)
                .limit(BATCH_ROWS)
            )
            changed = session.execute(
                table.update().where(literal_column("ctid").in_(batch)).values(**values)
            ).rowcount
            session.commit()
            if changed <= 0:
                break
            total += changed
            batches += 1
            if changed < BATCH_ROWS:
                break
    else:
        keys = list(table.primary_key.columns)
        if len(keys) != 1:
            changed = session.execute(
                table.update().where(condition).values(**values)
            ).rowcount
            session.commit()
            return changed
        key = keys[0]
        after = None
        while True:
            filters = [condition] if after is None else [condition, key > after]
            found = list(
                session.execute(
                    select(key).select_from(table).where(and_(*filters))
                    .order_by(key).limit(BATCH_ROWS)
                ).scalars()
            )
            if not found:
                break
            last = found[-1]
            filters = [condition, key <= last] if after is None else [
                condition, key > after, key <= last
            ]
            changed = session.execute(
                table.update().where(and_(*filters)).values(**values)
            ).rowcount
            session.commit()
            total += changed
            batches += 1
            after = last
            if len(found) < BATCH_ROWS:
                break
    if total:
        log(f"{table.name}: {total:,} rows updated in {batches} batches "
            f"({time.monotonic() - started:.1f}s)")
    return total


def _count_rule(session, rule: Rule) -> int:
    if rule.action == "prune_jobs":
        from eurogas_nexus.application.job_retention import prune_expired_job_records

        values = rule.values or {}
        result = prune_expired_job_records(
            session,
            retention_days=int(values["retention_days"]),
            now_utc=values["now_utc"],
            dry_run=True,
        )
        return int(result["jobs_eligible"])
    return session.query(rule.model).filter(rule.condition).count()


# --- sizes, vacuum ----------------------------------------------------------------------


def _table_sizes(session, tables: list[str]) -> dict[str, int | None]:
    if session.get_bind().dialect.name != "postgresql":
        return {table: None for table in tables}
    from sqlalchemy import text

    sizes: dict[str, int | None] = {}
    for table in tables:
        value = session.execute(
            text("SELECT pg_total_relation_size(to_regclass(:table))"), {"table": table}
        ).scalar()
        sizes[table] = int(value) if value is not None else None
    return sizes


def _database_size(session) -> int | None:
    from sqlalchemy import text

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return int(session.execute(text("SELECT pg_database_size(current_database())")).scalar())
    if dialect == "sqlite":
        page_count = session.execute(text("PRAGMA page_count")).scalar()
        page_size = session.execute(text("PRAGMA page_size")).scalar()
        if page_count is None or page_size is None:
            return None
        return int(page_count) * int(page_size)
    return None


def _vacuum_postgres(connection, table: str) -> None:
    """One plain VACUUM (ANALYZE) outside a transaction block.

    SQLAlchemy's connection-level AUTOCOMMIT option is too late once a pooled connection has
    been used (pg8000 then still opens a transaction and PostgreSQL refuses VACUUM). The
    driver's own autocommit flag, set on a rolled-back connection, is the one that works and
    it keeps this connection's TLS and search_path settings.
    """

    connection.rollback()
    driver = connection.connection.driver_connection
    previous = getattr(driver, "autocommit", None)
    cursor = driver.cursor()
    try:
        # A pooled connection can still be inside a driver-level transaction that
        # SQLAlchemy's rollback did not reach; ROLLBACK also clears an aborted transaction.
        try:
            cursor.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - no transaction to roll back is fine
            pass
        if previous is not None:
            driver.autocommit = True
        cursor.execute(f'VACUUM (ANALYZE) "{table}"')
    finally:
        cursor.close()
        if previous is not None:
            driver.autocommit = previous


def _vacuum(engine, dialect: str, tables: list[str], errors: list[dict[str, Any]]) -> list[str]:
    """Plain VACUUM (ANALYZE), never VACUUM FULL while the server is serving."""

    done: list[str] = []
    if not tables:
        return done
    if dialect == "postgresql":
        with engine.connect() as connection:
            for table in tables:
                try:
                    _vacuum_postgres(connection, table)
                    done.append(table)
                except Exception as exc:  # noqa: BLE001 - one table never stops the rest
                    errors.append(
                        {"table": table, "action": "vacuum",
                         "error": exc.__class__.__name__, "detail": str(exc)[:200]}
                    )
    elif dialect == "sqlite":
        with engine.connect() as connection:
            for table in tables:
                try:
                    connection.exec_driver_sql(f'ANALYZE "{table}"')
                    done.append(table)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {"table": table, "action": "analyze",
                         "error": exc.__class__.__name__, "detail": str(exc)[:200]}
                    )
            connection.commit()
    return done


# --- the run ----------------------------------------------------------------------------


@contextmanager
def _run_lock(session_factory):
    """At most one housekeeping pass (PostgreSQL advisory lock; a no-op elsewhere)."""

    from sqlalchemy import text

    session = session_factory()
    if session.get_bind().dialect.name != "postgresql":
        try:
            yield True
        finally:
            session.close()
        return
    try:
        acquired = session.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": HOUSEKEEPING_LOCK}
        ).scalar()
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            session.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": HOUSEKEEPING_LOCK}
            )
    finally:
        session.close()


@dataclass
class RunReport:
    run_id: str
    started_at_utc: str
    dry_run: bool
    status: str = "running"
    disk: dict[str, Any] = field(default_factory=dict)
    windows: dict[str, int | float] = field(default_factory=dict)
    plan: list[dict[str, Any]] = field(default_factory=list)
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    sizes: dict[str, Any] = field(default_factory=dict)
    vacuumed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    audit_event_id: str | None = None
    alert: str | None = None
    duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at_utc": self.started_at_utc,
            "dry_run": self.dry_run,
            "status": self.status,
            "disk": self.disk,
            "windows": self.windows,
            "plan": self.plan,
            "tables": self.tables,
            "sizes": self.sizes,
            "vacuumed": self.vacuumed,
            "errors": self.errors,
            "audit_event_id": self.audit_event_id,
            "alert": self.alert,
            "duration_seconds": self.duration_seconds,
        }


def run_housekeeping(
    session_factory,
    *,
    dry_run: bool = False,
    now_utc: datetime | None = None,
    environ: Mapping[str, str] | None = None,
    disk_reader: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """One housekeeping pass; ``dry_run`` counts and prints the plan without deleting."""

    started = time.monotonic()
    now = _as_utc(now_utc or datetime.now(UTC))
    settings = Settings.from_env(environ)
    disk = read_disk_state(settings, disk_reader)
    if disk.low:
        settings = settings.tightened()
    windows = settings.windows(now)
    report = RunReport(
        run_id=f"housekeeping-{uuid.uuid4().hex[:20]}",
        started_at_utc=now.isoformat(),
        dry_run=dry_run,
        disk=disk.as_dict(),
        windows=settings.window_report(),
    )

    rules = [
        *_simulated_rules(now, windows),
        *_public_rules(now, windows),
        *_operational_rules(now, windows),
    ]
    report.plan = [rule.as_dict(now - windows[rule.window_key]) for rule in rules]

    with _run_lock(session_factory) as acquired:
        if not acquired:
            report.status = "skipped_locked"
            report.duration_seconds = round(time.monotonic() - started, 2)
            _log_line(report)
            return report.as_dict()

        unique_tables = sorted({rule.table for rule in rules})
        with session_factory() as session:
            report.sizes["before"] = {
                "database_bytes": _database_size(session),
                "tables": _table_sizes(session, unique_tables),
            }

        if dry_run:
            with session_factory() as session:
                for rule in rules:
                    try:
                        count = _count_rule(session, rule)
                    except Exception as exc:  # noqa: BLE001 - a plan never fails a run
                        report.errors.append(
                            {"table": rule.table, "action": "count",
                             "error": exc.__class__.__name__}
                        )
                        count = None
                    report.tables.setdefault(
                        rule.table,
                        {"group": rule.group, "action": rule.action,
                         "rule": rule.reason, "would_remove": 0},
                    )["would_remove"] += count or 0
        else:
            try:
                _apply_rules(session_factory, rules, report)
            except Exception as exc:  # noqa: BLE001 - the audit and sizes still run
                report.errors.append(
                    {"table": "-", "action": "run", "error": exc.__class__.__name__}
                )
                _log(f"housekeeping rules stopped ({exc.__class__.__name__}); reporting what ran")
            with session_factory() as session:
                engine = getattr(session.get_bind(), "engine", session.get_bind())
                dialect = session.get_bind().dialect.name
            affected = [
                table for table, entry in report.tables.items()
                if entry.get("rows_removed") or entry.get("rows_updated")
            ]
            report.vacuumed = _vacuum(engine, dialect, affected, report.errors)
            with session_factory() as session:
                report.sizes["after"] = {
                    "database_bytes": _database_size(session),
                    "tables": _table_sizes(session, unique_tables),
                }

        report.status = "failed" if report.errors else "ok"

        with session_factory() as session:
            _write_audit(session, report, now=now, settings=settings)
            if not dry_run:
                report.alert = _write_disk_alert(session, disk, now)
            session.commit()

    report.duration_seconds = round(time.monotonic() - started, 2)
    _log_line(report)
    return report.as_dict()


def _apply_rules(session_factory, rules: list[Rule], report: RunReport) -> None:
    """Run the simulated backstop under the seed lock, then the other rules."""

    seed = _seed_module()
    for rule in rules:
        if rule.group == "simulated":
            continue
        _apply_one(session_factory, rule, report)
    simulated = [rule for rule in rules if rule.group == "simulated"]
    if not simulated:
        return
    with session_factory() as lock_session:
        with seed._seed_clear_lock(lock_session):
            for rule in simulated:
                _apply_one(session_factory, rule, report)


def _apply_one(session_factory, rule: Rule, report: RunReport) -> None:
    with session_factory() as session:
        try:
            changed = _delete_rule(session, rule)
        except Exception as exc:  # noqa: BLE001 - one rule never stops the others
            session.rollback()
            report.errors.append(
                {"table": rule.table, "action": rule.action,
                 "error": exc.__class__.__name__}
            )
            _log(f"{rule.table}: {rule.action} failed ({exc.__class__.__name__}); continuing")
            return
    entry = report.tables.setdefault(
        rule.table,
        {"group": rule.group, "action": rule.action, "rule": rule.reason},
    )
    key = "rows_updated" if rule.action == "update" else "rows_removed"
    entry[key] = entry.get(key, 0) + changed
    entry["window"] = rule.window


def _write_audit(session, report: RunReport, *, now: datetime, settings: Settings) -> None:
    from eurogas_nexus.db.repositories.audit import record_audit_event

    removed = {
        table: {
            key: entry.get(key)
            for key in ("rows_removed", "rows_updated", "would_remove")
            if entry.get(key)
        }
        for table, entry in report.tables.items()
    }
    event = record_audit_event(
        session,
        event_type="governance.demo",
        principal="demo-housekeeping",
        action="demo.housekeeping",
        resource=f"demo_housekeeping:{report.run_id}",
        outcome="dry_run" if report.dry_run else report.status,
        severity="info" if report.status == "ok" else "warning",
        detail=json.dumps(
            {
                "run_id": report.run_id,
                "tables": removed,
                "tightened": report.disk.get("low", False),
                "errors": report.errors,
            },
            sort_keys=True,
        )[:4000],
        source_system="demo-housekeeping",
        now_utc=now,
        after_summary={
            "windows": settings.window_report(),
            "tables": removed,
            "tightened": bool(report.disk.get("low")),
        },
    )
    report.audit_event_id = event.event_id


def _write_disk_alert(session, disk: DiskState, now: datetime) -> str:
    """One warning alert, updated in place; resolved again when space is back."""

    from eurogas_nexus.db.models import MonitoringAlertRecord
    from eurogas_nexus.db.repositories.monitoring import upsert_monitoring_alert
    from eurogas_nexus.domain.monitoring import MonitoringCandidate

    if not disk.low:
        row = (
            session.query(MonitoringAlertRecord)
            .filter(MonitoringAlertRecord.fingerprint == DISK_ALERT_FINGERPRINT)
            .one_or_none()
        )
        if row is not None and row.status != "resolved":
            row.status = "resolved"
            row.resolved_at_utc = now
            row.updated_at_utc = now
        return "resolved" if row is not None else "not_needed"

    visible = [path for path in disk.paths if path.visible]
    detail = "; ".join(
        f"{path.label} {path.path} {path.free_pct:.1f}% free"
        if path.free_pct is not None
        else f"{path.label} not visible"
        for path in visible
    ) or "no disk path visible"
    message = (
        f"Free space is below {disk.threshold_pct:.0f}% ({detail}). Housekeeping has "
        "tightened its windows. Free space on the demo host (see "
        "deploy/demo/host_housekeeping.sh) or move the demo to a larger disk."
    )
    candidate = MonitoringCandidate(
        fingerprint=DISK_ALERT_FINGERPRINT,
        category="operations",
        alert_type="demo_disk_space",
        severity="warning",
        title_en=DISK_ALERT_TITLE,
        title_zh_cn=DISK_ALERT_TITLE_ZH,
        message_en=message,
        message_zh_cn=message,
        entity_type="deployment",
        entity_id="demo",
        event_time_utc=now,
        evidence_snapshot={"disk": disk.as_dict()},
        source_refs=["demo_housekeeping"],
        simulated=False,
        human_review_required=False,
    )
    upsert_monitoring_alert(session, candidate, now_utc=now)
    return "updated"


def _log_line(report: RunReport) -> None:
    removed = {
        table: entry.get("rows_removed") or entry.get("rows_updated")
        for table, entry in report.tables.items()
        if entry.get("rows_removed") or entry.get("rows_updated")
    }
    print(
        json.dumps(
            {
                "event": "demo.housekeeping",
                "run_id": report.run_id,
                "status": report.status,
                "dry_run": report.dry_run,
                "tightened": bool(report.disk.get("low")),
                "rows": removed,
                "audit_event_id": report.audit_event_id,
                "alert": report.alert,
                "duration_seconds": report.duration_seconds,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


# --- command line -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; delete nothing"
    )
    parser.add_argument("--now", help="clock override, ISO 8601 (tests and rehearsals)")
    args = parser.parse_args(argv)

    from eurogas_nexus.security.local_accounts_policy import demo_profile_active

    if not demo_profile_active(os.environ):
        print(
            "refused: demo housekeeping runs only on the hosted demo server "
            "(EUROGAS_NEXUS_API_PROFILE=demo in a development/test environment); it "
            "removes rows without archiving them and must never run on a customer runtime.",
            file=sys.stderr,
        )
        return 2

    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        print(
            "refused: no runtime database URL is configured "
            "(RUNTIME_STORE_DATABASE_URL or DATABASE_URL).",
            file=sys.stderr,
        )
        return 1
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    report = run_housekeeping(
        get_session_factory(), dry_run=args.dry_run, now_utc=now
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if report["status"] == "skipped_locked":
        return 3
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
