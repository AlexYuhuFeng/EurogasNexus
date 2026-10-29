"""Explicit live ingestion for public/source-keyed data sources.

This script is operator-invoked only. It performs live HTTP reads, writes
normalized rows to PostgreSQL, never prints secrets, and archives the raw
provider payload for lineage (raw -> canonical audit trail).

Fail-closed gates (audit item 4): every live source passes the entitlement
check, and export-restricted sources (ENTSOG, GIE) additionally require a
certification record whose gate allows live; blocked sources are recorded as
failed runs, never silently skipped. An explicitly disabled (or unreadable)
source runtime operation also blocks, and the GIE credential-fetch boundary
refuses an operator-disabled stored credential or disabled source operation
regardless of GIE_API_KEY/GIE_API_KEY_FILE precedence.

ENTSOG and GIE observations append absent natural keys and verify unchanged
keys; semantic revisions are refused until append-only history is available.
ENTSOG reference replacement requires exhausted, nonempty bounded queries.
Exhaustion proves traversal completion only; snapshot consistency is unproven.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.models import (
    CapacityObservationRecord,
    FlowObservationRecord,
    FxObservationRecord,
    IngestionRunRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    EntsogObservationPersistenceError,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRequiresHistoryError,
    replace_reference_snapshot,
    upsert_observation_rows,
    upsert_revision_safe_observation_rows,
)
from eurogas_nexus.db.session import (
    create_session_factory,
    get_engine,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.entsog_ingestion import (
    EntsogIngestionError,
    archive_entsog_pages,
    persist_entsog_observations,
    persist_entsog_reference,
)
from eurogas_nexus.ingestion.entsog_transport import (
    EntsogFetchResult,
    EntsogTransportError,
    fetch_entsog_dataset,
)
from eurogas_nexus.ingestion.entsog_window import EntsogWindowPolicy
from eurogas_nexus.ingestion.gie_transport import (
    GIE_SOURCE_ID,
    GieApiKey,
    GieProduct,
    GieTransportError,
    fetch_gie_product,
    resolve_gie_runtime_api_key,
)
from eurogas_nexus.ingestion.public_sources import (
    ecb_fx_observations_from_xml,
    ecb_market_observations_from_xml,
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)

# Sources that are export-restricted and therefore require certification
# before live ingestion (ECB public reference rates are fully public).
CERTIFICATION_REQUIRED_SOURCES = frozenset({"ENTSOG", "GIE", "GIE-AGSI", "GIE-ALSI"})
# Raw payloads larger than this are not archived (warning only).
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ENTSOG_OPERATIONAL_URL = "https://transparency.entsog.eu/api/v1/operationaldatas"
ENTSOG_CONNECTION_POINTS_URL = "https://transparency.entsog.eu/api/v1/connectionpoints"
ENTSOG_OPERATOR_POINT_DIRECTIONS_URL = (
    "https://transparency.entsog.eu/api/v1/operatorpointdirections"
)
GIE_AGSI_EU_URL = "https://agsi.gie.eu/api"
GIE_ALSI_EU_URL = "https://alsi.gie.eu/api"
GIE_AGSI_PRODUCT = GieProduct.agsi(GIE_AGSI_EU_URL)
GIE_ALSI_PRODUCT = GieProduct.alsi(GIE_ALSI_EU_URL)
ENTSOG_CAPACITY_INDICATORS = (
    "Firm Technical",
    "Firm Booked",
    "Interruptible Booked",
    "Nomination",
)


def main() -> int:
    """    Run public-source ingestion for registered, certified sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=(
            "all",
            "ecb",
            "entsog",
            "entsog-capacity",
            "entsog-reference",
            "gie-agsi",
            "gie-alsi",
        ),
        action="append",
        default=[],
        help="Source to ingest. May be repeated. Default: all.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Bounded record limit per source.")
    parser.add_argument(
        "--entsog-from", help="Explicit ENTSOG observation query date (YYYY-MM-DD)."
    )
    parser.add_argument("--entsog-to", help="Explicit ENTSOG observation query date (YYYY-MM-DD).")
    parser.add_argument("--entsog-lookback-gas-days", type=int)
    parser.add_argument(
        "--entsog-window-anchor", help="Aware rolling run timestamp; frozen across retries."
    )
    parser.add_argument("--entsog-page-size", type=int, default=100)
    parser.add_argument("--entsog-max-pages", type=int, default=50)
    parser.add_argument(
        "--entsog-point-direction",
        action="append",
        default=[],
        metavar="POINT_DIRECTION",
        help=(
            "Explicit ENTSOG operational point direction (repeatable or "
            "comma-separated; each value must end with entry or exit). Applies "
            "only to flow/capacity observations, never topology reference data."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON report.")
    args = parser.parse_args()
    try:
        args.entsog_point_direction = _validate_entsog_point_directions(
            args.entsog_point_direction
        )
    except ValueError as exc:
        parser.error(f"invalid --entsog-point-direction: {exc}")

    database_url = resolve_database_url()
    if not database_url:
        return _emit({"ok": False, "error": "Database URL is missing."}, as_json=args.json)

    selected = set(args.source or ["all"])
    if "all" in selected:
        selected = {
            "ecb",
            "entsog",
            "entsog-capacity",
            "entsog-reference",
            "gie-agsi",
            "gie-alsi",
        }

    engine = None
    session_factory = None
    started = datetime.now(UTC)
    if args.entsog_lookback_gas_days is not None and args.entsog_window_anchor is None:
        args.entsog_window_anchor = started.isoformat()
    report: dict[str, Any] = {
        "ok": False,
        "redacted_database_url": redact_database_url(database_url),
        "sources": {},
        "warnings": [],
        "failures": [],
    }
    try:
        engine = get_engine(database_url)
        session_factory = create_session_factory(engine)
        with session_factory() as gate_session:
            gate_families = (
                ("ECB", {"ecb"}),
                ("ENTSOG", {"entsog", "entsog-capacity", "entsog-reference"}),
                ("GIE", {"gie-agsi", "gie-alsi"}),
            )
            for family, names in gate_families:
                if not selected & names:
                    continue
                blockers = _gate_blockers(gate_session, family)
                if blockers:
                    _record_run(
                        gate_session,
                        family,
                        "failed",
                        started,
                        0,
                        "gate:" + ",".join(blockers),
                    )
                    report["warnings"].append(
                        f"{family} live ingestion blocked (fail-closed): "
                        + ",".join(blockers)
                    )
                    selected -= names
            gate_session.commit()
        gie_key: str | None = None
        if selected & {"gie-agsi", "gie-alsi"}:
            failure_code = "gie_credential_missing"
            try:
                resolved_key = _resolve_gie_api_key(session_factory)
            except GieTransportError as exc:
                resolved_key = None
                failure_code = exc.code
                report["failures"].append({"source": "GIE", "code": exc.code})
                report["warnings"].append(
                    f"GIE credential configuration failed ({exc.code}); AGSI/ALSI were "
                    "not fetched and no synthetic data was substituted."
                )
            if resolved_key is None:
                if failure_code == "gie_credential_missing":
                    report["failures"].append({"source": "GIE", "code": failure_code})
                    report["warnings"].append(
                        "GIE key missing; AGSI/ALSI ingestion failed explicitly."
                    )
                with session_factory() as failure_session:
                    for blocked_name in ("GIE-AGSI", "GIE-ALSI"):
                        _record_run(
                            failure_session,
                            blocked_name,
                            "failed",
                            started,
                            0,
                            f"credential:{failure_code}",
                        )
                    failure_session.commit()
                selected -= {"gie-agsi", "gie-alsi"}
            else:
                gie_key = resolved_key.value

        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "EurogasNexus/0.5 preview public-source-ingestion"},
        ) as client:
            with session_factory() as session:
                if "ecb" in selected:
                    xml_text = _fetch_text(client, ECB_DAILY_URL)
                    _archive_raw_payload(
                        session,
                        source_system="ECB",
                        dataset="fx-reference-rates",
                        source_reference="ecb-eurofxref-daily",
                        payload_text=xml_text,
                        record_count=0,
                        received_at=started,
                    )
                    rows = ecb_market_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    fx_rows = ecb_fx_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    if not rows and not fx_rows:
                        _record_run(session, "ECB", "failed", started, 0, "empty_response")
                        report["warnings"].append("ECB returned no observations.")
                    else:
                        run_id = _new_run_id("ECB")
                        rows = _stamp_lineage(
                            rows, run_id=run_id, adapter_version="public-source-ingestor/1"
                        )
                        fx_rows = _stamp_lineage(
                            fx_rows, run_id=run_id, adapter_version="public-source-ingestor/1"
                        )
                        upsert_observation_rows(session, MarketObservationRecord, rows)
                        upsert_observation_rows(session, FxObservationRecord, fx_rows)
                        _record_run(
                            session,
                            "ECB",
                            "succeeded",
                            started,
                            len(rows) + len(fx_rows),
                            "ecb-eurofxref-daily",
                            run_id=run_id,
                        )
                        report["sources"]["ECB"] = {
                            "records": len(rows) + len(fx_rows),
                            "dataset": "fx-reference-rates",
                        }

                for entsog_route in ("entsog-reference", "entsog", "entsog-capacity"):
                    if entsog_route in selected:
                        _ingest_entsog_source(
                            client, session, route=entsog_route, args=args,
                            started=started, report=report,
                            point_directions=args.entsog_point_direction,
                        )

                for gie_route, gie_product in (
                    ("gie-agsi", GIE_AGSI_PRODUCT),
                    ("gie-alsi", GIE_ALSI_PRODUCT),
                ):
                    if gie_route not in selected:
                        continue
                    source_name = f"GIE-{gie_product.product}"
                    try:
                        gie_result = fetch_gie_product(
                            client,
                            product=gie_product,
                            api_key=gie_key or "",
                            max_records=args.limit,
                        )
                    except GieTransportError as exc:
                        # Explicit failure: a missing credential, a 401/403/429, a
                        # timeout, an empty/malformed/truncated/mismatched response
                        # or an inconsistent page sequence. Synthetic data is never
                        # substituted.
                        _record_run(
                            session,
                            source_name,
                            "failed",
                            started,
                            0,
                            f"transport:{exc.code}",
                        )
                        report["failures"].append(
                            {"source": source_name, "code": exc.code}
                        )
                        report["warnings"].append(
                            f"{source_name} fetch failed explicitly ({exc.code}); "
                            "no synthetic data was substituted."
                        )
                        continue

                    model = (
                        StorageObservationRecord
                        if gie_product.product == "AGSI"
                        else LngObservationRecord
                    )
                    report["sources"][source_name] = {
                        "records": 0,
                        "dataset": gie_product.product,
                        "pages_fetched": len(gie_result.pages),
                        "provider_last_page": gie_result.provider_last_page,
                        "page_size": gie_result.page_size,
                        "pages_allowed": gie_result.pages_allowed,
                        "record_capacity": gie_result.record_capacity,
                        "operator_record_budget": gie_result.budget_records,
                        "complete": gie_result.complete,
                        "stop_reason": gie_result.stop_reason,
                        "partial_reason": gie_result.partial_reason,
                    }
                    if not gie_result.complete:
                        report["warnings"].append(
                            f"{source_name} fetched {len(gie_result.pages)} of "
                            f"{gie_result.provider_last_page} provider pages within the "
                            f"operator budget ({gie_result.budget_records} records, "
                            f"capacity {gie_result.record_capacity}); this is an honest "
                            "bounded partial result, not full history."
                        )

                    persist_outcome = _persist_gie_product(
                        session,
                        product=gie_product,
                        source_name=source_name,
                        gie_result=gie_result,
                        model=model,
                        started=started,
                    )
                    report["sources"][source_name].update(persist_outcome["counts"])
                    if persist_outcome["failure"] is not None:
                        report["failures"].append(persist_outcome["failure"])
                        report["warnings"].append(persist_outcome["warning"])

                session.commit()

        report["ok"] = not report["failures"]
        return _emit(report, as_json=args.json)
    except (httpx.HTTPError, SQLAlchemyError, ValueError, RuntimeError) as exc:
        report["error"] = exc.__class__.__name__
        if session_factory is not None:
            failed_sources = set()
            for source in selected:
                if source == "ecb":
                    failed_sources.add("ECB")
                elif source.startswith("entsog"):
                    failed_sources.add("ENTSOG")
                elif source.startswith("gie"):
                    failed_sources.add("GIE")
            try:
                with session_factory() as session:
                    for source_name in failed_sources:
                        _record_run(
                            session,
                            source_name,
                            "failed",
                            started,
                            0,
                            f"public-source-{exc.__class__.__name__}",
                        )
                    session.commit()
            except SQLAlchemyError:
                pass
        return _emit(report, as_json=args.json)
    finally:
        if engine is not None:
            engine.dispose()


