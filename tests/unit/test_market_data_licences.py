"""Licensed data scopes are granted against the firm's licences: type, office, seats, dates."""

from datetime import date

from eurogas_nexus.domain.market_data.licences import (
    Licence,
    LicenceType,
    LicensedUse,
    grant_problems,
    validate_licence,
)

TODAY = date(2026, 10, 30)
PUBLIC = {"ENTSOG", "GIE"}


def _licence(**overrides) -> Licence:
    fields = dict(
        licence_id="l1",
        vendor="EEX",
        source_family="EEX",
        licence_type=LicenceType.ENTERPRISE,
        use=LicensedUse.DISPLAY_AND_NON_DISPLAY,
        valid_from=date(2026, 1, 1),
    )
    return Licence(**{**fields, **overrides})


def _problems(licences, families=("EEX",), office="UK", holders=None):
    return grant_problems(
        families=families,
        office=office,
        licences=licences,
        holders=holders or {},
        public_families=PUBLIC,
        today=TODAY,
    )


def test_public_and_wildcard_need_no_licence_but_licensed_families_do():
    assert _problems([], families=("ENTSOG", "*")) == {}
    assert "EEX" in _problems([])
    assert _problems([_licence()]) == {}


def test_expired_site_and_seat_limits():
    assert "EEX" in _problems([_licence(valid_to=date(2026, 6, 30))])
    site = _licence(licence_type=LicenceType.SITE, offices=("UK", "SG"))
    assert _problems([site], office="SG") == {}
    assert "CA" in _problems([site], office="CA")["EEX"]
    seats = _licence(licence_type=LicenceType.NAMED_USER, seats=2)
    assert _problems([seats], holders={"EEX": 1}) == {}
    assert "seats" in _problems([seats], holders={"EEX": 2})["EEX"]


def test_licence_validation():
    assert validate_licence(_licence(licence_type=LicenceType.NAMED_USER)) != []
    assert validate_licence(_licence(licence_type=LicenceType.SITE)) != []
    assert validate_licence(_licence(valid_to=date(2025, 1, 1))) != []
    assert validate_licence(_licence()) == []
