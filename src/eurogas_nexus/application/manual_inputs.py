"""Which inputs of a calculation were entered by hand (AGENTS.md rule 19, backend audit O7).

Every calculation result states ``meta.manual_inputs``: a list of
``{name, value, unit, entered_by, entered_at}``, empty when every input came from live,
public or firm records. Before this each calculation said it its own way (``inputs:
["manual"]`` on the forward balance, ``basis: "entered"`` on gas-day bands, "entered by hand"
texts on pipeline supplies) or not at all, so a client could not show it in one place.

One builder, two sources:

- :func:`from_request_body`: the fields the caller set in a request body (pydantic's
  ``model_fields_set``: what was typed, not the model's defaults), with units from the field
  name (``market_price_eur_mwh`` → ``EUR/MWh``) unless given;
- :func:`manual_input`: one value a calculation took from a hand entry it read (a firm
  override stored with who and when).

:func:`attach` writes the list to an envelope's ``meta``. A route wires it in one line::

    return attach(_envelope(result), from_request_body(body, request))
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

#: Field-name endings to the unit they state (longest first).
_UNIT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_usd_mmbtu", "USD/MMBtu"),
    ("_eur_mwh", "EUR/MWh"),
    ("_gbp_mwh", "GBP/MWh"),
    ("_usd_mwh", "USD/MWh"),
    ("_p_th", "GBp/th"),
    ("_eur_t", "EUR/t"),
    ("_mcm_d", "mcm/d"),
    ("_gwh_d", "GWh/d"),
    ("_mwh_d", "MWh/d"),
    ("_mmbtu", "MMBtu"),
    ("_mwh", "MWh"),
    ("_gwh", "GWh"),
    ("_twh", "TWh"),
    ("_mcm", "mcm"),
    ("_km", "km"),
    ("_pct", "%"),
    ("_percent", "%"),
    ("_days", "d"),
    ("_hours", "h"),
    ("_eur", "EUR"),
    ("_usd", "USD"),
    ("_gbp", "GBP"),
    ("_c", "°C"),
)

#: Request fields that are identifiers or choices, not figures entered for the calculation.
_NOT_INPUTS = frozenset(
    {
        "route_name", "from_node_id", "to_node_id", "from_market", "to_market", "fx_pair",
        "currency", "unit", "model_version", "language", "model", "book_id", "contract_id",
        "cargo_id", "hub", "hubs", "description", "note", "reason", "label", "name",
    }
)


def unit_for(name: str) -> str | None:
    """The unit a field name states, or None."""

    lowered = name.casefold()
    for suffix, unit in _UNIT_SUFFIXES:
        if lowered.endswith(suffix):
            return unit
    return None


def _json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump())
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def manual_input(
    name: str,
    value: Any,
    unit: str | None = None,
    *,
    entered_by: str | None = None,
    entered_at: datetime | str | None = None,
) -> dict[str, Any]:
    """One input entered by hand."""

    at = entered_at.astimezone(UTC).isoformat() if isinstance(entered_at, datetime) else entered_at
    return {
        "name": name,
        "value": _json_value(value),
        "unit": unit if unit is not None else unit_for(name),
        "entered_by": entered_by,
        "entered_at": at,
    }


def _caller_name(request: Any) -> str | None:
    identity = getattr(getattr(request, "state", None), "identity", None)
    for attribute in ("principal_id", "name", "principal"):
        value = getattr(identity, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def from_request_body(
    body: Any,
    request: Any = None,
    *,
    units: Mapping[str, str] | None = None,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] = (),
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The fields the caller set in ``body`` (a pydantic model), as manual inputs.

    ``include`` limits the list to those fields (a body that mixes record choices and typed
    figures); ``exclude`` drops some; ``units`` overrides the unit read from a name.
    """

    wanted = set(include) if include is not None else None
    skipped = _NOT_INPUTS | set(exclude)
    who = _caller_name(request)
    at = (now or datetime.now(UTC)).isoformat()
    out: list[dict[str, Any]] = []

    def walk(model: Any, prefix: str, top: bool) -> None:
        fields_set = getattr(model, "model_fields_set", None)
        names = sorted(fields_set) if fields_set is not None else sorted(dict(model or {}))
        for name in names:
            if top and wanted is not None and name not in wanted:
                continue
            if name in skipped or name.endswith(("_id", "_ids")):
                continue
            value = getattr(model, name, None) if fields_set is not None else model.get(name)
            if value is None or value == [] or value == {}:
                continue
            label = f"{prefix}{name}"
            # A list or map of nested models (cargoes, terminal inputs): each item's own
            # typed fields, named by its key or its identifier.
            items = (
                list(value.items()) if isinstance(value, Mapping)
                else list(enumerate(value)) if isinstance(value, list | tuple) else None
            )
            if items and all(hasattr(item, "model_fields_set") for _key, item in items):
                for key, item in items:
                    ident = next(
                        (
                            getattr(item, field)
                            for field in type(item).model_fields
                            if (field == "id" or field.endswith("_id"))
                            and getattr(item, field, None)
                        ),
                        key,
                    )
                    walk(item, f"{label}[{ident}].", False)
                continue
            if hasattr(value, "model_fields_set"):
                walk(value, f"{label}.", False)
                continue
            # Figures, not choices: a number, an instant, a top-level flag, or a field the
            # route named; a hub code, a TSO name or a mode is a choice, not an entry.
            named = top and wanted is not None and name in wanted
            figure = (isinstance(value, int | float) and not isinstance(value, bool)) or (
                isinstance(value, datetime | date)
            )
            if not (figure or named or (top and isinstance(value, bool))):
                continue
            unit = (units or {}).get(name)
            out.append(manual_input(label, value, unit, entered_by=who, entered_at=at))
            if unit is None:
                out[-1]["unit"] = unit_for(name)

    walk(body, "", True)
    return out


def attach(envelope: dict[str, Any], inputs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Write ``meta.manual_inputs`` (an empty list when nothing was entered by hand)."""

    meta = envelope.setdefault("meta", {})
    meta["manual_inputs"] = [dict(item) for item in inputs]
    return envelope
