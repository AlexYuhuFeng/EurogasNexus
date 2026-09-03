#!/usr/bin/env python
"""Write the generated GRM Turtle rendering next to the published OWL artifact.

Usage:
    python scripts/ontology/generate_grm_ttl.py [OUTPUT_PATH]

The executable ontology in ``src/eurogas_nexus/domain/ontology/`` is the
semantic source of truth. See ``tests/contract/test_ontology_grm_parity.py``
for the mechanical parity gate that keeps the published OWL file aligned.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eurogas_nexus.domain.ontology.grm_turtle import render_grm_ttl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    output = Path(args[0]) if args else Path("docs/ontology/eurogas-nexus-grm.generated.ttl")
    output.write_text(render_grm_ttl(), encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
