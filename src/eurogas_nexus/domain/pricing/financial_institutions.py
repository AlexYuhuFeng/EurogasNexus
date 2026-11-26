"""The firm's financial institutions as rate sources: one entry per bank (TAR-2, ADR 38).

The organisation setting ``financial_institutions`` maps an institution key (``ABCBANK``: up to
twelve capital letters or digits) to its terms::

    {"ABCBANK": {"name": "ABC Bank plc", "contracted": true, "provides": ["fx", "interest"],
                 "access": "file", "agreement_recorded": false, "contexts": ["lng_demurrage"],
                 "max_age_days": 3}}

* ``contracted``: the firm converts or finances with this bank on agreed terms, so its rates
  are the ``contracted_bank`` tier; an institution that is not contracted is held for
  reference and never used first.
* ``provides``: ``fx`` and/or ``interest``.
* ``access``: ``file`` (the firm's export imported through ``bank.fx_rates.v1`` /
  ``bank.interest_rates.v1``), ``manual`` (a person types the rates into a file of the same
  shape) or ``api`` (a live feed from the bank's API). ``api`` is accepted only with
  ``agreement_recorded`` true, because a live feed needs the firm's own agreement with the
  bank and the firm's own credentials. The credentials and the bank's endpoint configuration
  are the deployment's (environment or key file, or the encrypted credential store), never
  this setting. One bank has a connector in this build: Société Générale, key ``SOCGEN``
  (``ingestion/connectors/socgen.py``, source ``src-bank-socgen``, off by default), which
  fetches only with the agreement recorded, the endpoint configuration and the credentials in
  place, and otherwise reports "not connected" without a network call. An ``api`` entry for
  any other bank stays unconnected; use the file import.
* ``contexts`` (optional): the calculations this bank's rates apply to (none listed: all).
* ``max_age_days`` (optional, 1 to 31): how old a fixing may be before it is stale.

Rates imported for an institution carry ``source_system`` ``BANK:<KEY>``.

TAR-2：企业的结算或开户银行作为汇率与利率来源，按机构配置；实时接口须企业自有协议与凭据，
本版本仅提供法国兴业银行（SOCGEN）连接器，默认关闭，其他银行经文件导入。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SETTING = "financial_institutions"
SOURCE_PREFIX = "BANK:"
ACCESS = ("file", "manual", "api")
PROVIDES = ("fx", "interest")
DEFAULT_MAX_AGE_DAYS = 5
_KEY = re.compile(r"^[A-Z0-9]{2,12}$")
_CONTEXT = re.compile(r"^[a-z0-9_]{1,48}$")

#: The one institution key with a live-feed connector in this build (Société Générale).
CONNECTED_INSTITUTIONS = ("SOCGEN",)

LIVE_FEED_TERMS = (
    "A live feed from a bank's API needs the firm's own agreement with that bank "
    "(agreement_recorded) and the firm's own credentials, held in the deployment, never in "
    "this setting. Only Societe Generale (SOCGEN) has a connector in this build, off until it "
    "is configured; other banks' rates come in through the file import."
)


class InstitutionError(ValueError):
    """A ``financial_institutions`` entry the platform cannot use."""


@dataclass(frozen=True)
class Institution:
    key: str
    name: str
    contracted: bool
    provides: tuple[str, ...]
    access: str
    agreement_recorded: bool
    contexts: tuple[str, ...] = ()
    max_age_days: int = DEFAULT_MAX_AGE_DAYS

    @property
    def source_system(self) -> str:
        return f"{SOURCE_PREFIX}{self.key}"

    def applies(self, quantity: str, context: str = "") -> bool:
        return quantity in self.provides and (not self.contexts or context in self.contexts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "contracted": self.contracted,
            "provides": list(self.provides),
            "access": self.access,
            "agreement_recorded": self.agreement_recorded,
            "contexts": list(self.contexts),
            "max_age_days": self.max_age_days,
            "source_system": self.source_system,
            "live_feed": _live_feed(self),
        }


def _live_feed(institution: Institution) -> str | None:
    if institution.access != "api":
        return None
    if institution.key in CONNECTED_INSTITUTIONS:
        return (
            "connector available (src-bank-socgen): fetches only with the deployment's endpoint "
            "configuration and the firm's own credentials; not connected until they are set"
        )
    return "not connected (no connector for this bank in this build; use the file import)"


def source_system(key: str) -> str:
    return f"{SOURCE_PREFIX}{key.upper()}"


def validate_institutions(values: Any) -> dict[str, dict[str, Any]]:
    """The setting as stored: every entry checked, normalised, with no credential in it."""

    if not isinstance(values, Mapping):
        raise InstitutionError(f"{SETTING} must map an institution key to its terms")
    out: dict[str, dict[str, Any]] = {}
    for raw_key, terms in values.items():
        key = str(raw_key)
        if not _KEY.match(key):
            raise InstitutionError(f"{key!r}: a key is 2 to 12 capital letters or digits")
        if terms is None:  # removes the institution on a merge
            out[key] = None  # type: ignore[assignment]
            continue
        if not isinstance(terms, Mapping):
            raise InstitutionError(f"{key}: the terms must be an object")
        unknown = set(terms) - {
            "name", "contracted", "provides", "access", "agreement_recorded", "contexts",
            "max_age_days",
        }
        if unknown:
            raise InstitutionError(
                f"{key}: {sorted(unknown)[0]!r} is not a term (no credential is stored here)"
            )
        name = str(terms.get("name") or "").strip()
        if not name or len(name) > 120:
            raise InstitutionError(f"{key}: a name of 1 to 120 characters is required")
        provides = terms.get("provides") or []
        if (
            not isinstance(provides, (list, tuple))
            or not provides
            or any(item not in PROVIDES for item in provides)
        ):
            raise InstitutionError(f"{key}: provides is a list of {', '.join(PROVIDES)}")
        access = str(terms.get("access") or "file")
        if access not in ACCESS:
            raise InstitutionError(f"{key}: access is one of {', '.join(ACCESS)}")
        agreement = terms.get("agreement_recorded", False)
        if not isinstance(agreement, bool):
            raise InstitutionError(f"{key}: agreement_recorded is true or false")
        if access == "api" and not agreement:
            raise InstitutionError(f"{key}: {LIVE_FEED_TERMS}")
        contracted = terms.get("contracted", False)
        if not isinstance(contracted, bool):
            raise InstitutionError(f"{key}: contracted is true or false")
        contexts = terms.get("contexts") or []
        if not isinstance(contexts, (list, tuple)) or any(
            not isinstance(item, str) or not _CONTEXT.match(item) for item in contexts
        ):
            raise InstitutionError(f"{key}: contexts are calculation names (a-z, 0-9, _)")
        age = terms.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
        if not isinstance(age, int) or isinstance(age, bool) or not 1 <= age <= 31:
            raise InstitutionError(f"{key}: max_age_days is 1 to 31")
        out[key] = {
            "name": name,
            "contracted": contracted,
            "provides": list(dict.fromkeys(provides)),
            "access": access,
            "agreement_recorded": agreement,
            "contexts": list(dict.fromkeys(contexts)),
            "max_age_days": age,
        }
    return out


def institutions(setting: Any) -> list[Institution]:
    """The configured institutions; an entry that no longer validates is left out."""

    if not isinstance(setting, Mapping):
        return []
    found = []
    for key in sorted(setting):
        try:
            terms = validate_institutions({key: setting[key]})[key]
        except InstitutionError:
            continue
        if terms is None:
            continue
        found.append(
            Institution(
                key=key,
                name=terms["name"],
                contracted=terms["contracted"],
                provides=tuple(terms["provides"]),
                access=terms["access"],
                agreement_recorded=terms["agreement_recorded"],
                contexts=tuple(terms["contexts"]),
                max_age_days=terms["max_age_days"],
            )
        )
    return found


__all__ = [
    "ACCESS",
    "CONNECTED_INSTITUTIONS",
    "DEFAULT_MAX_AGE_DAYS",
    "LIVE_FEED_TERMS",
    "PROVIDES",
    "SETTING",
    "SOURCE_PREFIX",
    "Institution",
    "InstitutionError",
    "institutions",
    "source_system",
    "validate_institutions",
]
