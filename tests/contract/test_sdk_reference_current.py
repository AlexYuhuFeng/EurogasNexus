"""The generated SDK reference matches the SDK's public surface (standard D2, E4).

A new SDK function or model without a regenerated ``docs/sdk/REFERENCE.md`` fails here; run
``python -I scripts/docs/generate_sdk_reference.py --output docs/sdk/REFERENCE.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sdk_reference_is_current() -> None:
    completed = subprocess.run(
        [sys.executable, "-I", "scripts/docs/generate_sdk_reference.py", "--check",
         "docs/sdk/REFERENCE.md"],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
