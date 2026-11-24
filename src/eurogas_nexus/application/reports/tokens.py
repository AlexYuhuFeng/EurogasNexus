"""The design tokens a stored report draws with, mirrored from the web client's tokens.

Source: ``clients/web/src/styles/tokens.css``.

A report is one self-contained HTML file: it cannot load the web client's stylesheet, and an
e-mail client may not honour CSS variables at all. So the report carries the light-theme
values as SVG attributes (what prints and what a plain mail reader shows) and both themes as
CSS variables (what a browser shows on screen). ``tests/unit/test_report_tokens.py`` holds
these values to ``tokens.css``, so the two cannot drift.
"""

from __future__ import annotations

#: Light theme (print, e-mail, default screen).
LIGHT: dict[str, str] = {
    "bg": "#f7f7f8",
    "surface": "#ffffff",
    "surface-2": "#f4f4f5",
    "border-subtle": "#efeff1",
    "border": "#e4e4e7",
    "text-1": "#18181b",
    "text-2": "#52525b",
    "text-3": "#5f5f68",
    "accent": "#1d4ed8",
    "positive": "#166534",
    "negative": "#b91c1c",
    "status-watch": "#854d0e",
    "status-watch-soft": "#fcf3e3",
    "status-breach": "#b91c1c",
    "status-breach-soft": "#fdeded",
    "status-info": "#1d4ed8",
    "status-info-soft": "#e8eefc",
    "status-simulated": "#6d28d9",
    "status-simulated-soft": "#f1ebfd",
    "status-stale": "#52525b",
    "status-stale-soft": "#ededf0",
    "series-1": "#1d4ed8",
    "series-2": "#0f766e",
    "series-3": "#b45309",
    "series-4": "#641f29",
    "series-5": "#7c3aed",
    "series-6": "#4d7c0f",
    "series-7": "#0369a1",
    "series-8": "#52525b",
}

#: Dark theme (screen only, under ``prefers-color-scheme: dark``).
DARK: dict[str, str] = {
    "bg": "#0b0b0d",
    "surface": "#131316",
    "surface-2": "#1a1a1e",
    "border-subtle": "#1f1f23",
    "border": "#2a2a30",
    "text-1": "#f4f4f5",
    "text-2": "#a8a8b3",
    "text-3": "#9393a0",
    "accent": "#6ea8fe",
    "positive": "#4ade80",
    "negative": "#f87171",
    "status-watch": "#fbbf24",
    "status-watch-soft": "#2a2110",
    "status-breach": "#f87171",
    "status-breach-soft": "#2e1616",
    "status-info": "#6ea8fe",
    "status-info-soft": "#172338",
    "status-simulated": "#c4b5fd",
    "status-simulated-soft": "#221b35",
    "status-stale": "#a8a8b3",
    "status-stale-soft": "#232328",
    "series-1": "#6ea8fe",
    "series-2": "#2dd4bf",
    "series-3": "#fbbf24",
    "series-4": "#dd3858",
    "series-5": "#a78bfa",
    "series-6": "#a3e635",
    "series-7": "#38bdf8",
    "series-8": "#a8a8b3",
}

#: The interface face (system fonts only: a report loads no font).
FONT = (
    'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", '
    'Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif'
)
SERIES = 8


def css_variables() -> str:
    """``:root`` variables for both themes (``--r-<name>``)."""

    light = "".join(f"--r-{name}:{value};" for name, value in LIGHT.items())
    dark = "".join(f"--r-{name}:{value};" for name, value in DARK.items())
    return (
        f":root{{color-scheme:light dark;{light}}}"
        f"@media screen and (prefers-color-scheme: dark){{:root{{{dark}}}}}"
    )
