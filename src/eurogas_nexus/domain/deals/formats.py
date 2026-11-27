"""Deal file formats and the ETRM sheet layout as editable TOML files.

A format file says how one export layout maps to the canonical deal record: which column
holds each field (a list of accepted header spellings), how its values read (``B`` is a buy,
``Dutch TTF`` is TTF), the defaults for what the layout never states (an exchange deal is
cleared), and the number and date conventions. It is plain text with comments, so a desk
member edits it in a text editor; ``scripts/ops/check_deal_format.py`` reads a sample file
with it and lists every row it could not read.

Where the files live:

- the built-in files ship with the application in ``eurogas_nexus/reference_data/deal_formats``;
- a desk's own copies go in the folder named by ``EUROGAS_NEXUS_DEAL_FORMATS_DIR``; a file there
  with the same ``name`` replaces the built-in one, and a new name adds a format. No code
  changes, no rebuild.

格式文件（TOML，可加注释）：列映射、取值映射、默认值与数字日期约定；桌面副本放在
``EUROGAS_NEXUS_DEAL_FORMATS_DIR`` 指定的文件夹，同名覆盖内置文件。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eurogas_nexus.domain.deals.record import FIELDS

FORMATS_DIR_ENV = "EUROGAS_NEXUS_DEAL_FORMATS_DIR"
BUILTIN_DIR = Path(__file__).resolve().parents[2] / "reference_data" / "deal_formats"
#: The layout file of the ETRM entry sheet (a different shape: see ``sheet.py``).
SHEET_FILE = "etrm_entry_sheet.toml"
#: Code hooks a format may name for what a mapping cannot say; ``mapped_csv`` has none.
ADAPTERS = ("mapped_csv", "eex", "ice")
MAX_FORMAT_BYTES = 256 * 1024


class FormatError(ValueError):
    """A format file that cannot be used, with what to change."""


@dataclass(frozen=True)
class DealFormat:
    name: str
    title: str
    venue: str
    provenance: str
    adapter: str
    columns: dict[str, tuple[str, ...]]
    values: dict[str, dict[str, str]]
    defaults: dict[str, str]
    lot_sizes: dict[str, str]
    detect: tuple[str, ...]
    delimiter: str = ","
    decimal_separator: str = "."
    thousands_separator: str = ","
    header_line: int = 1
    timezone: str = "Europe/Amsterdam"
    date_formats: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%d.%m.%Y")
    datetime_formats: tuple[str, ...] = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
    end_inclusive: bool = True
    source_path: str = ""
    #: Whether the layout is checked against real files of the desk (``verified = true``).
    verified: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def header_for(self, canonical: str, headers: list[str]) -> str | None:
        """The file's header that holds ``canonical`` (case and spacing ignored)."""

        wanted = [_norm(name) for name in self.columns.get(canonical, ())]
        by_norm = {_norm(name): name for name in headers}
        for name in wanted:
            if name in by_norm:
                return by_norm[name]
        return None

    def mapped(self, canonical: str, raw: str) -> str:
        """``raw`` through the value table of ``canonical`` (unchanged when not listed)."""

        table = self.values.get(canonical) or {}
        if not table:
            return raw
        key = _norm(raw)
        for source, target in table.items():
            if _norm(source) == key:
                return target
        return raw

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "venue": self.venue,
            "provenance": self.provenance,
            "verified": self.verified,
            "adapter": self.adapter,
            "columns": {key: list(value) for key, value in self.columns.items()},
            "defaults": dict(self.defaults),
            "detect": list(self.detect),
            "source_path": self.source_path,
            "notes": list(self.notes),
        }


def _norm(text: str) -> str:
    return " ".join(str(text or "").replace("﻿", "").split()).casefold()


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise FormatError(f"{where}: give a header name or a list of header names")


