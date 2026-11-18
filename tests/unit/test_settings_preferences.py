"""Personal preferences, organisation defaults and what takes effect."""

import pytest

from eurogas_nexus.domain.settings.preferences import (
    BUILT_IN_DEFAULTS,
    SettingsError,
    effective_preferences,
    validate_organisation_defaults,
    validate_preferences,
)


def test_user_overrides_organisation_overrides_built_in():
    effective = effective_preferences(
        {"theme": "dark", "market_view": "network"}, {"theme": "light"}
    )
    assert effective["theme"] == "light"
    assert effective["market_view"] == "network"
    assert effective["market_board_layout"] == BUILT_IN_DEFAULTS["market_board_layout"]


def test_a_switched_off_language_falls_back_to_the_organisation_default():
    organisation = {"enabled_languages": ["en"], "language": "en"}
    assert effective_preferences(organisation, {"language": "zh-CN"})["language"] == "en"


@pytest.mark.parametrize(
    "values",
    [{"colour": "blue"}, {"theme": "neon"}, {"language": "fr"}, {"market_view": 3}],
)
def test_values_outside_the_vocabulary_are_refused(values):
    with pytest.raises(SettingsError):
        validate_preferences(values)


def test_null_clears_and_organisation_language_must_be_enabled():
    assert validate_preferences({"theme": None}) == {}
    with pytest.raises(SettingsError):
        validate_organisation_defaults({"enabled_languages": ["en"], "language": "zh-CN"})
    assert validate_organisation_defaults({"enabled_languages": ["zh-CN", "en", "en"]}) == {
        "enabled_languages": ["zh-CN", "en"]
    }


def test_strip_thresholds_are_closed_vocabularies_with_defaults():
    effective = effective_preferences({"strip_outage_gwh_d": "100"}, {"strip_quiet_line": "off"})
    assert effective["strip_outage_gwh_d"] == "100"  # organisation default
    assert effective["strip_outage_share_pct"] == "50"  # built in
    assert effective["strip_price_move_pct"] == "5"
    assert effective["strip_quiet_line"] == "off"  # personal
    assert effective["strip_focus_hubs"] == ""
    assert validate_preferences({"strip_outage_gwh_d": "25", "strip_price_move_pct": "10"}) == {
        "strip_outage_gwh_d": "25",
        "strip_price_move_pct": "10",
    }


@pytest.mark.parametrize(
    "values",
    [
        {"strip_outage_gwh_d": "37"},
        {"strip_outage_gwh_d": 50},
        {"strip_outage_share_pct": "100"},
        {"strip_price_move_pct": "-5"},
        {"strip_quiet_line": "maybe"},
        {"strip_focus_hubs": "TTF,XYZ"},
        {"strip_focus_hubs": "TTF,TTF"},
        {"strip_focus_hubs": "TTF,NBP,THE,PEG,ZTP,PSV,CEGH"},
        {"strip_focus_hubs": ["TTF"]},
        {"strip_hidden": "not an entry"},
        {"strip_hidden": "\n".join(f"outage:e{n}@active|1" for n in range(41))},
        {"strip_threshold": "50"},
    ],
)
def test_strip_preferences_refuse_values_and_keys_outside_their_rules(values):
    with pytest.raises(SettingsError):
        validate_preferences(values)


def test_focus_hubs_and_the_hide_list_accept_bounded_lists():
    assert validate_preferences({"strip_focus_hubs": "NBP,TTF"}) == {"strip_focus_hubs": "NBP,TTF"}
    assert validate_preferences({"strip_focus_hubs": ""}) == {"strip_focus_hubs": ""}
    hidden = "outage:demo-umm-1@active|563|1\ncredit:CP-1@breach|105"
    assert validate_preferences({"strip_hidden": hidden}) == {"strip_hidden": hidden}


def test_the_hide_list_is_personal_never_an_organisation_default():
    with pytest.raises(SettingsError):
        validate_organisation_defaults({"strip_hidden": "outage:x@active"})
    assert validate_organisation_defaults({"strip_outage_share_pct": "75"}) == {
        "strip_outage_share_pct": "75"
    }
    # A stray stored row cannot leak one person's hide list to everyone.
    assert effective_preferences({"strip_hidden": "outage:x@a"}, {})["strip_hidden"] == ""


def test_display_preferences_are_closed_vocabularies_with_defaults():
    assert BUILT_IN_DEFAULTS["reporting_currency"] == "EUR"
    assert BUILT_IN_DEFAULTS["energy_unit"] == "MWh"
    assert validate_preferences({"reporting_currency": "CNY", "energy_unit": "th"}) == {
        "reporting_currency": "CNY",
        "energy_unit": "th",
    }
    for values in ({"reporting_currency": "BTC"}, {"energy_unit": "Sm3"}, {"energy_unit": "mwh"}):
        with pytest.raises(SettingsError):
            validate_preferences(values)
