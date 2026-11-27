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

import re
from collections.abc import Callable, Mapping
from typing import Any

from eurogas_nexus.domain.ai.register import (
    AI_ENABLED_SETTING,
    AI_FEATURES_SETTING,
    AI_SHARING_CATEGORIES,
    AI_SHARING_SETTING,
)
from eurogas_nexus.domain.ontology.markets import european_gas_hubs
from eurogas_nexus.domain.pricing.financial_institutions import SETTING as INSTITUTIONS_SETTING
from eurogas_nexus.domain.pricing.financial_institutions import (
    InstitutionError,
    validate_institutions,
)
from eurogas_nexus.domain.pricing.source_precedence import SETTING as SOURCE_PRECEDENCE_SETTING
from eurogas_nexus.domain.pricing.source_precedence import PrecedenceError, validate_orders
from eurogas_nexus.governance.four_eyes import (
    FOUR_EYES_SETTING,
    FourEyesSettingError,
    validate_four_eyes,
)

#: The interface languages the clients ship. A new language is added here and in the
#: client locale registry (clients/web/src/i18n/locales.ts) with its translation file.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "zh-CN")

#: Currencies a reader may report in: the euro and the currencies in the ECB euro reference
#: table, so every conversion has a published rate (design basis G2, L7).
REPORTING_CURRENCIES: tuple[str, ...] = (
    "EUR", "USD", "GBP", "CHF", "NOK", "SEK", "DKK", "PLN", "CZK", "HUF", "RON", "JPY",
    "CNY", "HKD", "SGD", "KRW", "INR", "AUD", "NZD", "CAD", "BRL", "MXN", "ZAR", "TRY",
    "ILS", "ISK", "IDR", "MYR", "PHP", "THB",
)  # fmt: skip

#: Energy units a reader may read secondary values in; codes of the units authority
#: (domain.ontology.quantity). Volume units need a heating value and are not offered.
ENERGY_UNITS: tuple[str, ...] = ("MWh", "th", "MMBtu", "GJ")

PREFERENCE_VOCABULARY: dict[str, tuple[str, ...]] = {
    "language": SUPPORTED_LANGUAGES,
    "theme": ("system", "light", "dark"),
    # Where Desk opens: Today (decision D1), the curves board or the network map.
    "market_view": ("overview", "curves", "network"),
    # Quote layout: hub board (hubs down) or execution-screen ladder (products down).
    "market_board_layout": ("board", "ladder"),
    # Profit colour: green (Europe, Americas), red (China and much of Asia), or blue with
    # orange loss, the colour-vision friendly scheme (UX R1).
    "pnl_colors": ("green_up", "red_up", "blue_orange"),
    # Row height (UX R11): comfortable 32 px rows, or compact 28 px for more rows above the
    # fold. Only rows change; controls, type and spacing keep their sizes.
    "density": ("comfortable", "compact"),
    # Times shown in: the device's zone, UTC, or the gas market's clock (CET/CEST). Instants are
    # stored and sent in UTC whatever this says; gas days are never shifted.
    "time_zone": ("device", "utc", "market"),
    # Display only (design basis G1-G7): the currency and energy unit of the secondary value
    # beside a native figure, and of totals across currencies. A traded price, a contract
    # term or a limit is never replaced by these; conversion is server-side and named.
    "reporting_currency": REPORTING_CURRENCIES,
    "energy_unit": ENERGY_UNITS,
    # The situational strip under the top bar (docs/product/ROLE_FIRST_REDESIGN.md, section 5):
    # an unplanned outage qualifies at or above either size; a price move at or above the share.
    "strip_outage_gwh_d": ("25", "50", "100", "200", "500"),
    "strip_outage_share_pct": ("25", "50", "75"),
    "strip_price_move_pct": ("2", "3", "5", "10"),
    # One calm standing fact when nothing is urgent (booked today, the next window, counts).
    "strip_quiet_line": ("on", "off"),
}

#: Preferences whose values are a bounded list rather than one word of a closed vocabulary.
#: Each is still refused unless every part is valid.
_HUBS = european_gas_hubs()
_HIDE_ENTRY = re.compile(r"^[a-z_]{2,16}:[A-Za-z0-9:._\-]{1,120}@[A-Za-z0-9:._|+\-]{0,80}$")
MAX_FOCUS_HUBS = 6
MAX_HIDDEN_ITEMS = 40


