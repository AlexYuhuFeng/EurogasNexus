"""ASGI entrypoint for the Eurogas Nexus API service."""

import sys
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from eurogas_nexus.api.app import create_app  # noqa: E402

app = create_app()

__all__ = ["app"]
