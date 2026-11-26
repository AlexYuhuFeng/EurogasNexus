"""Société Générale bank-rate connector (TAR-2): fake transport only, no network, no real data.

Every address here is under the reserved ``.invalid`` domain and every rate is made up; the
response shape is a made-up one the configuration maps, not Société Générale's (which is not
known to this repository and is to be confirmed with the bank).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import bank_feeds
from eurogas_nexus.application.source_precedence import resolve_fx_rate, resolve_interest_rate
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    InterestRateObservationRecord,
    OrganisationSettingRecord,
)
from eurogas_nexus.domain.connectors.registry import manifest_for
from eurogas_nexus.domain.dataops.registry import definition_for_source
from eurogas_nexus.domain.pricing import financial_institutions as fi
from eurogas_nexus.ingestion.connectors import socgen

NOW = datetime(2026, 11, 25, 18, 45, tzinfo=UTC)
AS_OF = datetime(2026, 11, 25, 20, tzinfo=UTC)
SECRET = "unit-test-secret-not-real"

CONFIG = {
    "base_url": "https://bank-api.invalid/rates",
    "auth": {
        "scheme": "oauth2_client_credentials",
        "token_url": "https://bank-auth.invalid/oauth/token",
        "client_id": "unit-test-client",
        "scope": "rates.read",
    },
    "feeds": {
        "fx": {
            "path": "fx/fixings",
            "records": "data.fixings",
            "params": {"from": "{from}", "to": "{to}"},
            "fields": {
                "base_currency": "ccy1",
                "quote_currency": "ccy2",
                "rate": "fixing",
                "value_date": "date",
                "rate_type": "side",
                "rate_id": "ref",
            },
            "values": {"rate_type": {"MID": "mid", "BID": "buy", "ASK": "sell"}},
            "published_at": {"time": "16:00", "timezone": "Europe/Paris"},
        },
        "interest": {
            "path": "interest/fixings",
            "records": "data",
            "fields": {"rate_id": "name", "currency": "ccy", "rate_pct": "value",
                       "value_date": "date", "day_count": "basis"},
            "scale": {"rate_pct": 100},
        },
    },
    "lookback_days": 5,
}

FX_BODY = {"data": {"fixings": [
    {"ccy1": "EUR", "ccy2": "USD", "fixing": 1.0951, "date": "2026-11-25", "side": "MID",
     "ref": "T-1"},
    {"ccy1": "EUR", "ccy2": "GBP", "fixing": 0.8712, "date": "2026-11-25", "side": "MID",
     "ref": "T-2"},
]}}
RATES_BODY = {"data": [
    {"name": "EUR-ON", "ccy": "EUR", "value": 0.0215, "date": "2026-11-25", "basis": "ACT/360"},
]}


class FakeBank:
    """A fake transport that records every request; nothing leaves the process."""

    def __init__(self, fx=FX_BODY, rates=RATES_BODY, *, token_status=200, fx_status=200):
        self.calls: list[httpx.Request] = []
        self.fx, self.rates = fx, rates
        self.token_status, self.fx_status = token_status, fx_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.calls.append(request)
        path = request.url.path
        if request.url.host == "bank-auth.invalid" and path == "/oauth/token":
            return httpx.Response(self.token_status, json={"access_token": "tok-1",
                                                          "token_type": "Bearer"})
        if request.headers.get("Authorization") != "Bearer tok-1":
            return httpx.Response(401, json={"error": "nope"})
        if path == "/rates/fx/fixings":
            return httpx.Response(self.fx_status, json=self.fx)
        if path == "/rates/interest/fixings":
            return httpx.Response(200, json=self.rates)
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _socgen(session, **terms):
    value = {"SOCGEN": {"name": "Societe Generale", "contracted": True,
                        "provides": ["fx", "interest"], "access": "api",
                        "agreement_recorded": True, **terms}}
    session.merge(OrganisationSettingRecord(setting_key="financial_institutions",
                                            value_json=value, updated_by="admin",
                                            updated_at_utc=NOW))
    session.flush()


def _env(tmp_path, config=CONFIG, *, secret=SECRET):
    path = tmp_path / "socgen.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env = {socgen.CONFIG_FILE_ENV: str(path)}
    if secret:
        env[socgen.SECRET_ENV] = secret
    return env


def _run(session, env, bank, **kwargs):
    return bank_feeds.run_socgen_feed(session, environ=env, client=bank.client(), now=NOW,
                                      commit=True, **kwargs)


# ------------------------------------------------------------- not connected: no network call


def test_not_configured_does_nothing_and_says_not_connected(session, tmp_path):
    bank = FakeBank()
    report = _run(session, _env(tmp_path), bank)
    assert report["connected"] is False and report["state"] == "not connected"
    assert report["code"] == socgen.INSTITUTION_NOT_CONFIGURED
    assert bank.calls == []


@pytest.mark.parametrize(
    ("env_of", "code"),
    [
        (lambda tmp: {}, socgen.ENDPOINT_NOT_CONFIGURED),
        (lambda tmp: _env(tmp, secret=None), socgen.CREDENTIAL_MISSING),
        (lambda tmp: {socgen.CONFIG_FILE_ENV: str(tmp / "missing.json"),
                      socgen.SECRET_ENV: SECRET}, socgen.ENDPOINT_CONFIG_INVALID),
    ],
)
def test_without_configuration_or_credential_nothing_is_fetched(session, tmp_path, env_of, code):
    _socgen(session)
    bank = FakeBank()
    report = _run(session, env_of(tmp_path), bank)
    assert report["connected"] is False and report["code"] == code
    assert bank.calls == [] and report["sources"] == {}
    assert session.query(FxObservationRecord).count() == 0


def test_file_access_is_not_a_live_feed(session, tmp_path):
    _socgen(session, access="file", agreement_recorded=False)
    bank = FakeBank()
    report = _run(session, _env(tmp_path), bank)
    assert report["code"] == socgen.ACCESS_NOT_API and bank.calls == []


def test_refuses_without_the_firms_agreement(session, tmp_path):
    # The setting refuses api access without the agreement ...
    with pytest.raises(fi.InstitutionError, match="agreement"):
        fi.validate_institutions({"SOCGEN": {"name": "SG", "provides": ["fx"], "access": "api"}})
    # ... and the connector refuses it too, even when handed such an institution directly.
    bank = FakeBank()
    institution = fi.Institution("SOCGEN", "SG", True, ("fx",), "api", False)
    connector = socgen.SocGenConnector(institution, environ=_env(tmp_path), client=bank.client())
    assert connector.status().code == socgen.AGREEMENT_NOT_RECORDED
    with pytest.raises(socgen.SocGenNotConnected, match="agreement"):
        connector.fetch("bank-fx-rates")
    assert bank.calls == []


def test_the_configuration_holds_no_secret_and_only_https():
    with pytest.raises(socgen.SocGenError, match="secret"):
        socgen.parse_config(CONFIG | {"auth": CONFIG["auth"] | {"client_secret": "x"}})
    with pytest.raises(socgen.SocGenError, match="https"):
        socgen.parse_config(CONFIG | {"base_url": "http://bank-api.invalid"})
    with pytest.raises(socgen.SocGenError, match="user or password"):
        socgen.parse_config(CONFIG | {"base_url": "https://u:p@bank-api.invalid"})
    with pytest.raises(socgen.SocGenError, match="path under"):
        socgen.parse_config(CONFIG | {"feeds": {"fx": {"path": "https://elsewhere.invalid/x"}}})
    with pytest.raises(socgen.SocGenError, match="not a column"):
        socgen.parse_config(CONFIG | {"feeds": {"fx": {"path": "x", "fields": {"iban": "x"}}}})


# ------------------------------------------------------------------------ mapping and storing


def test_rows_land_as_bank_socgen_through_the_import_contracts(session, tmp_path):
    _socgen(session)
    bank = FakeBank()
    report = _run(session, _env(tmp_path), bank)
    assert report["ok"] is True and report["connected"] is True and report["committed"] is True
    fx, rates = report["sources"]["bank-fx-rates"], report["sources"]["bank-interest-rates"]
    assert (fx["records"], fx["inserted"], fx["refused"]) == (2, 2, 0)
    assert (rates["records"], rates["inserted"]) == (1, 1)
    assert fx["stale"] is False and fx["newest_value_date"] == "2026-11-25"

    row = session.get(FxObservationRecord, "bank:SOCGEN:EURUSD:mid:2026-11-25")
    assert row.source_system == "BANK:SOCGEN" and row.rate == pytest.approx(1.0951)
    assert row.metadata_json == {"institution": "SOCGEN", "contract": "bank.fx_rates.v1"}
    assert row.source_record_id == "T-1"
    assert row.source_reference.startswith("import:bank.fx_rates.v1:socgen:api-bank-fx-rates-")
    # 16:00 Paris on the value date (the configured publication time), stable across fetches.
    observed = row.observed_at_utc.replace(tzinfo=row.observed_at_utc.tzinfo or UTC)
    assert observed == datetime(2026, 11, 25, 15, tzinfo=UTC)
    rate = session.query(InterestRateObservationRecord).one()
    assert (rate.source_system, rate.benchmark_id) == ("BANK:SOCGEN", "SOCGEN:EUR-ON")
    assert rate.rate_pct == pytest.approx(2.15) and rate.value_date == date(2026, 11, 25)

    # The OAuth token was asked once, with the client id and secret as basic auth, and the
    # window went as query parameters.
    token, fx_call = bank.calls[0], bank.calls[1]
    assert token.url.host == "bank-auth.invalid" and b"grant_type=client_credentials" in (
        token.content
    )
    assert token.headers["Authorization"].startswith("Basic ")
    assert fx_call.url.params["from"] == "2026-11-20" and fx_call.url.params["to"] == "2026-11-25"
    assert len([call for call in bank.calls if call.url.host == "bank-auth.invalid"]) == 1

    # The same fetch again changes nothing.
    again = _run(session, _env(tmp_path), FakeBank())
    assert again["sources"]["bank-fx-rates"]["unchanged"] == 2
    assert again["sources"]["bank-fx-rates"]["inserted"] == 0


def test_a_dry_run_stores_nothing(session, tmp_path):
    _socgen(session)
    report = bank_feeds.run_socgen_feed(session, environ=_env(tmp_path),
                                        client=FakeBank().client(), now=NOW)
    assert report["ok"] is True and report["committed"] is False
    assert report["sources"]["bank-fx-rates"]["inserted"] == 2
    session.flush()
    assert session.query(FxObservationRecord).count() == 0


def test_a_row_the_contract_refuses_refuses_the_feed_with_its_reason(session, tmp_path):
    _socgen(session)
    bad = {"data": {"fixings": [dict(FX_BODY["data"]["fixings"][0], side="SPOT")]}}
    report = _run(session, _env(tmp_path), FakeBank(fx=bad))
    fx = report["sources"]["bank-fx-rates"]
    assert report["ok"] is False and fx["file_refused"] is True
    assert fx["import"]["refused"][0]["reason_code"] == "rate_type_unknown"
    assert session.query(FxObservationRecord).count() == 0


def test_a_refusal_by_the_bank_carries_no_secret_and_no_response_text(session, tmp_path):
    _socgen(session)
    report = _run(session, _env(tmp_path), FakeBank(token_status=401))
    assert report["ok"] is False
    assert {f["code"] for f in report["failures"]} == {"auth_refused"}
    assert SECRET not in json.dumps(report) and "nope" not in json.dumps(report)


def test_api_key_scheme_sends_the_secret_in_the_configured_header(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=FX_BODY)

    config = CONFIG | {"auth": {"scheme": "api_key", "header": "X-Api-Key"}}
    institution = fi.institutions({"SOCGEN": {"name": "SG", "provides": ["fx"], "access": "api",
                                              "agreement_recorded": True}})[0]
    connector = socgen.SocGenConnector(
        institution, environ=_env(tmp_path, config),
        client=httpx.Client(transport=httpx.MockTransport(handler)), now=NOW,
    )
    payload = connector.fetch("bank-fx-rates")
    assert payload.source_system == "BANK:SOCGEN" and len(payload.raw_data) == 2
    assert seen[0].headers["X-Api-Key"] == SECRET and "Authorization" not in seen[0].headers


# --------------------------------------------------------------------------- staleness


def test_an_old_fixing_is_reported_stale_and_the_resolver_skips_it(session, tmp_path):
    _socgen(session, max_age_days=3)
    old = {"data": {"fixings": [dict(FX_BODY["data"]["fixings"][0], date="2026-11-18")]}}
    session.add(FxObservationRecord(
        observation_id="ecb-1", pair="EURUSD", base_currency="EUR", quote_currency="USD",
        rate=1.10, rate_type="reference", value_date="2026-11-25", observed_at_utc=NOW,
        source_system="ECB", source_reference="test", freshness="daily", research_only=True,
    ))
    report = _run(session, _env(tmp_path), FakeBank(fx=old))
    fx = report["sources"]["bank-fx-rates"]
    assert fx["stale"] is True and fx["newest_value_date"] == "2026-11-18"
    assert report["stale"] == ["bank-fx-rates"]
    session.flush()
    used = resolve_fx_rate(session, "EUR", "USD", AS_OF)
    assert used.used.tier == "ecb_reference" and used.tiers[0].reason == "stale"


# ------------------------------------------------------------------ precedence over the ECB


def test_socgen_rows_win_over_ecb_in_the_unchanged_precedence(session, tmp_path):
    session.add(FxObservationRecord(
        observation_id="ecb-1", pair="EURUSD", base_currency="EUR", quote_currency="USD",
        rate=1.10, rate_type="reference", value_date="2026-11-25", observed_at_utc=NOW,
        source_system="ECB", source_reference="test", freshness="daily", research_only=True,
    ))
    session.add(InterestRateObservationRecord(
        observation_id="estr-1", benchmark_id="ESTR", currency="EUR",
        value_date=date(2026, 11, 25), rate_pct=1.93, day_count="ACT/360", source_system="ECB",
        source_reference="t", ingested_at_utc=NOW,
    ))
    session.flush()
    assert resolve_fx_rate(session, "EUR", "USD", AS_OF).used.tier == "ecb_reference"
    _socgen(session)
    _run(session, _env(tmp_path), FakeBank())
    session.flush()
    fx = resolve_fx_rate(session, "EUR", "USD", AS_OF, "lng_demurrage")
    assert fx.used.tier == "contracted_bank" and fx.used.found.source == "BANK:SOCGEN"
    assert fx.value == pytest.approx(1.0951)
    assert [tier.tier for tier in fx.tiers] == [
        "contracted_bank", "published_reference", "ecb_reference"
    ]
    rate = resolve_interest_rate(session, "EUR", AS_OF)
    assert rate.used.found.source == "BANK:SOCGEN" and rate.value == pytest.approx(2.15)


# ------------------------------------------------------------------- registration and status


def test_the_source_is_registered_schedulable_and_off_by_default():
    manifest = manifest_for(socgen.SOURCE_ID)
    assert manifest is not None and manifest.system == socgen.SOURCE_SYSTEM
    assert manifest.credentials[0].provider_id == socgen.PROVIDER_ID
    assert manifest.credentials[0].env_vars == (socgen.SECRET_ENV,)
    assert manifest.credentials[0].file_env == socgen.SECRET_FILE_ENV
    definition = definition_for_source(socgen.SOURCE_ID)
    assert definition.schedulable is True and definition.enabled_default is False


def test_feed_status_is_secret_free_and_names_other_banks_unconnected(tmp_path):
    sg, other = fi.institutions({
        "SOCGEN": {"name": "SG", "provides": ["fx"], "access": "api", "agreement_recorded": True},
        "ABCBANK": {"name": "ABC", "provides": ["fx"], "access": "api",
                    "agreement_recorded": True},
    })[::-1]
    ready = bank_feeds.feed_status(sg, environ=_env(tmp_path))
    assert ready["connected"] is True and SECRET not in json.dumps(ready)
    assert bank_feeds.feed_status(sg, environ={})["state"] == "not connected"
    assert bank_feeds.feed_status(other)["code"] == "no_connector"
    assert "connector available" in sg.as_dict()["live_feed"]
    assert "not connected" in other.as_dict()["live_feed"]
    assert "SOCGEN" in fi.LIVE_FEED_TERMS and "agreement" in fi.LIVE_FEED_TERMS
