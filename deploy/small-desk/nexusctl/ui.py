"""Plain-words output, and a log of every action for the diagnostics bundle."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


class Out:
    """Prints lines a non-specialist can read and keeps a copy in the action log.

    Never pass a secret to it: everything printed is also logged. The one-time administrator
    password is printed by the product's own account command straight to the terminal.
    """

    def __init__(self, stream: TextIO | None = None, log_path: Path | None = None) -> None:
        self.stream = stream or sys.stdout
        self.log_path = log_path
        self.problems = 0
        self.warnings = 0

    def _emit(self, text: str) -> None:
        print(text, file=self.stream, flush=True)
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                with self.log_path.open("a", encoding="utf-8") as handle:
                    for line in text.splitlines() or [""]:
                        handle.write(f"{stamp} {line}\n")
            except OSError:
                pass

    def title(self, text: str) -> None:
        self._emit(f"\n{text}\n{'-' * len(text)}")

    def step(self, text: str) -> None:
        self._emit(f"... {text}")

    def ok(self, text: str) -> None:
        self._emit(f"  OK       {text}")

    def info(self, text: str) -> None:
        self._emit(f"           {text}")

    def warn(self, text: str, todo: str | None = None) -> None:
        self.warnings += 1
        self._emit(f"  WARNING  {text}")
        if todo:
            self._emit(f"           What to do: {todo}")

    def problem(self, text: str, todo: str | None = None) -> None:
        self.problems += 1
        self._emit(f"  PROBLEM  {text}")
        if todo:
            self._emit(f"           What to do: {todo}")

    def line(self, text: str = "") -> None:
        self._emit(text)


def human_age(seconds: float | None) -> str:
    """'45 seconds', '12 minutes', '3 hours', '2 days' (rounded down)."""

    if seconds is None:
        return "unknown"
    seconds = max(0.0, float(seconds))
    for size, word in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = int(seconds // size)
            return f"{count} {word}{'s' if count != 1 else ''}"
    count = int(seconds)
    return f"{count} second{'s' if count != 1 else ''}"


def human_bytes(size: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