def parse_format(text: str, *, source_path: str = "") -> DealFormat:
    """One format from the text of its TOML file; raises :class:`FormatError`."""

    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FormatError(f"{source_path or 'format'}: not valid TOML ({exc})") from exc
    where = source_path or str(raw.get("name") or "format")
    for key in ("name", "title", "venue"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise FormatError(f"{where}: '{key}' is required")
    adapter = str(raw.get("adapter") or "mapped_csv")
    if adapter not in ADAPTERS:
        raise FormatError(f"{where}: adapter must be one of {', '.join(ADAPTERS)}")
    columns_raw = raw.get("columns") or {}
    if not isinstance(columns_raw, dict):
        raise FormatError(f"{where}: [columns] must be a table")
    unknown = sorted(set(columns_raw) - set(FIELDS))
    if unknown:
        raise FormatError(
            f"{where}: [columns] names fields that do not exist: {', '.join(unknown)}; "
            f"the fields are {', '.join(FIELDS)}"
        )
    columns = {
        key: _strings(value, f"{where}: columns.{key}") for key, value in columns_raw.items()
    }
    defaults = {str(k): str(v) for k, v in (raw.get("defaults") or {}).items()}
    bad_defaults = sorted(set(defaults) - set(FIELDS))
    if bad_defaults:
        raise FormatError(f"{where}: [defaults] names unknown fields: {', '.join(bad_defaults)}")
    for needed in ("venue_trade_id", "side", "volume", "price"):
        if needed not in columns:
            raise FormatError(f"{where}: [columns] must say which column holds '{needed}'")
    if "hub" not in columns and "hub" not in defaults:
        raise FormatError(f"{where}: map a 'hub' column or give a default hub")
    if "product" not in columns and not {"delivery_start", "delivery_end"} <= set(columns):
        raise FormatError(
            f"{where}: map a 'product' column or both 'delivery_start' and 'delivery_end'"
        )
    values: dict[str, dict[str, str]] = {}
    for key, table in (raw.get("values") or {}).items():
        if key not in FIELDS or not isinstance(table, dict):
            raise FormatError(f"{where}: [values.{key}] is not a field's value table")
        values[key] = {str(k): str(v) for k, v in table.items()}
    detect = tuple(raw.get("detect") or ())
    delimiter = str(raw.get("delimiter") or ",")
    if delimiter == "\\t":
        delimiter = "\t"
    if len(delimiter) != 1:
        raise FormatError(f"{where}: delimiter must be one character")
    return DealFormat(
        name=raw["name"].strip(),
        title=raw["title"].strip(),
        venue=raw["venue"].strip().upper(),
        provenance=str(raw.get("provenance") or ""),
        adapter=adapter,
        columns=columns,
        values=values,
        defaults=defaults,
        lot_sizes={str(k).upper(): str(v) for k, v in (raw.get("lot_sizes") or {}).items()},
        detect=tuple(str(item) for item in detect),
        delimiter=delimiter,
        decimal_separator=str(raw.get("decimal_separator") or "."),
        thousands_separator=str(raw.get("thousands_separator", ",")),
        header_line=max(1, int(raw.get("header_line") or 1)),
        timezone=str(raw.get("timezone") or "Europe/Amsterdam"),
        date_formats=tuple(raw.get("date_formats") or DealFormat.date_formats),
        datetime_formats=tuple(raw.get("datetime_formats") or DealFormat.datetime_formats),
        end_inclusive=bool(raw.get("end_inclusive", True)),
        source_path=source_path,
        verified=bool(raw.get("verified", False)),
        notes=tuple(str(item) for item in raw.get("notes") or ()),
    )


def format_dirs(environ: dict[str, str] | None = None) -> list[Path]:
    """Built-in folder first, then the desk's own (which wins on a shared name)."""

    env = os.environ if environ is None else environ
    dirs = [BUILTIN_DIR]
    custom = (env.get(FORMATS_DIR_ENV) or "").strip()
    if custom:
        dirs.append(Path(custom))
    return dirs


def load_formats(environ: dict[str, str] | None = None) -> tuple[dict[str, DealFormat], list[str]]:
    """Every usable format by name, and a line per file that could not be read."""

    formats: dict[str, DealFormat] = {}
    errors: list[str] = []
    for folder in format_dirs(environ):
        if not folder.is_dir():
            if folder != BUILTIN_DIR:
                errors.append(f"{folder}: folder not found")
            continue
        for path in sorted(folder.glob("*.toml")):
            if path.name == SHEET_FILE:
                continue
            try:
                if path.stat().st_size > MAX_FORMAT_BYTES:
                    raise FormatError(f"{path.name}: larger than {MAX_FORMAT_BYTES} bytes")
                found = parse_format(path.read_text(encoding="utf-8"), source_path=str(path))
            except (OSError, UnicodeDecodeError, FormatError) as exc:
                errors.append(str(exc))
                continue
            formats[found.name] = found
    return formats, errors


def detect_format(headers: list[str], formats: dict[str, DealFormat]) -> DealFormat | None:
    """The format whose ``detect`` headers are all present (the most specific one wins)."""

    present = {_norm(name) for name in headers}
    best: tuple[int, DealFormat] | None = None
    for item in formats.values():
        if not item.detect:
            continue
        if all(_norm(name) in present for name in item.detect):
            score = len(item.detect)
            if best is None or score > best[0]:
                best = (score, item)
    return best[1] if best else None


def sheet_layout_path(environ: dict[str, str] | None = None) -> Path:
    """The ETRM entry sheet layout: the desk's copy when there is one, else the built-in."""

    for folder in reversed(format_dirs(environ)):
        candidate = folder / SHEET_FILE
        if candidate.is_file():
            return candidate
    return BUILTIN_DIR / SHEET_FILE
