"""Move pre-design-system stylesheets onto the design system (idempotent).

For every CSS file under clients/web/src except styles/design-system.css:

- wrap the file in ``@layer legacy { ... }`` so design-system layers win without
  specificity fights (docs/ux/DESIGN_SYSTEM.md);
- snap literal font sizes to the type scale and weights to 400/500/600;
- replace monospace label stacks with the interface font and drop forced uppercase;
- replace the most common hard-coded colours with the tokens they meant.

Run: python scripts/ui/migrate_legacy_css.py [--check]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "clients" / "web" / "src"
SKIP = {ROOT / "styles" / "design-system.css"}
MARKER = "@layer legacy {"


def _size_token(px: float) -> str:
    for limit, token in (
        (11.5, "xs"),
        (12.75, "sm"),
        (13.5, "base"),
        (14.5, "md"),
        (16.5, "lg"),
        (19, "xl"),
        (24, "2xl"),
    ):
        if px <= limit:
            return f"var(--ds-text-{token})"
    return "var(--ds-text-3xl)"


_WEIGHTS = {"300": "400", "650": "600", "700": "600", "800": "600", "900": "600", "bold": "600"}

_COLOR_PROPS_TEXT = ("color",)
_TEXT_GREY = {"#5b6472", "#58657a", "#5e6b75", "#6f6f6f", "#667085", "#64748b"}
_TEXT_DARK = {"#182026", "#171717", "#18202f", "#111827"}
_BORDER = {"#d8dde5", "#d7dde6", "#d7e0e5", "#e6ebf1", "#d8dee6", "#ebebeb", "#e5e7eb"}
_ACCENT = {"#0b63ce", "#0070f3", "#0f766e"}
_POSITIVE = {"#1c8a4c", "#176e3e"}
_NEGATIVE = {"#b42318", "#9b2c22"}
_WARNING = {"#b7791f", "#b66a19", "#92400e"}
_RGB_FAMILIES = {
    "15 118 110": "--ds-accent",
    "0 112 243": "--ds-accent",
    "180 83 9": "--ds-warning",
    "28 138 76": "--ds-positive",
    "180 35 24": "--ds-negative",
}


def _color(prop: str, value: str) -> str:
    def hex_sub(match: re.Match) -> str:
        code = match.group(0).lower()
        if prop == "color" and code in _TEXT_GREY:
            return "var(--ds-text-2)"
        if prop == "color" and code in _TEXT_DARK:
            return "var(--ds-text-1)"
        if prop.startswith(("border", "outline")) and code in _BORDER:
            return "var(--ds-border)"
        if prop.startswith("background") and code in {"#ffffff", "#fff"}:
            return "var(--ds-surface)"
        if code in _ACCENT:
            return "var(--ds-accent)"
        if code in _POSITIVE:
            return "var(--ds-positive)"
        if code in _NEGATIVE:
            return "var(--ds-negative)"
        if code in _WARNING:
            return "var(--ds-warning)"
        return match.group(0)

    value = re.sub(r"#[0-9a-fA-F]{3,8}\b", hex_sub, value)

    def rgb_sub(match: re.Match) -> str:
        token = _RGB_FAMILIES.get(match.group(1).strip())
        if not token:
            return match.group(0)
        return f"color-mix(in srgb, var({token}) {match.group(2)}, transparent)"

    return re.sub(r"rgb\(\s*(\d+ \d+ \d+)\s*/\s*(\d+%)\s*\)", rgb_sub, value)


_DECL = re.compile(r"^(\s*)([a-z-]+)(\s*:\s*)([^;{}]+)(;?)\s*$")
_MONO = re.compile(r"ui-monospace,\s*SFMono-Regular[^;]*")


def migrate(text: str) -> str:
    body = text
    if body.lstrip().startswith(MARKER):
        inner = body.lstrip()[len(MARKER) :]
        body = inner[: inner.rstrip().rfind("}")]
    out = []
    for line in body.splitlines():
        match = _DECL.match(line)
        if not match:
            # Continuation lines of multi-line declarations (font stacks, colour lists).
            out.append(_MONO.sub("var(--ds-font-ui)", line))
            continue
        indent, prop, colon, value, semi = match.groups()
        value = value.rstrip()
        if prop == "text-transform" and value == "uppercase":
            continue
        if prop == "font-size":
            px = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
            if px:
                value = _size_token(float(px.group(1)))
        elif prop == "font-weight" and value in _WEIGHTS:
            value = _WEIGHTS[value]
        elif prop == "font-family":
            value = _MONO.sub("var(--ds-font-ui)", value)
        elif "color" in prop or prop.startswith(
            ("background", "border", "outline", "fill", "stroke")
        ):
            value = _color(prop, value)
        out.append(f"{indent}{prop}{colon}{value}{semi or ';'}")
    joined = "\n".join(out).strip("\n")
    return f"{MARKER}\n{joined}\n}}\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path in sorted(ROOT.rglob("*.css")):
        if path in SKIP:
            continue
        original = path.read_text(encoding="utf-8")
        updated = migrate(original)
        if updated != original:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(updated, encoding="utf-8")
    if check and stale:
        print("not migrated:", *stale, sep="\n  ")
        return 1
    print(f"{'checked' if check else 'migrated'} {len(stale)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
