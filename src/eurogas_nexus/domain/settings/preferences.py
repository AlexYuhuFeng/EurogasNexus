"""Three tiers of settings and who owns each.

- **Profile** (name, role, data scopes, job functions, office): owned by the identity
  administrator or SSO; lives on the identity principal. Not edited here.
- **Organisation defaults**: owned by the platform administrator; what a new user sees
  until they choose otherwise (default language, theme, landing views, the languages
  offered).
- **Personal preferences**: owned by the user; stored per principal on the server, so
  they follow a trader from the web client to the desktop client and between offices.

Only settings that change something are accepted. Every key has a closed vocabulary, so
a stored value is always one the clients can apply. Preferences never grant authority:
they choose how permitted data is shown, not what is permitted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The interface languages the clients ship. A new language is added here and in the
#: client locale registry (clients/web/src/i18n/locales.ts) with its translation file.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "zh-CN")

PREFERENCE_VOCABULARY: dict[str, tuple[str, ...]] = {
    "language": SUPPORTED_LANGUAGES,
    "theme": ("system", "light", "dark"),
    # Market page: numeric curves board or the network map first.
    "market_view": ("curves", "network"),
    # Quote layout: hub board (hubs down) or execution-screen ladder (products down).
    "market_board_layout": ("board", "ladder"),
}

BUILT_IN_DEFAULTS: dict[str, str] = {
    "language": "en",
    "theme": "system",
    "market_view": "curves",
    "market_board_layout": "board",
}


class SettingsError(ValueError):
    """A setting outside its vocabulary."""


def validate_preferences(values: Mapping[str, Any]) -> dict[str, str]:
    """Return the accepted preferences; unknown keys or values are refused, not dropped."""

    accepted: dict[str, str] = {}
    for key, value in values.items():
        allowed = PREFERENCE_VOCABULARY.get(key)
        if allowed is None:
            raise SettingsError(f"unknown preference {key!r}")
        if value is None:
            continue  # null clears a personal choice back to the organisation default
        if not isinstance(value, str) or value not in allowed:
            raise SettingsError(f"{key} must be one of {', '.join(allowed)}")
        accepted[key] = value
    return accepted


def validate_organisation_defaults(values: Mapping[str, Any]) -> dict[str, Any]:
    """Organisation defaults use the preference vocabulary plus the languages offered."""

    enabled = values.get("enabled_languages")
    rest = {key: value for key, value in values.items() if key != "enabled_languages"}
    accepted: dict[str, Any] = validate_preferences(rest)
    if enabled is not None:
        if (
            not isinstance(enabled, list)
            or not enabled
            or any(item not in SUPPORTED_LANGUAGES for item in enabled)
        ):
            raise SettingsError(
                "enabled_languages must be a non-empty list of " + ", ".join(SUPPORTED_LANGUAGES)
            )
        accepted["enabled_languages"] = list(dict.fromkeys(enabled))
    languages = accepted.get("enabled_languages", list(SUPPORTED_LANGUAGES))
    if accepted.get("language", BUILT_IN_DEFAULTS["language"]) not in languages:
        raise SettingsError("the default language must be one of the enabled languages")
    return accepted


def effective_preferences(
    organisation: Mapping[str, Any], personal: Mapping[str, Any]
) -> dict[str, Any]:
    """Built-in defaults, overridden by the organisation, overridden by the user.

    A personal language the organisation no longer offers falls back to the
    organisation default rather than showing a language that was switched off.
    """

    effective: dict[str, Any] = dict(BUILT_IN_DEFAULTS)
    effective.update({k: v for k, v in organisation.items() if k in PREFERENCE_VOCABULARY})
    effective.update({k: v for k, v in personal.items() if k in PREFERENCE_VOCABULARY})
    languages = list(organisation.get("enabled_languages") or SUPPORTED_LANGUAGES)
    if effective["language"] not in languages:
        effective["language"] = organisation.get("language", languages[0])
    effective["enabled_languages"] = languages
    return effective
