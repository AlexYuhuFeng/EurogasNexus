"""Read LNG terminal operators' published tariffs into the public tariff register (CP-11).

    python scripts/ops/refresh_lng_terminal_tariffs.py            # read permitted operators
    python scripts/ops/refresh_lng_terminal_tariffs.py --dry-run  # read and print, store nothing
    python scripts/ops/refresh_lng_terminal_tariffs.py --det-notice URL

**Terms first.** An operator's documents are read only after the firm has recorded that
operator's permission to reuse them (Admin -> Data sources -> LNG terminal tariffs, or
``PUT /api/lng/terminal-tariffs/operators/{operator}``). The terms check of 2026-11-18 found
that Fluxys and Elengy forbid reuse of their site content without written permission and DET
publishes no reuse terms (docs/legal/DATA_SOURCE_TERMS.md); without the recorded permission the
operator is skipped and reported ``needs_firm_terms``. The product never accepts terms itself.

Run daily from the scheduler once permitted (Fluxys publishes a new indexed tariff monthly):

* Zeebrugge: the Fluxys LNG price simulator (indexed slot for the month) and tariff list;
* Montoir, Fos Cavaou, Fos Tonkin: Elengy's ATTM tariff brochure, standard and SMART SPOT;
* Brunsbüttel / Wilhelmshaven: a DET auction notice given with ``--det-notice``.

Each document becomes candidate rows of ``lng_terminal_tariff`` keyed by its SHA-256: the same
document again changes nothing, a new one adds rows and queues one attention item ("Fluxys LNG
tariff changed: review 3 values"). A second person reviews them before they price anything
actionable. The firm's own terms (``lng_terminal_terms``) are never written here.
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


def collect(
    det_notice: str | None, operators: set[str]
) -> tuple[dict[str, list[TerminalCost]], list[str]]:
    """Read the documents of the permitted operators only; one list of figures per operator."""

    costs: dict[str, list[TerminalCost]] = {}
    problems: list[str] = []
    if "fluxys_lng" in operators:
        try:
            links = fluxys_document_links(_get(FLUXYS_TARIFF_PAGE).decode("utf-8", "ignore"))
            simulator = _get(links["simulator"])
            cost = parse_fluxys_simulator(simulator, source_url=links["simulator"])
            if "tariff_list" in links:
                gas_in_kind = parse_fluxys_gas_in_kind(_pdf_text(_get(links["tariff_list"])))
                if gas_in_kind is not None:
                    cost = TerminalCost(**{**cost.__dict__, "fuel_retention_pct": gas_in_kind})
            costs["fluxys_lng"] = [cost]
        except (httpx.HTTPError, TerminalTariffError, KeyError) as exc:
            problems.append(f"Fluxys: {type(exc).__name__}: {exc}"[:300])
    if "elengy" in operators:
        try:
            link = elengy_brochure_link(_get(ELENGY_TARIFF_PAGE).decode("utf-8", "ignore"))
            brochure = _get(link)
            costs["elengy"] = parse_elengy_brochure(
                _pdf_text(brochure), source_url=link, digest=sha256(brochure)
            )
        except (httpx.HTTPError, TerminalTariffError) as exc:
            problems.append(f"Elengy: {type(exc).__name__}: {exc}"[:300])
    if det_notice and "det" in operators:
        try:
            notice = _get(det_notice)
            costs["det"] = [
                parse_det_auction_notice(
                    _plain(notice), source_url=det_notice, digest=sha256(notice)
                )
            ]
        except (httpx.HTTPError, TerminalTariffError) as exc:
            problems.append(f"DET: {type(exc).__name__}: {exc}"[:300])
    return costs, problems


_TITLES = {
    "fluxys_lng": "Fluxys LNG price simulator",
    "elengy": "Elengy ATTM tariff brochure",
    "det": "DET auction result notice",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--det-notice", help="URL of a DET auction result notice")
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        # The firm's recorded permissions live in the runtime store: without it nothing is read.
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    from eurogas_nexus.application import lng_terminal_tariff_register as register

    with get_session_factory()() as session:
        states = {op: register.operator_permitted(session, op) for op in register.OPERATOR_TERMS}
    permitted = {op for op, ok in states.items() if ok}
    skipped = sorted(op for op, ok in states.items() if not ok)
    costs, problems = collect(args.det_notice, permitted)
    summary: dict = {
        "needs_firm_terms": skipped,
        "read": {
            op: [
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
                for c in items
            ]
            for op, items in costs.items()
        },
        "problems": problems,
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return 0
    now = datetime.now(UTC)
    results = {}
    with get_session_factory()() as session:
        for operator, items in costs.items():
            results[operator] = register.record_document(
                session, items, operator=operator, document_title=_TITLES[operator], now_utc=now
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
    summary["recorded"] = results
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
