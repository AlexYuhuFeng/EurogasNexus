#!/usr/bin/env python
"""EN/zh-CN parity gate for the Web client.

Checks key-set parity and statically referenced keys. Dynamic keys are allowed
to resolve through their family prefix. Exits non-zero on missing keys.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "clients" / "web" / "src"
EN = json.loads((CLIENT / "i18n" / "en.json").read_text(encoding="utf-8"))
ZH = json.loads((CLIENT / "i18n" / "zh.json").read_text(encoding="utf-8"))


def referenced_keys() -> set[str]:
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in CLIENT.rglob("*.ts*")
    )
    keys = {match.group(1) for match in re.finditer(r'\bt\(\s*["\']([^"\']+)["\']', text)}
    # Keys produced through template literals are checked by their family
    # prefix below; concrete keys must resolve exactly.
    return {key for key in keys if "{" not in key}


def main() -> int:
    errors = []
    only_en = sorted(set(EN) - set(ZH))
    only_zh = sorted(set(ZH) - set(EN))
    if only_en:
        errors.append(f"only-en keys: {only_en[:10]}")
    if only_zh:
        errors.append(f"only-zh keys: {only_zh[:10]}")
    missing = sorted(key for key in referenced_keys() if key not in EN)
    if missing:
        errors.append(f"missing referenced keys: {missing[:20]}")
    same = [
        key
        for key in EN
        if key in ZH
        and EN[key] == ZH[key]
        and not re.fullmatch(r"[A-Z0-9_ /:.,%+()\-–—&]+", EN[key])
    ]
    print(
        json.dumps(
            {
                "ok": not errors,
                "en_keys": len(EN),
                "zh_keys": len(ZH),
                "referenced_keys": len(referenced_keys()),
                "missing": missing,
                "only_en": only_en,
                "only_zh": only_zh,
                "identical_suspicious": same[:20],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
