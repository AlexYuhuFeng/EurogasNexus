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
