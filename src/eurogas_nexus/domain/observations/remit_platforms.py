"""Inside-information platforms gas UMMs are exported from, and their reuse terms.

REMIT Art. 4 requires inside information to be published on an inside-information platform
(IIP). ACER's position is that an IIP must give market participants unrestricted access and
download, and that restrictions on using the published information are not consistent with
REMIT; each platform still sets its own terms of use. This register records what was
verified for each platform the desk may export from. A platform whose terms have not been
confirmed for commercial reuse can still be imported, but only after the operator confirms
the terms in writing (``--terms-confirmed``), and the confirmation is stored with the data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemitPlatform:
    """One inside-information platform and the reuse position recorded for it."""

    platform_id: str
    name: str
    url: str
    #: True once commercial reuse with attribution has been confirmed from the platform's
    #: own published statements.
    reuse_confirmed: bool
    attribution: str
    basis: str


REMIT_PLATFORMS: dict[str, RemitPlatform] = {
    platform.platform_id: platform
    for platform in (
        RemitPlatform(
            "GIE_IIP",
            "GIE Inside Information Platform",
            "https://iip.gie.eu/",
            True,
            "Source: GIE Inside Information Platform",
            "GIE states IIP data is free of charge and available for re-use and repackaging "
            "with the source credited.",
        ),
        RemitPlatform(
            "EEX_TP",
            "EEX Transparency Platform",
            "https://www.eex-transparency.com/",
            False,
            "Source: EEX Transparency Platform",
            "Public terms for commercial reuse were not found; confirm with EEX in writing.",
        ),
        RemitPlatform(
            "GASSCO_UMM",
            "Gassco UMM",
            "https://umm.gassco.no/",
            False,
            "Source: Gassco",
            "Confirm Gassco's terms for commercial reuse in writing.",
        ),
        RemitPlatform(
            "PRISMA_IIP",
            "PRISMA Inside Information Platform",
            "https://www.prisma-capacity.eu/",
            False,
            "Source: PRISMA",
            "PRISMA publishes general terms for its IIP; confirm reuse of exported UMMs.",
        ),
        RemitPlatform(
            "OTHER",
            "Other platform",
            "",
            False,
            "",
            "Unregistered platform; confirm its terms in writing before use.",
        ),
    )
}


def source_reference_for(platform_id: str, file_name: str, *, terms_confirmed: bool) -> str:
    """Provenance stored with every message: platform, file and how reuse was cleared."""

    platform = REMIT_PLATFORMS[platform_id]
    clearance = "terms-published" if platform.reuse_confirmed else "terms-confirmed-by-operator"
    if not platform.reuse_confirmed and not terms_confirmed:
        raise ValueError(
            f"{platform.name}: reuse terms are not confirmed ({platform.basis}) "
            "Pass --terms-confirmed once the platform has confirmed commercial reuse."
        )
    return f"{platform_id}:{clearance}:{file_name}"[:160]
