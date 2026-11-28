"""The consents' scope, enforced (owner, 2026-11-28): the firm's own use, no resale.

- every identified user of the firm reads data fetched under consent; a caller that presented
  nothing does not;
- every export decision treats it as internal use only, whatever a licence record says;
- a spread never sets a real price against a simulated one, and a published cash-out price is
  what My gas day values an open net at, with its gas day.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from eurogas_nexus.application.gas_day import cost_of_nothing
from eurogas_nexus.application.licensed_use import licensed_families
from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal
from eurogas_nexus.governance.entitlement import ExportDecision, file_export_decision
from eurogas_nexus.security.identity import (
    ANONYMOUS_IDENTITY_SOURCE,
    AuthenticatedPrincipal,
    is_consented_family,
    principal_allows_source_family,
)


def _principal(**kw) -> AuthenticatedPrincipal:
    base = dict(principal_id="p", name="p", principal_type="USER", role="VIEWER",
                status="ACTIVE", data_scopes=(), auth_method="identity_key")
    return AuthenticatedPrincipal(**(base | kw))


ROWS = [{"source_system": "THE"}, {"source_system": "MIBGAS"}, {"source_system": "ENTSOG"},
        {"source_system": "EEX"}]


def test_every_identified_user_reads_consented_data_without_a_grant():
    viewer = _principal()
    assert principal_allows_source_family(viewer, "MIBGAS")
    assert principal_allows_source_family(viewer, "NATIONAL_GAS_PRICES")
    assert not principal_allows_source_family(viewer, "EEX")  # the licensed family is unchanged
    assert [r["source_system"] for r in filter_entitled_rows(viewer, ROWS)] == [
        "THE", "MIBGAS", "ENTSOG"]
    assert is_consented_family("EEX_PUBLIC") and not is_consented_family("EEX")


def test_an_anonymous_caller_never_reads_consented_data():
    token = _principal(principal_id="service:public-api", principal_type="SERVICE",
                       role="OPERATOR", data_scopes=("*",), auth_method="legacy_public_token")
    anonymous = replace(token, identity_source=ANONYMOUS_IDENTITY_SOURCE)
    # The deployment's own token keeps its single-trust-domain view...
    assert len(filter_entitled_rows(token, ROWS)) == 4
    # ...a caller that presented nothing does not get the consented families.
    assert [r["source_system"] for r in filter_entitled_rows(anonymous, ROWS)] == [
        "ENTSOG", "EEX"]
    assert [r["source_system"] for r in filter_rows_for_principal(anonymous, ROWS)] == [
        "ENTSOG", "EEX"]
    assert not principal_allows_source_family(
        replace(_principal(), identity_source=ANONYMOUS_IDENTITY_SOURCE), "THE")


def test_every_export_decision_keeps_consented_data_inside_the_firm():
    assert {"THE", "MIBGAS", "EEX_PUBLIC"} <= licensed_families(["THE", "MIBGAS", "EEX_PUBLIC",
                                                                 "ENTSOG"])
    decision = file_export_decision({"MIBGAS"}, redistributable={"MIBGAS"},
                                    registered={"MIBGAS"})
    assert decision.decision is ExportDecision.RESTRICTED
    assert decision.restrictions == ("internal-use-only", "no-redistribution")
    assert file_export_decision(set()).decision is ExportDecision.ALLOWED


def test_a_report_for_outside_the_firm_never_counts_consented_data_as_redistributable(tmp_path):
    from sqlalchemy.orm import Session

    from eurogas_nexus.application.reports.engine import redistributable_families
    from tests.fixtures.news_seed import store

    _url, engine = store(tmp_path, "licences.sqlite")
    with Session(engine) as session:
        assert redistributable_families(session, {"THE", "MIBGAS"}, date(2026, 3, 3)) == set()


def _close(hub, day, price, *, simulated):
    return {"hub": hub, "tenor": "day-ahead", "day": day, "price": price, "price_mwh": price,
            "unit": "EUR/MWh", "unit_mwh": "EUR/MWh", "currency": "EUR",
            "observed_at_utc": datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            "simulated": simulated, "source_system": "X_Sim" if simulated else "MIBGAS",
            "hub_resolved": True, "period_start_utc": None, "period_end_utc": None}


def test_a_spread_never_sets_a_real_leg_against_a_simulated_one():
    from types import SimpleNamespace

    from eurogas_nexus.application.spreads_board import _same_class_legs

    day = date(2026, 3, 2)
    rows = [_close("PVB", day, 40.0, simulated=False), _close("PVB", day, 41.0, simulated=True),
            _close("TTF", day, 38.0, simulated=True)]
    mine, ref = _same_class_legs(SimpleNamespace(rows=rows), "PVB", "TTF", "day-ahead")
    assert mine[day]["simulated"] and ref[day]["simulated"]  # sim against sim, the real unused
    rows.append(_close("TTF", day, 37.5, simulated=False))
    mine, ref = _same_class_legs(SimpleNamespace(rows=rows), "PVB", "TTF", "day-ahead")
    assert not mine[day]["simulated"] and not ref[day]["simulated"]
    assert mine[day]["price"] - ref[day]["price"] == 2.5


def test_my_gas_day_values_an_open_net_at_the_published_cash_out_with_its_day():
    published = {"gas_day": "2026-03-01", "currency": "EUR", "reference": 30.0,
                 "short_price": 31.2, "long_price": 29.1, "short_premium": 1.2,
                 "long_discount": 0.9, "source_system": "THE", "publisher": "Trading Hub Europe",
                 "statuses": ["final"]}
    short = cost_of_nothing(-100.0, None, "THE", "short", published=published)
    assert short["basis"] == "published" and short["value"] == 120.0
    assert short["published_gas_day"] == "2026-03-01" and short["published_price"] == 31.2
    long_ = cost_of_nothing(100.0, None, "THE", "long", published=published)
    assert long_["value"] == 90.0 and long_["side"] == "long_discount"
    # No published price, no assumption: missing, as before.
    assert cost_of_nothing(-100.0, None, "THE", "short")["basis"] == "missing"
    # A published price in another currency is never used.
    assert cost_of_nothing(-100.0, None, "NBP", "short", published=published)["basis"] == \
        "missing"
