"""The write path of a bank's live rate feed: fetch, map, store through the bank contracts.

One bank has a connector in this build, Société Générale (institution key ``SOCGEN``,
``ingestion/connectors/socgen.py``). :func:`run_socgen_feed` reads the institution from the
organisation setting ``financial_institutions``, asks the connector whether it is connected
(no network call when it is not), fetches each feed the institution provides, maps the
records to the ``bank.fx_rates.v1`` / ``bank.interest_rates.v1`` columns and stores them with
:func:`~eurogas_nexus.application.import_contracts.run_import` under the system ``SOCGEN``.
The rows are therefore the same ``BANK:SOCGEN`` rows a file of the bank's export makes, with
the same keys, checks, refusals, lineage (``source_reference``) and audit event, and the
source-precedence resolver uses them first (contracted bank, then a published reference,
then the ECB) without any change.

:func:`feed_status` is the secret-free connection state an institution shows (pricing route).

Run by ``scripts/ops/fetch_bank_rates.py`` (operator, or the data-ops scheduler once an
administrator enables ``src-bank-socgen``; it is off by default).

TAR-2：银行实时费率的写入路径：取数、映射，再经银行导入契约写入为 BANK:SOCGEN 行，
来源优先级与数据血缘保持不变；未连接时不发起网络调用。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.application.import_contracts import REJECT_FILE, run_import
from eurogas_nexus.application.source_precedence import configured_institutions
from eurogas_nexus.domain.pricing.financial_institutions import Institution
from eurogas_nexus.ingestion.connectors import socgen

#: Institution keys with a connector in this build.
CONNECTORS = (socgen.INSTITUTION_KEY,)


def socgen_institution(session: Any) -> Institution | None:
    """The configured ``SOCGEN`` institution, or ``None``."""

    return next(
        (bank for bank in configured_institutions(session) if bank.key == socgen.INSTITUTION_KEY),
        None,
    )


def feed_status(
    institution: Institution, *, environ: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    """The live-feed state of an institution with access ``api`` (``None`` otherwise)."""

    if institution.access != "api":
        return None
    if institution.key not in CONNECTORS:
        return {
            "connector": None,
            "connected": False,
            "state": "not connected",
            "code": "no_connector",
            "message": "no connector for this bank in this build; use the file import",
        }
    return socgen.connection_status(institution, environ=environ).as_dict()


def _newest(rows: Sequence[Mapping[str, str]]) -> date | None:
    days = []
    for row in rows:
        try:
            days.append(date.fromisoformat(str(row.get("value_date") or "")[:10]))
        except ValueError:
            continue
    return max(days) if days else None


def run_socgen_feed(
    session: Any,
    *,
    environ: Mapping[str, str] | None = None,
    client: Any = None,
    config: socgen.ApiConfig | None = None,
    secret_lookup: Callable[[], str | None] | None = None,
    commit: bool = False,
    on_error: str = REJECT_FILE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch the ``SOCGEN`` feeds and store them through the bank import contracts.

    Without ``commit`` it is a dry run: the bank is read and the counts say what storing
    would do, and nothing is written. With ``commit`` the rows are written in ``session``
    (the caller commits). ``on_error`` is the contracts' (``reject_file``: one refused row
    stores nothing of that feed).

    Returns:
        A report: ``ok``, ``connected``, ``code``/``message`` when not connected, and per
        dataset the counts (``records``, ``accepted``, ``inserted``, ``updated``,
        ``unchanged``, ``refused``), the newest value date, whether it is ``stale`` (older
        than the institution's ``max_age_days``) and the import report.
    """

    moment = (now or datetime.now(UTC)).astimezone(UTC)
    institution = socgen_institution(session)
    connector = socgen.SocGenConnector(
        institution, environ=environ, client=client, config=config,
        secret_lookup=secret_lookup, now=moment,
    )
    state = connector.status()
    base = {
        "institution": socgen.INSTITUTION_KEY,
        "source_id": socgen.SOURCE_ID,
        "source_system": socgen.SOURCE_SYSTEM,
        "committed": False,
    }
    if not state.connected:
        return base | {
            "ok": False,
            "connected": False,
            "state": "not connected",
            "code": state.code,
            "message": state.message,
            "sources": {},
        }
    assert institution is not None
    sources: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    for kind in institution.provides:
        dataset = socgen.DATASETS[kind]
        try:
            feed = connector.feed(dataset)
            payload = connector.fetch(dataset)
        except socgen.SocGenError as exc:
            failures.append({"dataset": dataset, "code": exc.code, "message": exc.message})
            continue
        rows = socgen.contract_rows(kind, payload.raw_data, feed)
        if not rows:
            failures.append({
                "dataset": dataset,
                "code": "empty_response",
                "message": f"the bank returned no {dataset} for the look-back window",
            })
            continue
        report = run_import(
            socgen.CONTRACT_IDS[kind],
            socgen.contract_csv(kind, rows),
            system=socgen.INSTITUTION_KEY,
            file_name=f"api-{dataset}-{moment.strftime('%Y%m%dT%H%M%SZ')}.csv",
            session=session,
            on_error=on_error,
            commit=commit,
            now=moment,
        )
        newest = _newest(rows)
        stale = newest is None or (moment.date() - newest).days > institution.max_age_days
        sources[dataset] = {
            "records": report.rows,
            "accepted": report.accepted,
            "inserted": report.created,
            "updated": report.updated,
            "unchanged": report.unchanged,
            "refused": len(report.refused),
            "file_refused": report.file_refused,
            "newest_value_date": newest.isoformat() if newest else None,
            "max_age_days": institution.max_age_days,
            "stale": stale,
            "retrieved_at_utc": payload.retrieval_ts_utc,
            "lineage": payload.source_reference_id,
            "import": report.as_dict(),
        }
        if report.file_refused:
            failures.append({
                "dataset": dataset,
                "code": "rows_refused",
                "message": f"{len(report.refused)} row(s) refused by {socgen.CONTRACT_IDS[kind]}",
            })
    return base | {
        "ok": not failures and bool(sources),
        "connected": True,
        "state": "ready",
        "committed": bool(commit) and bool(sources),
        "sources": sources,
        "failures": failures,
        "stale": sorted(name for name, item in sources.items() if item["stale"]),
    }


__all__ = ["CONNECTORS", "feed_status", "run_socgen_feed", "socgen_institution"]
