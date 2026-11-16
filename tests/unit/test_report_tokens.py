"""The report's mirrored colour tokens equal the web client's ``tokens.css`` in both themes."""

from __future__ import annotations

import re
from pathlib import Path

from eurogas_nexus.application.reports.tokens import DARK, LIGHT

TOKENS = Path(__file__).resolve().parents[2] / "clients" / "web" / "src" / "styles" / "tokens.css"


def _block(css: str, selector: str) -> dict[str, str]:
    start = css.index(selector + " {")
    body = css[start: css.index("\n}", start)]
    return dict(re.findall(r"--ds-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", body))


def test_light_and_dark_values_match_the_client_tokens():
    css = TOKENS.read_text(encoding="utf-8")
    light, dark = _block(css, ":root"), _block(css, ":root.dark")
    for name, value in LIGHT.items():
        assert light[name].lower() == value, name
    for name, value in DARK.items():
        assert dark[name].lower() == value, name
