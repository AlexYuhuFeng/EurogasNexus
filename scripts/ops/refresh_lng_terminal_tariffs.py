"""Read each LNG terminal operator's latest published tariff and update the firm's terms.

    python scripts/ops/refresh_lng_terminal_tariffs.py            # fetch, update, notify
    python scripts/ops/refresh_lng_terminal_tariffs.py --dry-run  # fetch and print only
    python scripts/ops/refresh_lng_terminal_tariffs.py --det-notice URL

Run daily from the scheduler (Fluxys publishes a new indexed tariff every month):

* Zeebrugge: the Fluxys LNG tariff page's newest price simulator (indexed slot for the
  month) and tariff list (gas in kind);
* Montoir, Fos Cavaou, Fos Tonkin: Elengy's ATTM tariff brochure, standard and SMART SPOT;
* Brunsbüttel / Wilhelmshaven: a DET auction notice given with ``--det-notice`` (DET
  publishes results as news, so the desk passes the notice it wants priced).

Each terminal product becomes one row of ``lng_terminal_terms`` (``zeebrugge:term``,
``montoir:spot`` ...) with the operator's figures, the document URL, its SHA-256, the period
and when it was read. Desk-entered fields (sailing days, entry tariff, port costs, other)
are kept. When a document's content changes, a "tariff" notification is queued so the desk
reviews the new prices. Terminals without a public price list (Gate, Dunkerque LNG, Grain,
Eemshaven, private terminals) stay as the desk entered them from the firm's own contracts.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import UTC, datetime

import httpx

from eurogas_nexus.application.notifications import dispatch, queue_notification
from eurogas_nexus.core.outbound_http import client_options
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.ingestion.lng_terminal_tariffs import (
    ELENGY_TARIFF_PAGE,
    FLUXYS_TARIFF_PAGE,
    TerminalCost,
    TerminalTariffError,
    elengy_brochure_link,
    fluxys_document_links,
    parse_det_auction_notice,
    parse_elengy_brochure,
    parse_fluxys_gas_in_kind,
    parse_fluxys_simulator,
    sha256,
)

USER_AGENT = "EurogasNexus-TariffRefresh/1.0 (+terminal tariff evidence)"


def _get(url: str) -> bytes:
    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        trust_env=False,
        **client_options(url),
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _pdf_text(content: bytes) -> str:
    import io

    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


def _plain(content: bytes) -> str:
    text = content.decode("utf-8", "ignore")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))


def collect(det_notice: str | None) -> tuple[list[TerminalCost], list[str]]:
    costs: list[TerminalCost] = []
    problems: list[str] = []
    try:
        links = fluxys_document_links(_get(FLUXYS_TARIFF_PAGE).decode("utf-8", "ignore"))
        simulator = _get(links["simulator"])
        cost = parse_fluxys_simulator(simulator, source_url=links["simulator"])
        if "tariff_list" in links:
            gas_in_kind = parse_fluxys_gas_in_kind(_pdf_text(_get(links["tariff_list"])))
            if gas_in_kind is not None:
                cost = TerminalCost(**{**cost.__dict__, "fuel_retention_pct": gas_in_kind})
        costs.append(cost)
    except (httpx.HTTPError, TerminalTariffError, KeyError) as exc:
        problems.append(f"Fluxys: {type(exc).__name__}: {exc}"[:300])
    try:
        link = elengy_brochure_link(_get(ELENGY_TARIFF_PAGE).decode("utf-8", "ignore"))
        brochure = _get(link)
        costs += parse_elengy_brochure(
            _pdf_text(brochure), source_url=link, digest=sha256(brochure)
        )
    except (httpx.HTTPError, TerminalTariffError) as exc:
        problems.append(f"Elengy: {type(exc).__name__}: {exc}"[:300])
    if det_notice:
        try:
            notice = _get(det_notice)
            costs.append(
                parse_det_auction_notice(
                    _plain(notice), source_url=det_notice, digest=sha256(notice)
                )
            )
        except (httpx.HTTPError, TerminalTariffError) as exc:
            problems.append(f"DET: {type(exc).__name__}: {exc}"[:300])
    return costs, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--det-notice", help="URL of a DET auction result notice")
    args = parser.parse_args(argv)
    costs, problems = collect(args.det_notice)
    summary = {
        "read": [
            {
                "terminal": c.terminal_id,
                "regime": c.regime,
                "period": c.period,
                "fixed_per_cargo": c.fixed_per_cargo,
                "per_mwh": c.per_mwh,
                "by_cargo_class": c.by_cargo_class,
                "fuel_pct": c.fuel_retention_pct,
                "sha256": c.source_sha256[:12],
            }
            for c in costs
        ],
        "problems": problems,
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return 0 if costs else 1
    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    from eurogas_nexus.db.models import LngTerminalTermsRecord

    now = datetime.now(UTC)
    changed = []
    with get_session_factory()() as session:
        for cost in costs:
            row = session.get(LngTerminalTermsRecord, cost.terminal_id)
            if row is None:
                row = LngTerminalTermsRecord(
                    terminal_id=cost.terminal_id,
                    entry_tariff_per_mwh=0.0,
                    port_costs_per_cargo=0.0,
                    other_per_mwh=0.0,
                    extra_sailing_days=0.0,
                    capacity_basis="spot",
                )
                session.add(row)
            if row.source_sha256 and row.source_sha256 != cost.source_sha256:
                changed.append(cost)
            label = (
                "SMART SPOT"
                if cost.product == "spot" and cost.regime == "regulated"
                else cost.product
            )
            row.name = f"{cost.name} ({label})"
            row.country, row.hub, row.regime = cost.country, cost.hub, cost.regime
            row.regas_tariff_per_mwh = cost.per_mwh
            row.fixed_per_cargo = cost.fixed_per_cargo
            row.by_cargo_class = cost.by_cargo_class or None
            if cost.fuel_retention_pct:
                row.fuel_retention_pct = cost.fuel_retention_pct
            row.source_url, row.source_sha256 = cost.source_url, cost.source_sha256
            row.effective_from, row.retrieved_at_utc = cost.effective_from, now
            row.source_note = cost.note()
            row.updated_by, row.updated_at_utc = "tariff-refresh", now
        for cost in changed:
            queue_notification(
                session,
                category="tariff",
                severity="medium",
                title=f"LNG tariff changed: {cost.name}",
                body=f"{cost.period}\nSource: {cost.source_url}",
                dedupe_key=f"lng-tariff:{cost.terminal_id}:{cost.source_sha256}",
                now=now,
            )
        for problem in problems:
            queue_notification(
                session,
                category="source",
                severity="medium",
                title="LNG tariff refresh could not read a publication",
                body=problem,
                dedupe_key=f"lng-tariff-problem:{now:%Y-%m-%d}:{problem[:80]}",
                now=now,
            )
        dispatch(session, now=now)
        session.commit()
    summary["changed"] = [cost.terminal_id for cost in changed]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
