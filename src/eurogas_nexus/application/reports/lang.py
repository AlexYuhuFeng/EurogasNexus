"""The language a report is written in: English or Chinese, chosen per report.

The engine sets the language for the time it builds one report (:func:`writing`); every rule
template picks its wording with :func:`T` (English, Chinese) and the shared phrase helpers in
``commentary.py`` (dates, moves, the simulated mark) follow it. Figures, units, hub and
contract names never change with the language.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_LANG: ContextVar[str] = ContextVar("report_language", default="en")


def current() -> str:
    return _LANG.get()


def zh() -> bool:
    return _LANG.get() == "zh-CN"


def T(en: str, zh_text: str) -> str:  # noqa: N802 - reads as a template marker
    """The wording in the report's language."""

    return zh_text if zh() else en


@contextmanager
def writing(language: str | None):
    """Write the report in ``language`` (``zh-CN`` or English) inside the block."""

    token = _LANG.set("zh-CN" if str(language or "").lower().startswith("zh") else "en")
    try:
        yield
    finally:
        _LANG.reset(token)


#: Country codes as the text names them.
COUNTRIES = {
    "en": {"FR": "French", "NL": "Dutch", "GB": "British", "BE": "Belgian", "DE": "German",
           "DE_LU": "German", "IT": "Italian", "ES": "Spanish", "PL": "Polish", "DK": "Danish",
           "NO": "Norwegian"},
    "zh-CN": {"FR": "法国", "NL": "荷兰", "GB": "英国", "BE": "比利时", "DE": "德国",
              "DE_LU": "德国", "IT": "意大利", "ES": "西班牙", "PL": "波兰", "DK": "丹麦",
              "NO": "挪威"},
}


def country(code: str) -> str:
    return COUNTRIES[current()].get(str(code).upper(), str(code))


__all__ = ["COUNTRIES", "T", "country", "current", "writing", "zh"]