def _fetch_text(client: httpx.Client, url: str) -> str:
    try:
        response = _get_with_retry(client, url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        if url != ECB_DAILY_URL or os.name != "nt":
            raise
        return _fetch_text_with_powershell(url)


def _fetch_text_with_powershell(url: str) -> str:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$ProgressPreference='SilentlyContinue'; "
                f"(Invoke-WebRequest -Uri '{url}' -UseBasicParsing -TimeoutSec 30).Content"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _fetch_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = _get_with_retry(client, url, params=params, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Provider response was not a JSON object.")
    return payload


def _gate_blockers(session, source_system: str) -> list[str]:
    """Return fail-closed gate blockers for a live source (audit item 4).

    Entitlement is checked for every source; export-restricted sources
    (ENTSOG, GIE) additionally require a certification record whose gate
    allows live ingestion. An explicit operator disable of the source's runtime
    operation also blocks, and an unreadable runtime state is never treated as a
    confirmed permit. Any blocker means the source must not be fetched.
    """

    from eurogas_nexus.governance.entitlement import (
        KNOWN_ENTITLED_SYSTEMS_V1,
        entitlement_check,
    )

    blockers: list[str] = []
    decision = entitlement_check(
        source_system,
        known_entitled_systems=KNOWN_ENTITLED_SYSTEMS_V1,
    )
    if not decision.granted:
        blockers.append(f"entitlement:{decision.scope.value}")
        return blockers

    blockers.extend(_source_runtime_blockers(session, source_system))

    if source_system not in CERTIFICATION_REQUIRED_SOURCES:
        return blockers

    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    certification = latest_certification(session, source_system)
    gate = certification_gate(
        source_system,
        stage=(certification or {}).get("stage", "unverified"),
        checks=(certification or {}).get("checks"),
    )
    if not gate.allows_live:
        blockers.append(f"certification:{gate.reason}")
    return blockers


#: Registry id of the runtime operation that owns each fail-closed gate family.
SOURCE_RUNTIME_ID_BY_FAMILY = {
    "ECB": "src-ecb",
    "ENTSOG": "src-entsog",
    "GIE": GIE_SOURCE_ID,
}


def _source_runtime_blockers(session, source_system: str) -> list[str]:
    """Return the fail-closed operator runtime state for one source family.

    An explicit operator disable blocks the live entry. An unreadable runtime
    state is also blocked -- with its own code -- because an unknown state is not
    a confirmed permit. An absent state row is *no override* and does not block.
    """

    source_id = SOURCE_RUNTIME_ID_BY_FAMILY.get(source_system)
    if source_id is None:
        return []
    try:
        from eurogas_nexus.db.models import SourceRuntimeStateRecord

        row = (
            session.query(SourceRuntimeStateRecord)
            .filter(SourceRuntimeStateRecord.source_id == source_id)
            .one_or_none()
        )
    except Exception:  # noqa: BLE001 - an unreadable state must not read as consent
        return ["source_state_unreadable"]
    if row is None:
        return []
    return [] if bool(row.enabled) else ["source_operation_disabled"]


def _archive_raw_payload(
    session,
    *,
    source_system: str,
    dataset: str,
    source_reference: str,
    payload_text: str | None = None,
    payload_json: dict | None = None,
    record_count: int = 0,
    received_at: datetime,
) -> dict[str, str] | None:
    """Archive one raw provider payload for raw -> canonical lineage.

    Oversized payloads are skipped with a printed warning (never truncated), and
    an empty payload is not archived at all; both cases return ``None``. A
    successful archive returns its exact safe identity (``archive_id`` and
    ``payload_sha256``) so a caller can stamp the precise archive link on the
    normalized rows it writes. The identity is never provider content.
    """

    from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload

    if payload_text is not None:
        serialized = payload_text.encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        size = len(serialized)
    elif payload_json is not None:
        serialized = json.dumps(payload_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        size = len(serialized)
    else:
        return None
    if size > MAX_ARCHIVE_BYTES:
        print(
            f"raw payload archive skipped (>{MAX_ARCHIVE_BYTES} bytes): "
            f"{source_system}/{dataset}"
        )
        return None
    archive_id = f"raw-{uuid.uuid4().hex[:20]}"
    archive_raw_payload(
        session,
        archive_id=archive_id,
        source_system=source_system,
        dataset=dataset,
        source_reference=source_reference,
        payload_text=payload_text,
        payload_json=payload_json,
        payload_sha256=digest,
        record_count=record_count,
        received_at_utc=received_at,
    )
    return {"archive_id": archive_id, "payload_sha256": digest}


def _get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET with backoff retry on transport errors AND 429/5xx responses.

    ``Retry-After`` (seconds or HTTP-date) is honored when present; otherwise
    the backoff is ``1.5 * (attempt + 1)`` seconds.
    """

    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code not in {429, 500, 502, 503, 504}:
            return response
        if attempt == attempts - 1:
            return response
        time.sleep(_retry_delay_seconds(response, attempt))
    assert last_error is not None
    raise last_error


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    """Return the retry delay honoring ``Retry-After`` when available."""

    retry_after = response.headers.get("retry-after", "").strip()
    if retry_after.isdigit():
        return min(float(retry_after), 30.0)
    if retry_after:
        try:
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(retry_after)
            if target is not None:
                delay = (target - datetime.now(UTC)).total_seconds()
                if delay > 0:
                    return min(delay, 30.0)
        except (TypeError, ValueError):
            pass
    return 1.5 * (attempt + 1)


def _resolve_gie_api_key(session_factory) -> GieApiKey | None:
    """Resolve the GIE credential with the operator state enforced at fetch time.

    Precedence is deterministic and owned by the transport resolver: env, then
    secret file, then encrypted store. The same runtime path also reads the
    stored credential status and the GIE source runtime state through
    :func:`resolve_gie_runtime_api_key`, so an operator-disabled stored credential
    or an explicitly disabled source operation cannot be silently re-enabled by
    ``GIE_API_KEY``/``GIE_API_KEY_FILE``. A configured but unreadable
    ``GIE_API_KEY_FILE`` raises rather than falling through to another source, and
    an unreadable operator state fails closed with a stable code instead of being
    reported as a confirmed permit.
    """

    return resolve_gie_runtime_api_key(session_factory=session_factory)


def _resolve_gie_key(session_factory) -> str | None:
    """Backward-compatible accessor returning only the resolved key value."""

    resolved = _resolve_gie_api_key(session_factory)
    return resolved.value if resolved is not None else None


ENTSOG_POINT_DIRECTION_MAX_COUNT = 64
ENTSOG_POINT_DIRECTION_MAX_CHARS = 8192
_ENTSOG_POINT_DIRECTION_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz0123456789._-"
)


def _validate_entsog_point_directions(values) -> tuple[str, ...]:
    """Return the explicit, canonical ENTSOG operational point scope.

    Values are caller-declared provider identities; nothing is inferred or
    defaulted. A value may contain a comma-separated composite. Canonicalisation
    lowercases, strips, deduplicates and sorts so the same declaration always
    produces the same query. Validation happens before database/HTTP side
    effects in ``main``.
    """

    if values is None:
        return ()
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = tuple(values)
    if not raw_values:
        return ()
    if not all(isinstance(value, str) for value in raw_values):
        raise ValueError("point directions must be text values")
    if sum(len(value) for value in raw_values) > ENTSOG_POINT_DIRECTION_MAX_CHARS:
        raise ValueError(
            f"point directions exceed {ENTSOG_POINT_DIRECTION_MAX_CHARS} characters"
        )
    tokens: list[str] = []
    for value in raw_values:
        if not value.isascii():
            raise ValueError("point directions must be ASCII")
        for part in value.split(","):
            token = part.strip().lower()
            if not token:
                raise ValueError("point directions must not be blank")
            if token.endswith("entry"):
                suffix = "entry"
            elif token.endswith("exit"):
                suffix = "exit"
            else:
                raise ValueError(
                    f"point direction {token!r} must end with 'entry' or 'exit'"
                )
            prefix = token[: -len(suffix)]
            if not prefix or not prefix[0].isalnum():
                raise ValueError(
                    f"point direction {token!r} has no provider identity prefix"
                )
            if "www." in token or "://" in token:
                raise ValueError(f"point direction {token!r} must not be a URL")
            if any(char not in _ENTSOG_POINT_DIRECTION_CHARS for char in token):
                raise ValueError(
                    f"point direction {token!r} contains a control or unsupported character"
                )
            tokens.append(token)
    canonical = tuple(sorted(set(tokens)))
    if len(canonical) > ENTSOG_POINT_DIRECTION_MAX_COUNT:
        raise ValueError(
            f"at most {ENTSOG_POINT_DIRECTION_MAX_COUNT} point directions are allowed"
        )
    if len(",".join(canonical)) > ENTSOG_POINT_DIRECTION_MAX_CHARS:
        raise ValueError(
            f"point directions exceed {ENTSOG_POINT_DIRECTION_MAX_CHARS} characters"
        )
    return canonical


def _ingest_entsog_source(
    client,
    session,
    *,
    route: str,
    args,
    started: datetime,
    report: dict[str, Any],
    point_directions: tuple[str, ...] | None = None,
) -> None:
    """Execute one ENTSOG route while keeping other source transactions usable."""
    if point_directions is None:
        point_directions = getattr(args, "entsog_point_direction", ())
    point_directions = _validate_entsog_point_directions(point_directions)
    point_scope = ",".join(point_directions)
    source_name = {
        "entsog": "ENTSOG",
        "entsog-capacity": "ENTSOG-capacity",
        "entsog-reference": "ENTSOG-reference",
    }[route]
    run_id = _new_run_id(source_name)
    results: list[EntsogFetchResult] = []
    persistence_started = False
    selected_window = None
    detail: dict[str, Any] = {
        "records": 0,
        "dataset": route,
        "complete": False,
        "snapshot_consistent": False,
    }
    report["sources"][source_name] = detail
    try:
        if route == "entsog-reference":
            queries = (
                ("connectionpoints", {"extended": "1"}),
                ("operatorpointdirections", {"hasData": "1"}),
            )
        else:
            policy = EntsogWindowPolicy(
                args.entsog_from, args.entsog_to,
                getattr(args, "entsog_lookback_gas_days", None),
            )
            selected_window = policy.select(getattr(args, "entsog_window_anchor", None))
            detail["window"] = selected_window.metadata()
            if point_scope:
                detail["point_direction"] = point_scope
                detail["point_directions"] = list(point_directions)
            window = {"from": selected_window.from_date, "to": selected_window.to_date}
            indicators = ("Physical Flow",) if route == "entsog" else ENTSOG_CAPACITY_INDICATORS
            queries = tuple(
                (
                    "operationaldatas",
                    {
                        **window,
                        "indicator": indicator,
                        **({"pointDirection": point_scope} if point_scope else {}),
                    },
                )
                for indicator in indicators
            )
        for dataset, filters in queries:
            results.append(
                fetch_entsog_dataset(
                    client,
                    dataset,
                    filters=filters,
                    max_records=args.limit,
                    page_size=args.entsog_page_size,
                    max_pages=args.entsog_max_pages,
                )
            )
        detail.update(
            {
                "complete": all(result.complete for result in results),
                "queries": [
                    {
                        "reference": result.source_reference,
                        "received_at_utc": result.received_at_utc.isoformat(),
                        "received_records": result.record_count,
                        "complete": result.complete,
                        "stop_reason": result.stop_reason,
                    }
                    for result in results
                ],
                "pages_fetched": sum(len(result.pages) for result in results),
                "received_records": sum(result.record_count for result in results),
            }
        )
        persistence_started = True
        if route == "entsog-reference":
            counts = persist_entsog_reference(
                session,
                results=results,
                run_id=run_id,
                replace_network=_replace_reference_network,
            )
        else:
            counts = persist_entsog_observations(
                session,
                results=results,
                run_id=run_id,
                model=FlowObservationRecord if route == "entsog" else CapacityObservationRecord,
            )
        detail.update(counts)
        warnings = (
            not detail["complete"]
            or bool(counts.get("skipped_records"))
            or bool(counts.get("skipped_tables"))
            or bool(selected_window and selected_window.rolling)
        )
        status = "SUCCEEDED_WITH_WARNINGS" if warnings else "succeeded"
        detail["status"] = status
        _record_run(
            session,
            source_name,
            status,
            started,
            counts["records"],
            " | ".join(result.source_reference for result in results)
            + (f" | {selected_window.reference}" if selected_window else ""),
            run_id=run_id,
        )
        if warnings:
            if selected_window and selected_window.rolling:
                report["warnings"].append(
                    f"{source_name} includes gas day {selected_window.open_gas_day_label} open at "
                    "the run anchor; offset exhaustion does not establish closed-day coverage."
                )
            report["warnings"].append(
                f"{source_name} has a bounded partial result or skipped normalization; "
                "see per-query completeness and row counters. Snapshot consistency is unproven."
            )
    except (
        EntsogTransportError,
        EntsogIngestionError,
        EntsogObservationPersistenceError,
        ValueError,
        SQLAlchemyError,
    ) as exc:
        # Every canonical operation owns a savepoint. Expected source failures
        # retain raw evidence and cannot roll back independent ECB/GIE work.
        code = getattr(exc, "code", "entsog_normalization_or_persistence_failed")
        prefix = getattr(exc, "validated_prefix_result", None)
        if prefix is not None and not persistence_started:
            results.append(prefix)
        if results and not persistence_started:
            # A later query may fail after earlier queries returned valid pages.
            # Retain those completed queries without normalizing a partial batch.
            try:
                archived = archive_entsog_pages(session, results)
                detail["archived_pages"] = sum(map(len, archived))
                detail["received_records"] = sum(result.record_count for result in results)
                detail["pages_fetched"] = sum(len(result.pages) for result in results)
                detail["queries"] = [
                    {
                        "reference": result.source_reference,
                        "complete": result.complete,
                        "stop_reason": result.stop_reason,
                    }
                    for result in results
                ]
            except EntsogIngestionError as archive_error:
                code = archive_error.code
        detail["status"] = "failed"
        _record_run(session, source_name, "failed", started, 0, f"entsog:{code}", run_id=run_id)
        report["failures"].append({"source": source_name, "code": code})
        report["warnings"].append(
            f"{source_name} refused canonical writes ({code}); existing rows kept."
        )


def _normalize_gie_page(
    product: GieProduct,
    page,
    *,
    fetch_reference: str = "",
) -> list[dict[str, Any]]:
    """Normalize one provider page and attach its per-page receipt metadata.

    The response-receipt instant is passed to the normalizer so a bare provider
    ``updatedAt`` (whose zone is not proven) uses the receipt while recording that
    substitution in ``metadata_json``. The exact archived raw-payload identity is
    stamped afterwards by :func:`_persist_gie_product`, which owns the archive
    call, so a row can never claim an archive that was not written.
    """

    if product.product == "AGSI":
        rows = gie_storage_observations_from_json(
            page.raw_payload, observed_at_utc=page.received_at_utc
        )
    else:
        rows = gie_lng_observations_from_json(
            page.raw_payload, observed_at_utc=page.received_at_utc
        )
    for row in rows:
        # The provider updatedAt must never replace the observed_at_utc the
        # persistence comparison keys on: it is carried as availability metadata.
        provider_updated_at = (row.get("metadata_json") or {}).get("updatedAt")
        metadata = dict(row.get("metadata_json") or {})
        metadata.update(
            {
                "source_page": page.page,
                "source_page_size": page.size,
                "provider_last_page": page.last_page,
                "provider_total_on_page": page.total_on_page,
                "source_receipt_at_utc": page.received_at_utc.isoformat(),
                "fetch_reference": fetch_reference,
            }
        )
        if provider_updated_at is not None:
            metadata["provider_updated_at"] = provider_updated_at
        row["metadata_json"] = metadata
    return rows


def _persist_gie_product(
    session,
    *,
    product: GieProduct,
    source_name: str,
    gie_result,
    model,
    started: datetime,
) -> dict[str, Any]:
    """Persist one product's bounded batch with revision-safe, exact lineage.

    The whole product batch is archived, normalized and written inside one
    SAVEPOINT of the caller's transaction:

    * every page is archived first and its **exact** ``archive_id`` + payload
      SHA-256 is stamped on the rows normalized from that page;
    * a page whose payload could not be archived (size/policy) fails the product
      closed -- canonical rows are never written claiming archive lineage that
      does not exist;
    * a semantically unchanged existing row is left byte-for-byte unchanged; a
      revised measurement is refused with ``gie_revision_requires_history`` and
      the savepoint rollback leaves every original row untouched, with no
      partial canonical write surviving the failure.

    Returns a report fragment with counts and, on failure, an explicit failure
    entry carrying only counts and observation ids -- never provider payload.
    """

    run_id = _new_run_id(source_name)
    archive_refs: list[dict[str, str]] = []
    partial_archive = _archive_page_payloads(
        session,
        product=product,
        source_name=source_name,
        gie_result=gie_result,
        archive_refs=archive_refs,
    )
    if partial_archive is not None:
        return _gie_persist_failure(
            session,
            source_name=source_name,
            started=started,
            run_id=run_id,
            code=partial_archive.code,
            observation_ids=[],
            archived_pages=len(archive_refs),
            warning=(
                f"{source_name} did not persist canonical rows: {partial_archive}. No row "
                "was written that claimed archive lineage it does not have."
            ),
        )

    # Normalize each page and stamp exactly that page's archive identity on its
    # rows; the per-page archive count and normalized row count must agree.
    rows: list[dict[str, Any]] = []
    for page, archive_ref in zip(gie_result.pages, archive_refs, strict=True):
        page_rows = _normalize_gie_page(
            product, page, fetch_reference=gie_result.source_reference
        )
        for row in page_rows:
            metadata = dict(row.get("metadata_json") or {})
            metadata.update(archive_ref)
            row["metadata_json"] = metadata
        rows.extend(page_rows)

    # Validate before any canonical side effect, so a synthetic / empty provider
    # payload fails the product without touching the observation tables.
    _reject_synthetic_gie_rows(rows, product=product.product)
    if not rows:
        _record_run(session, source_name, "failed", started, 0, "empty_response", run_id=run_id)
        return {
            "failure": {"source": source_name, "code": "gie_empty_response", "records": 0},
            "warning": f"{source_name} returned no observations.",
            "counts": {"records": 0, "inserted": 0, "unchanged": 0},
        }
    observation_ids = _observation_ids(rows)

    try:
        with session.begin_nested():
            stamped_rows = _stamp_lineage(
                rows, run_id=run_id, adapter_version="public-source-ingestor/1"
            )
            outcome = upsert_revision_safe_observation_rows(session, model, stamped_rows)
            session.flush()
    except GieRevisionRequiresHistoryError as exc:
        return _gie_persist_failure(
            session,
            source_name=source_name,
            started=started,
            run_id=run_id,
            code=exc.code,
            observation_ids=observation_ids,
            archived_pages=len(archive_refs),
            warning=(
                f"{source_name} refused a revised measurement ({exc.code}); the "
                "original rows are unchanged and no partial canonical write was kept. "
                "Append-only revision history is required before revised values may be "
                "stored."
            ),
        )

    _record_run(
        session,
        source_name,
        "succeeded" if gie_result.complete else "SUCCEEDED_WITH_WARNINGS",
        started,
        len(rows),
        gie_result.source_reference,
        run_id=run_id,
    )
    return {
        "failure": None,
        "warning": None,
        "counts": {
            "records": len(rows),
            "inserted": outcome["inserted"],
            "unchanged": outcome["unchanged"],
            "archived_pages": len(archive_refs),
        },
    }


class _GieArchiveLineageError(RuntimeError):
    """A GIE payload could not be archived, so canonical rows must not be written."""

    code = "gie_archive_lineage_required"


def _archive_page_payloads(
    session,
    *,
    product: GieProduct,
    source_name: str,
    gie_result,
    archive_refs: list[dict[str, str]],
) -> _GieArchiveLineageError | None:
    """Archive every page and append its exact reference to ``archive_refs``.

    Returns ``None`` on success. Any page that cannot be archived (size/policy)
    stops the product: an :class:`_GieArchiveLineageError` is returned so the
    caller fails closed instead of writing canonical rows that claim archive
    lineage which does not exist.
    """

    for page in gie_result.pages:
        archive_ref = _archive_raw_payload(
            session,
            source_system="GIE",
            dataset=product.product,
            source_reference=page.source_reference,
            payload_json=page.raw_payload,
            record_count=len(page.records),
            received_at=page.received_at_utc,
        )
        if archive_ref is None:
            return _GieArchiveLineageError(
                "GIE raw payload could not be archived for "
                f"{source_name} page {page.page}; refusing to persist canonical "
                "rows without exact archive lineage."
            )
        archive_refs.append(archive_ref)
    return None


def _gie_persist_failure(
    session,
    *,
    source_name: str,
    started: datetime,
    run_id: str,
    code: str,
    observation_ids: list[str],
    archived_pages: int,
    warning: str,
) -> dict[str, Any]:
    """Record the real failed run and return counts/ids only -- never payload."""

    _record_run(
        session,
        source_name,
        "failed",
        started,
        0,
        f"persist:{code}",
        run_id=run_id,
    )
    return {
        "failure": {
            "source": source_name,
            "code": code,
            "observation_ids": observation_ids,
            "records": 0,
        },
        "warning": warning,
        "counts": {
            "records": 0,
            "inserted": 0,
            "unchanged": 0,
            "refused": len(observation_ids),
            "archived_pages": archived_pages,
        },
    }


def _observation_ids(rows: list[dict[str, Any]]) -> list[str]:
    """Return distinct observation ids without ever quoting provider payload."""

    seen: list[str] = []
    for row in rows:
        observation_id = str(row.get("observation_id") or "")
        if observation_id and observation_id not in seen:
            seen.append(observation_id)
    return seen


def _reject_synthetic_gie_rows(
    rows: list[dict[str, Any]], *, product: str
) -> None:
    """Refuse to persist anything that is not a real GIE provider row.

    Bounded guard for the new GIE path: a mock/simulated row or a row attributed to
    another source system fails the run instead of being written as if it were live
    provider data.
    """

    for row in rows:
        if row.get("source_system") != "GIE":
            raise RuntimeError(
                f"GIE {product} produced a row attributed to "
                f"{row.get('source_system')!r}; refusing to persist synthetic data."
            )
        observation_id = str(row.get("observation_id") or "")
        if observation_id.startswith(("mock-", "sim-")):
            raise RuntimeError(
                f"GIE {product} produced a synthetic observation id "
                f"{observation_id!r}; refusing to persist it."
            )
        metadata = row.get("metadata_json") or {}
        if metadata.get("simulated") or metadata.get("mock"):
            raise RuntimeError(
                f"GIE {product} produced a row marked simulated/mock; refusing it."
            )




def _stamp_lineage(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    adapter_version: str,
) -> list[dict[str, Any]]:
    """Attach CR-09 lineage metadata to normalized rows before persistence."""

    stamped: list[dict[str, Any]] = []
    for row in rows:
        metadata = dict(row.get("metadata_json") or {})
        metadata["ingestion_run_id"] = run_id
        metadata["adapter_version"] = adapter_version
        stamped.append({**row, "metadata_json": metadata})
    return stamped


def _new_run_id(source_name: str) -> str:
    return f"run-{source_name.lower()}-{uuid.uuid4().hex[:12]}"

def _record_run(
    session,
    source_name: str,
    status: str,
    started: datetime,
    records: int,
    reference: str,
    *,
    run_id: str | None = None,
) -> None:
    finished_at = datetime.now(UTC)
    session.merge(
        IngestionRunRecord(
            run_id=run_id or f"run-{source_name.lower()}-{uuid.uuid4().hex[:12]}",
            source_name=source_name,
            status=status,
            started_at_utc=started,
            finished_at_utc=finished_at,
            notes=f"{records} normalized records upserted from {reference}.",
        )
    )
    record_audit_event(
        session,
        event_type="ingestion",
        principal="operator",
        action="public_source_ingest",
        resource=f"source:{source_name}",
        outcome=status,
        severity="warning" if status == "failed" else "info",
        detail=f"{records} normalized records from {reference}.",
        source_system="eurogas-nexus",
        now_utc=finished_at,
    )


def _replace_reference_network(
    session,
    *,
    nodes: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
    hubs: list[dict[str, Any]],
    tso_access_points: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace the ENTSOG reference snapshot table by table.

    Each table is replaced only when its incoming payload is non-empty, so a
    partial provider response can never wipe the existing reference network.
    Operator-maintained tables (edges, node/facility mappings, topology/market
    mappings) and non-ENTSOG rows are never touched. The whole step runs inside
    the caller's transaction, so any failure (including a foreign-key conflict
    on an operator edge that references a removed node) rolls everything back.
    """

    if not any((nodes, facilities, hubs, tso_access_points)):
        raise RuntimeError(
            "ENTSOG returned no reference-network rows; existing topology was kept."
        )

    node_ids = {row["id"] for row in nodes}
    now = datetime.now(UTC)
    summary: dict[str, Any] = {"replaced": 0, "skipped_tables": []}
    for model, rows in (
        (ReferenceNode, nodes),
        (ReferenceFacility, facilities),
        (ReferenceMarketHub, hubs),
        (ReferenceTsoAccessPoint, tso_access_points),
    ):
        if not rows:
            summary["skipped_tables"].append(model.__tablename__)
            continue
        prepared: list[dict[str, Any]] = []
        for row in rows:
            prepared_row = {**row, "created_at_utc": now}
            if model is ReferenceTsoAccessPoint and prepared_row["point_id"] not in node_ids:
                prepared_row["point_id"] = None
            prepared.append(prepared_row)
        summary["replaced"] += replace_reference_snapshot(
            session,
            model,
            prepared,
            source_system="ENTSOG",
        )
    session.flush()
    return summary


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("ok"):
        counts = ", ".join(
            f"{source}={detail['records']}" for source, detail in payload.get("sources", {}).items()
        )
        print(f"public source ingestion succeeded: {counts}")
    else:
        failures = payload.get("failures") or []
        if failures:
            detail = ", ".join(
                f"{failure.get('source')}:{failure.get('code')}" for failure in failures
            )
        else:
            detail = str(payload.get("error"))
        print(f"public source ingestion failed: {detail}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
