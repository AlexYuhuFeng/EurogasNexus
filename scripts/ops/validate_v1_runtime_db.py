"""Compatibility wrapper for scripts/ops/validate_runtime_db.py.

The neutral script name is now preferred:

    python scripts/ops/validate_runtime_db.py --json

This wrapper remains so older local commands and external references do not
break during the migration away from milestone-style naming.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from validate_runtime_db import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
