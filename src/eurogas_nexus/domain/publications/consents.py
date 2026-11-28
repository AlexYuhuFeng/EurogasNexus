"""Written consents to use a publisher's publicly available data (owner, 2026-11-28).

The records ship as data (``reference_data/publisher_consents.toml``), not as code branches. A
publication whose website terms forbid storing it is fetched only while its publisher has a
record here **and** an administrator has not withdrawn it (the withdrawal lives in the runtime
store, ``publisher_consent_states``; see ``application/publisher_consents``).

The scope is the same for every record and is enforced, not only documented:

- publicly available data only (nothing behind a login or an account);
- the firm's own use: the firm's own authenticated users, and the daily packs to its own
  managers and risk function;
- no resale or redistribution: the source families below are "internal use only" in every
  export decision (``governance/entitlement``) and are never served to an anonymous caller
  (``security/identity``), whatever a licence record says.

Import-safe: no database, web or network import.

发布方书面同意（所有者 2026-11-28 报告）：以数据形式随产品发布；范围为公开数据、仅限本公司内部使用、
不得转售或再分发；管理员可撤回（记入审计），撤回后立即停止获取。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib import resources

CONSENT_FILE = "publisher_consents.toml"
#: The legal register's section the records are stated in.
CONSENT_SECTION = "Written consents reported by the owner, 2026-11-28"
#: How the fetched data is classed in every export decision.
INTERNAL_USE_ONLY = "internal-use-only"


@dataclass(frozen=True)
class PublisherConsent:
    """One publisher's written consent, as the owner reported it."""

    publisher_id: str
    name: str
    scope: str
    basis: str
    reported_on: date
    supersedes: str
    #: The source systems this publisher's fetched prices are stored under.
    families: tuple[str, ...] = ()

    def line(self) -> str:
        """The consent line the admin list and every fetched item carry."""

        return (f"fetched under written consent (reported {self.reported_on.isoformat()}, "
                "own use, no resale)")

    def to_json(self) -> dict:
        return {
            "publisher_id": self.publisher_id,
            "name": self.name,
            "scope": self.scope,
            "basis": self.basis,
            "reported_on": self.reported_on.isoformat(),
            "supersedes": self.supersedes,
            "families": list(self.families),
            "line": self.line(),
        }


def parse_consents(text: str) -> tuple[PublisherConsent, ...]:
    """The records of a consent file (``ValueError`` on a malformed one)."""

    data = tomllib.loads(text)
    reported = date.fromisoformat(str(data["reported_on"]))
    scope = str(data["scope"])
    basis = str(data["basis"])
    out = []
    for publisher_id, item in sorted((data.get("publisher") or {}).items()):
        out.append(PublisherConsent(
            publisher_id=str(publisher_id),
            name=str(item["name"]),
            scope=str(item.get("scope") or scope),
            basis=str(item.get("basis") or basis),
            reported_on=date.fromisoformat(str(item.get("reported_on") or reported)),
            supersedes=str(item.get("supersedes") or ""),
            families=tuple(str(f) for f in item.get("families") or ()),
        ))
    ids = [c.publisher_id for c in out]
    if len(ids) != len(set(ids)):
        raise ValueError("two consent records share a publisher id")
    return tuple(out)


@lru_cache(maxsize=1)
def publisher_consents() -> tuple[PublisherConsent, ...]:
    """The shipped consent records."""

    text = (resources.files("eurogas_nexus.reference_data") / CONSENT_FILE).read_text(
        encoding="utf-8")
    return parse_consents(text)


def publisher_consent(publisher_id: str | None) -> PublisherConsent | None:
    """One publisher's record, or ``None`` when there is none."""

    return next((c for c in publisher_consents() if c.publisher_id == publisher_id), None)


@lru_cache(maxsize=1)
def consented_source_families() -> frozenset[str]:
    """Every source system stored under a consent: internal use only, never anonymous."""

    return frozenset(f for consent in publisher_consents() for f in consent.families)


def consent_for_family(family: str | None) -> PublisherConsent | None:
    """The consent a source family's data was fetched under."""

    value = (family or "").strip()
    return next((c for c in publisher_consents() if value in c.families), None)


__all__ = [
    "CONSENT_FILE",
    "CONSENT_SECTION",
    "INTERNAL_USE_ONLY",
    "PublisherConsent",
    "consent_for_family",
    "consented_source_families",
    "parse_consents",
    "publisher_consent",
    "publisher_consents",
]
