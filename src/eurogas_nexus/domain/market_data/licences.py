"""Market-data licences held by the organisation, and the rule for granting data scopes.

Exchanges and vendors license data to the firm, not to individuals: an enterprise licence
covers everyone, a site licence the offices it names, a named-user licence a number of
seats. A data scope for a licensed source family is therefore granted by an administrator
against a licence the firm holds, never typed in by the user. The register also answers
the vendor's audit question: who had access to what, under which contract, when.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from eurogas_nexus.domain.ontology.vocabulary import LicenceType, LicensedUse


@dataclass(frozen=True)
class Licence:
    licence_id: str
    vendor: str
    source_family: str  # the data-scope family it covers, e.g. EEX, ICE_ENDEX, TRAYPORT
    licence_type: LicenceType
    use: LicensedUse
    valid_from: date
    valid_to: date | None = None
    offices: tuple[str, ...] = ()  # SITE: covered offices; empty means all for ENTERPRISE
    seats: int | None = None  # NAMED_USER: seat count
    contract_reference: str = ""

    def active_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)

    def covers_office(self, office: str | None) -> bool:
        if self.licence_type is not LicenceType.SITE:
            return True
        return bool(office) and office.upper() in {o.upper() for o in self.offices}


def validate_licence(licence: Licence) -> list[str]:
    problems = []
    if licence.valid_to is not None and licence.valid_to < licence.valid_from:
        problems.append("valid_to is before valid_from")
    if licence.licence_type is LicenceType.NAMED_USER and not (licence.seats and licence.seats > 0):
        problems.append("a named-user licence needs a positive seat count")
    if licence.licence_type is LicenceType.SITE and not licence.offices:
        problems.append("a site licence names at least one office")
    if not licence.source_family.strip():
        problems.append("source_family is required")
    return problems


def grant_problems(
    *,
    families: Iterable[str],
    office: str | None,
    licences: Iterable[Licence],
    holders: Mapping[str, int],
    public_families: Iterable[str],
    today: date,
) -> dict[str, str]:
    """Why each newly requested licensed family cannot be granted (empty when all can).

    ``holders`` counts the principals that already hold each family, excluding the one
    being granted. A family is grantable when an active licence for it covers the
    person's office and, for a named-user licence, a seat is free. The wildcard ``*`` is
    not checked here: it is reserved for service accounts and break-glass access.
    """

    public = {f.upper() for f in public_families}
    active = [lic for lic in licences if lic.active_on(today)]
    problems: dict[str, str] = {}
    for family in {f.strip().upper() for f in families if f.strip() and f.strip() != "*"}:
        if family in public:
            continue
        candidates = [lic for lic in active if lic.source_family.upper() == family]
        if not candidates:
            problems[family] = "no active licence for this source in the licence register"
            continue
        covering = [lic for lic in candidates if lic.covers_office(office)]
        if not covering:
            problems[family] = f"no licence for this source covers office {office or '(none)'}"
            continue
        if any(lic.licence_type is not LicenceType.NAMED_USER for lic in covering):
            continue
        seats = sum(lic.seats or 0 for lic in covering)
        if holders.get(family, 0) >= seats:
            problems[family] = f"all {seats} named-user seats are assigned"
    return problems
