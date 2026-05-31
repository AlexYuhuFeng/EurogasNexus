"""Observation model contract tests (DB-free)."""


def test_market_observation_importable() -> None:
    from eurogas_nexus.observations.market import MarketObservation

    obs = MarketObservation(
        observation_id="mkt-001", market_venue="TTF", product="month-ahead",
        price=42.5, unit="EUR/MWh", currency="EUR",
        period_start_utc="2026-06-01T00:00:00Z", period_end_utc="2026-07-01T00:00:00Z",
    )
    assert obs.market_venue == "TTF"
    assert obs.research_only is True


def test_fx_observation_importable() -> None:
    from eurogas_nexus.observations.market import FxObservation

    fx = FxObservation(pair="EURUSD", rate=1.085, base_currency="EUR", quote_currency="USD")
    assert fx.pair == "EURUSD"
    assert fx.base_currency == "EUR"
    assert fx.research_only is True


def test_market_price_mark_supports_live_screen_fields() -> None:
    from eurogas_nexus.observations.market import MarketPriceMark

    mark = MarketPriceMark(
        mark_id="ice-ocm-nbp-wd",
        venue="ICE OCM",
        hub="NBP",
        product="within-day",
        delivery_start_utc="2026-05-31T05:00:00Z",
        delivery_end_utc="2026-06-01T05:00:00Z",
        currency="GBP",
        unit="GBP/MWh",
        bid=28.2,
        ask=28.4,
    )
    assert mark.bid == 28.2
    assert mark.research_only is True


def test_flow_observation_importable() -> None:
    from eurogas_nexus.observations.physical import FlowObservation

    obs = FlowObservation(
        observation_id="flw-001", point_id="node-x", point_name="Test",
        direction="entry", flow_mcm_d=85.0,
        period_start_utc="2026-05-29T00:00:00Z", period_end_utc="2026-05-30T00:00:00Z",
        tso="Example TSO",
    )
    assert obs.direction == "entry"
    assert obs.tso == "Example TSO"
    assert obs.research_only is True


def test_capacity_observation_importable() -> None:
    from eurogas_nexus.observations.physical import CapacityObservation

    obs = CapacityObservation(
        observation_id="cap-001", point_id="node-x", point_name="Test",
        capacity_type="technical", capacity_mcm_d=100.0,
        period_start_utc="2026-05-29T00:00:00Z", period_end_utc="2026-05-30T00:00:00Z",
    )
    assert obs.capacity_type == "technical"


def test_outage_event_importable() -> None:
    from eurogas_nexus.observations.physical import OutageEvent

    evt = OutageEvent(
        event_id="out-001", facility_id="fac-x", facility_name="Test",
        event_type="planned", status="scheduled", start_utc="2026-06-15T00:00:00Z",
    )
    assert evt.event_type == "planned"


def test_lng_models_importable() -> None:
    from eurogas_nexus.observations.lng import LngObservation, LngTerminal

    terminal = LngTerminal(terminal_id="lng-x", name="Test", country="NL", lat=52.0, lon=4.0)
    assert terminal.country == "NL"

    obs = LngObservation(
        observation_id="lng-001", terminal_id="lng-x", terminal_name="Test",
        observation_type="send_out", value_mcm=28.0,
    )
    assert obs.observation_type == "send_out"


def test_storage_models_importable() -> None:
    from eurogas_nexus.observations.storage import StorageObservation, StorageSite

    site = StorageSite(site_id="stor-x", name="Test", country="AT", lat=48.0, lon=13.0)
    assert site.country == "AT"

    obs = StorageObservation(
        observation_id="sto-001", site_id="stor-x", site_name="Test",
        observation_type="fill_level", fill_pct=62.5,
    )
    assert obs.fill_pct == 62.5


def test_weather_models_importable() -> None:
    from eurogas_nexus.observations.weather import HddCddMetric, WeatherObservation, WeatherStation

    station = WeatherStation(station_id="ws-x", name="Test", country="NL", lat=52.0, lon=4.0)
    assert station.country == "NL"

    obs = WeatherObservation(
        observation_id="wth-001", station_id="ws-x", station_name="Test",
        temperature_c=14.5, period_start_utc="2026-05-29T00:00:00Z",
        period_end_utc="2026-05-30T00:00:00Z",
    )
    assert obs.temperature_c == 14.5

    hdd = HddCddMetric(
        metric_id="hdd-001", station_id="ws-x", station_name="Test",
        metric_type="HDD", base_temperature_c=15.5, value=1.0,
        period_start_utc="2026-05-29T00:00:00Z", period_end_utc="2026-05-30T00:00:00Z",
    )
    assert hdd.metric_type == "HDD"


def test_contracts_models_importable() -> None:
    from eurogas_nexus.observations.contracts import CapacityContract, RouteEligibility

    ctr = CapacityContract(
        contract_id="ctr-001", route_name="TTF-NCG",
        from_node_id="node-ttf", to_node_id="node-ncg", capacity_boe_d=500000.0,
        capacity_mwh_per_day=2930000.0,
    )
    assert ctr.research_only is True
    assert ctr.capacity_mwh_per_day == 2930000.0

    route = RouteEligibility(
        route_id="rte-001", from_node_id="node-ttf", to_node_id="node-ncg",
        eligibility="confirmed", confidence=0.95,
    )
    assert route.eligibility == "confirmed"


def test_all_models_preserve_research_metadata() -> None:
    """All observation models must have research_only flag."""
    from eurogas_nexus.observations.lng import LngObservation
    from eurogas_nexus.observations.market import MarketObservation
    from eurogas_nexus.observations.physical import FlowObservation
    from eurogas_nexus.observations.storage import StorageObservation
    from eurogas_nexus.observations.weather import WeatherObservation

    assert MarketObservation.__dataclass_fields__["research_only"].default is True
    assert FlowObservation.__dataclass_fields__["research_only"].default is True
    assert LngObservation.__dataclass_fields__["research_only"].default is True
    assert StorageObservation.__dataclass_fields__["research_only"].default is True
    assert WeatherObservation.__dataclass_fields__["research_only"].default is True