def _focus_hubs(value: str) -> bool:
    """Comma-separated hub codes the strip follows; empty means the book's hubs."""

    if value == "":
        return True
    hubs = value.split(",")
    return len(hubs) <= MAX_FOCUS_HUBS and len(set(hubs)) == len(hubs) and set(hubs) <= set(_HUBS)


def _hidden_items(value: str) -> bool:
    """Strip items the person hid, ``id@signature`` separated by newlines."""

    if value == "":
        return True
    entries = value.split("\n")
    return len(entries) <= MAX_HIDDEN_ITEMS and all(_HIDE_ENTRY.match(entry) for entry in entries)


_HINT_ID = re.compile(r"^[a-z][a-z0-9_.\-]{1,63}$")
MAX_HINTS_SEEN = 120


def _hints_seen(value: str) -> bool:
    """First-use hints the person dismissed (design basis H.1): comma-separated hint ids."""

    if value == "":
        return True
    ids = value.split(",")
    return len(ids) <= MAX_HINTS_SEEN and len(set(ids)) == len(ids) and all(
        _HINT_ID.match(item) for item in ids
    )


PREFERENCE_PATTERNS: dict[str, tuple[Callable[[str], bool], str]] = {
    "strip_focus_hubs": (
        _focus_hubs,
        f"comma-separated hub codes ({', '.join(_HUBS)}), at most {MAX_FOCUS_HUBS}, or empty",
    ),
    "strip_hidden": (_hidden_items, f"at most {MAX_HIDDEN_ITEMS} id@signature lines"),
    "hints_seen": (_hints_seen, f"at most {MAX_HINTS_SEEN} comma-separated hint ids"),
}

#: A person's own record, never an organisation default (which items they hid).
PERSONAL_ONLY_KEYS: frozenset[str] = frozenset({"strip_hidden", "hints_seen"})

BUILT_IN_DEFAULTS: dict[str, str] = {
    "language": "en",
    # Light by default (SMALL_DESK_PLAN section 9); dark and the device's choice stay a click away.
    "theme": "light",
    "market_view": "overview",
    "market_board_layout": "board",
    "pnl_colors": "green_up",
    "density": "comfortable",
    "time_zone": "device",
    "reporting_currency": "EUR",
    "energy_unit": "MWh",
    "strip_outage_gwh_d": "50",
    "strip_outage_share_pct": "50",
    "strip_price_move_pct": "5",
    "strip_quiet_line": "on",
    "strip_focus_hubs": "",
    "strip_hidden": "",
    "hints_seen": "",
}

#: Every key a client may store.
PREFERENCE_KEYS: frozenset[str] = frozenset(PREFERENCE_VOCABULARY) | frozenset(PREFERENCE_PATTERNS)


class SettingsError(ValueError):
    """A setting outside its vocabulary."""


def validate_preferences(values: Mapping[str, Any]) -> dict[str, str]:
    """Return the accepted preferences; unknown keys or values are refused, not dropped."""

    accepted: dict[str, str] = {}
    for key, value in values.items():
        if key not in PREFERENCE_KEYS:
            raise SettingsError(f"unknown preference {key!r}")
        if value is None:
            continue  # null clears a personal choice back to the organisation default
        pattern = PREFERENCE_PATTERNS.get(key)
        if pattern is not None:
            valid, described = pattern
            if not isinstance(value, str) or not valid(value):
                raise SettingsError(f"{key} must be {described}")
        else:
            allowed = PREFERENCE_VOCABULARY[key]
            if not isinstance(value, str) or value not in allowed:
                raise SettingsError(f"{key} must be one of {', '.join(allowed)}")
        accepted[key] = value
    return accepted


