"""Migrate a dedicated test database, provision its UAT login, load public data, then serve.

Startup order: migrations, the test login, published reference data (TSO tariffs,
public route templates, hubs, glossary; nothing simulated), then the data-operations
scheduler as a child process, so the preview fetches the same open sources a real
installation does (ECB FX, SONIA/€STR/SOFR, and EIA, ENTSO-E when their keys are set)
and keeps them current while the service is awake. Sources that need a certification
record (ENTSOG, GIE) stay blocked until an operator records one.
"""

import atexit
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    required = {
        "EUROGAS_NEXUS_MOBILE_PREVIEW": "1",
        "EUROGAS_NEXUS_ENV": "test",
        "EUROGAS_NEXUS_API_PROFILE": "development",
        "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS": "0",
        "EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES": "0",
        "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "0",
    }
    for key, expected in required.items():
        if os.environ.get(key) != expected:
            raise RuntimeError(f"Isolated preview requires {key}={expected}")
    for key in (
        "DATABASE_URL",
        "EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
        "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
    ):
        if not os.environ.get(key, "").strip():
            raise RuntimeError(f"Missing preview configuration: {key}")
    if len(os.environ["EUROGAS_NEXUS_DEV_LOGIN_PASSWORD"]) < 20:
        raise RuntimeError("Use a fresh preview password of at least 20 characters")
    # Render supplies postgresql://; pg8000 is the project's locked driver.
    dsn = os.environ["DATABASE_URL"]
    for prefix in ("postgres://", "postgresql://"):
        if dsn.startswith(prefix):
            dsn = "postgresql+pg8000://" + dsn[len(prefix):]
            break
    os.environ["RUNTIME_STORE_DATABASE_URL"] = dsn
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, "scripts/uat/seed_browser_identity.py"], check=True)
    subprocess.run(
        [sys.executable, "scripts/ops/seed_preview_runtime_data.py", "--public-only"], check=True
    )
    _queue_first_runs()
    scheduler = subprocess.Popen(
        [
            sys.executable,
            "scripts/ops/run_dataops_scheduler.py",
            # ENTSOG refuses to run without an explicit window; the cadence is the
            # scheduler's own default.
            "--entsog-lookback-gas-days",
            "3",
        ]
    )
    atexit.register(scheduler.terminate)
    import uvicorn

    uvicorn.run(
        "apps.api.mobile_preview:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


def _queue_first_runs() -> None:
    """Enable keyed sources whose key is set, and run every enabled source once now.

    A fresh database schedules each source's first run at its next slot, hours away, so
    the preview would show nothing until then. An operator-style run per enabled source
    fills it at startup; the scheduler executes them through the normal gates.
    """

    from datetime import UTC, datetime

    from eurogas_nexus.application.dataops_runtime import request_operator_run, set_source_enabled
    from eurogas_nexus.db.models import IngestionRunRecord, SourceRuntimeStateRecord
    from eurogas_nexus.db.repositories.dataops import reconcile_source_runtime_states
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.domain.dataops.contracts import IngestionTriggerType
    from eurogas_nexus.domain.dataops.registry import source_definitions

    keyed = {"src-entsoe": "ENTSOE_SECURITY_TOKEN", "src-eia": "EIA_API_KEY"}
    with get_session_factory(database_url=resolve_database_url())() as session:
        # A fresh database has no per-source state until the scheduler's first pass.
        reconcile_source_runtime_states(session, source_definitions(), now_utc=datetime.now(UTC))
        for source_id, variable in keyed.items():
            if os.environ.get(variable, "").strip():
                set_source_enabled(session, source_id=source_id, enabled=True)
        session.commit()
        enabled = [
            state.source_id
            for state in session.query(SourceRuntimeStateRecord).filter(
                SourceRuntimeStateRecord.enabled.is_(True)
            )
        ]
        pending = {
            run.source_id
            for run in session.query(IngestionRunRecord).filter(
                IngestionRunRecord.status.in_(("QUEUED", "RUNNING"))
            )
        }
        for source_id in enabled:
            if source_id in pending or not _certified_if_required(session, source_id):
                continue
            request_operator_run(
                session,
                source_id=source_id,
                trigger_type=IngestionTriggerType.MANUAL,
                reason="preview startup: first load",
            )
        session.commit()


#: Families whose ingestion needs a certification record (scripts/ops/ingest_public_sources.py).
_CERTIFIED_FAMILY = {"src-entsog": "ENTSOG", "src-gie": "GIE", "src-eex": "EEX"}


def _certified_if_required(session, source_id: str) -> bool:
    """False for a source that would only be refused for lack of certification."""

    family = _CERTIFIED_FAMILY.get(source_id)
    if family is None:
        return True
    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    record = latest_certification(session, family) or {}
    return certification_gate(
        family, stage=record.get("stage", "unverified"), checks=record.get("checks")
    ).allows_live


if __name__ == "__main__":
    raise SystemExit(main())
