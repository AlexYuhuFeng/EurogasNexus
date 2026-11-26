"""One rule decides whether a row is simulated (backend audit O1, AGENTS.md rule 17).

``domain/ontology/provenance.is_simulated`` is the rule. Hand-written checks of the
``_Sim`` suffix grew to about 50 call sites under five disagreeing rules; this ratchet
fails when a new one appears, so each later change moves a reader onto the rule instead.
Lower ``ALLOWED`` when you remove some.
"""

from __future__ import annotations

import re
from pathlib import Path

from eurogas_nexus.domain.ontology.provenance import is_simulated, is_simulated_row

ROOT = Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus"
HAND_CHECK = re.compile(r"""endswith\(["']_Sim["']\)""")
#: Hand-written suffix checks still in the code on 2026-11-26.
ALLOWED = 39


def test_no_new_hand_written_simulated_check() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in sorted(ROOT.rglob("*.py"))
        if path.name != "provenance.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if HAND_CHECK.search(line)
    ]
    assert len(found) <= ALLOWED, found


def test_the_rule() -> None:
    assert is_simulated("EEX_Sim") and is_simulated("eex_sim")
    assert is_simulated("DEMO") and is_simulated("DEMO_Sim")
    assert is_simulated("ICE_ENDEX", {"simulated": True})
    assert not is_simulated("ICE_ENDEX") and not is_simulated("GIE") and not is_simulated(None)
    assert not is_simulated("DEMOCRAT")  # a name, not the demo source
    assert is_simulated_row({"source_system": "REMIT", "metadata_json": {"simulated": True}})