def validate_ai_features(values: Any) -> dict[str, bool]:
    """The per-use AI switches (GOV-1): registered uses only, each ``true`` or ``false``."""

    from eurogas_nexus.domain.ai.register import AI_USES_BY_NAME

    if not isinstance(values, Mapping) or not values:
        raise SettingsError(f"{AI_FEATURES_SETTING} must map AI uses to true or false")
    unknown = sorted(str(key) for key in values if key not in AI_USES_BY_NAME)
    if unknown:
        raise SettingsError(f"{unknown[0]} is not a registered AI use")
    if any(not isinstance(value, bool) for value in values.values()):
        raise SettingsError(f"each {AI_FEATURES_SETTING} value must be true or false")
    return {str(key): bool(value) for key, value in values.items()}


def validate_ai_sharing(values: Any) -> dict[str, bool]:
    """What the model may be sent, per category (``AI_SHARING_CATEGORIES``), each a bool."""

    if not isinstance(values, Mapping) or not values:
        raise SettingsError(f"{AI_SHARING_SETTING} must map data categories to true or false")
    unknown = sorted(str(key) for key in values if key not in AI_SHARING_CATEGORIES)
    if unknown:
        raise SettingsError(f"{unknown[0]} is not a data category the model can be sent")
    if any(not isinstance(value, bool) for value in values.values()):
        raise SettingsError(f"each {AI_SHARING_SETTING} value must be true or false")
    return {str(key): bool(value) for key, value in values.items()}


def validate_organisation_defaults(values: Mapping[str, Any]) -> dict[str, Any]:
    """Organisation defaults use the preference vocabulary plus the languages offered."""

    personal_only = sorted(PERSONAL_ONLY_KEYS & set(values))
    if personal_only:
        raise SettingsError(f"{personal_only[0]} is a personal preference, not a default")
    enabled = values.get("enabled_languages")
    switches = values.get(AI_FEATURES_SETTING)
    ai_on = values.get(AI_ENABLED_SETTING)
    sharing = values.get(AI_SHARING_SETTING)
    four_eyes = values.get(FOUR_EYES_SETTING)
    precedence = values.get(SOURCE_PRECEDENCE_SETTING)
    banks = values.get(INSTITUTIONS_SETTING)
    rest = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "enabled_languages",
            AI_FEATURES_SETTING,
            AI_ENABLED_SETTING,
            AI_SHARING_SETTING,
            FOUR_EYES_SETTING,
            SOURCE_PRECEDENCE_SETTING,
            INSTITUTIONS_SETTING,
        }
    }
    accepted: dict[str, Any] = validate_preferences(rest)
    if switches is not None:
        accepted[AI_FEATURES_SETTING] = validate_ai_features(switches)
    if ai_on is not None:
        # The administrator's one switch for every AI feature (small-desk plan 3.6).
        if not isinstance(ai_on, bool):
            raise SettingsError(f"{AI_ENABLED_SETTING} must be true or false")
        accepted[AI_ENABLED_SETTING] = ai_on
    if sharing is not None:
        accepted[AI_SHARING_SETTING] = validate_ai_sharing(sharing)
    if four_eyes is not None:
        # P-17: which reference writes need a second person (governance/four_eyes.py).
        try:
            accepted[FOUR_EYES_SETTING] = validate_four_eyes(four_eyes)
        except FourEyesSettingError as exc:
            raise SettingsError(str(exc)) from exc
    if precedence is not None:
        # TAR-2: the order of sources per quantity kind (domain/pricing/source_precedence.py).
        try:
            accepted[SOURCE_PRECEDENCE_SETTING] = validate_orders(precedence)
        except PrecedenceError as exc:
            raise SettingsError(str(exc)) from exc
    if banks is not None:
        # TAR-2: the firm's banks as FX and interest-rate sources; no credential is stored.
        try:
            accepted[INSTITUTIONS_SETTING] = validate_institutions(banks)
        except InstitutionError as exc:
            raise SettingsError(str(exc)) from exc
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
    effective.update(
        {
            k: v
            for k, v in organisation.items()
            if k in PREFERENCE_KEYS and k not in PERSONAL_ONLY_KEYS
        }
    )
    effective.update({k: v for k, v in personal.items() if k in PREFERENCE_KEYS})
    languages = list(organisation.get("enabled_languages") or SUPPORTED_LANGUAGES)
    if effective["language"] not in languages:
        effective["language"] = organisation.get("language", languages[0])
    effective["enabled_languages"] = languages
    return effective
