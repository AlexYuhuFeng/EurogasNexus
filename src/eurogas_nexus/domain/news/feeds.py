"""Read an RSS 2.0 or Atom feed into entries, safely and without a third-party parser.

The feed is untrusted text from the network, so before parsing: it must be at most
:data:`MAX_FEED_BYTES`, and a document type declaration or an entity declaration refuses it
whole (no entity expansion, no external entity). Markup inside a title or summary is removed
and the text is shortened to :data:`MAX_SUMMARY_CHARS`; a link must be ``http(s)``. Nothing
here fetches anything.

RSS/Atom 订阅解析：拒绝 DOCTYPE/实体声明，去除标记，截断摘要，链接必须为 http(s)。
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET  # noqa: S405 - DOCTYPE and ENTITY are refused before parse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_FEED_BYTES = 2_000_000
MAX_ENTRIES = 200
MAX_TITLE_CHARS = 400
MAX_SUMMARY_CHARS = 1_200

_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_TAG = re.compile(r"<[^>]{0,2000}>")
_CODE = re.compile(r"<(script|style)\b[^>]{0,2000}>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_SPACE = re.compile(r"\s+")


class FeedError(ValueError):
    """The document cannot be read as a feed (names why)."""


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """One entry as the feed states it."""

    guid: str
    title: str
    url: str
    summary: str
    published_at_utc: datetime | None
    language: str | None


def plain_text(value: str | None, limit: int) -> str:
    """Markup removed (scripts and styles with their content), entities decoded, white space
    collapsed, at most ``limit`` characters. Markup that decoding reveals is removed too."""

    text = html.unescape(_TAG.sub(" ", _CODE.sub(" ", value or "")))
    text = _SPACE.sub(" ", _TAG.sub(" ", _CODE.sub(" ", text))).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def _when(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            moment = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _link(value: str | None) -> str:
    text = (value or "").strip()
    return text if re.match(r"^https?://[^\s<>\"]+$", text) else ""


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def parse_feed(document: bytes | str) -> tuple[str, list[FeedEntry]]:
    """``(feed language or "", entries)`` of an RSS 2.0 or Atom document.

    Raises:
        FeedError: too large, a DOCTYPE or ENTITY declaration, not XML, or neither format.
    """

    raw = document.encode("utf-8") if isinstance(document, str) else document
    if len(raw) > MAX_FEED_BYTES:
        raise FeedError(f"feed larger than {MAX_FEED_BYTES} bytes")
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():
        raise FeedError("a feed with a DOCTYPE or ENTITY declaration is refused")
    try:
        root = ET.fromstring(raw)  # noqa: S314 - declarations refused above
    except ET.ParseError as exc:
        raise FeedError(f"not well-formed XML: {exc}") from exc
    entries: list[FeedEntry] = []
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise FeedError("RSS without a channel")
        language = _text(channel.find("language")).strip()
        for item in channel.findall("item")[:MAX_ENTRIES]:
            url = _link(_text(item.find("link")))
            guid = _text(item.find("guid")).strip() or url
            entries.append(
                FeedEntry(
                    guid=guid[:400],
                    title=plain_text(_text(item.find("title")), MAX_TITLE_CHARS),
                    url=url,
                    summary=plain_text(_text(item.find("description")), MAX_SUMMARY_CHARS),
                    published_at_utc=_when(
                        _text(item.find("pubDate")) or _text(item.find(f"{_DC}date"))
                    ),
                    language=language or None,
                )
            )
        return language, entries
    if root.tag == f"{_ATOM}feed":
        language = root.get("{http://www.w3.org/XML/1998/namespace}lang", "")
        for item in root.findall(f"{_ATOM}entry")[:MAX_ENTRIES]:
            url = ""
            for link in item.findall(f"{_ATOM}link"):
                if link.get("rel", "alternate") == "alternate":
                    url = _link(link.get("href"))
                    break
            guid = _text(item.find(f"{_ATOM}id")).strip() or url
            summary = _text(item.find(f"{_ATOM}summary")) or _text(item.find(f"{_ATOM}content"))
            entries.append(
                FeedEntry(
                    guid=guid[:400],
                    title=plain_text(_text(item.find(f"{_ATOM}title")), MAX_TITLE_CHARS),
                    url=url,
                    summary=plain_text(summary, MAX_SUMMARY_CHARS),
                    published_at_utc=_when(
                        _text(item.find(f"{_ATOM}published"))
                        or _text(item.find(f"{_ATOM}updated"))
                    ),
                    language=language or None,
                )
            )
        return language, entries
    raise FeedError(f"neither RSS 2.0 nor Atom (root {root.tag!r})")


__all__ = [
    "MAX_ENTRIES",
    "MAX_FEED_BYTES",
    "MAX_SUMMARY_CHARS",
    "MAX_TITLE_CHARS",
    "FeedEntry",
    "FeedError",
    "parse_feed",
    "plain_text",
]
