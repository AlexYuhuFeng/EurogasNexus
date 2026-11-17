"""What the report form may offer this user, decided before Generate is pressed.

Every refusal the server can give a report request is known in advance from the caller and the
store, so the catalogue tells the form about each option instead of the request failing:

- **Generate at all**: the report routes need the analyst role floor (``Permission.GOVERNED``);
  a viewer or reviewer is told so and Generate is not offered.
- **Audience**: book sections exist only in an internal report; a report for distribution
  drops them (the form does it, the server does it too).
- **Sections**: each section is read once for today's daily scope, exactly as a report would
  read it. A section with nothing held is offered as "will be listed as not held", with the
  section's own reason; nothing fails.
- **Period**: the limits ``validate_plan`` enforces (400 days, no day after today).
- **AI editing**: whether the model may edit this caller's report, with the reason when not.

The probe is the reports' own builders, so its verdict is the generation's verdict. It is
cached per caller for a short time; nothing is stored.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.caller import Caller

#: Seconds a caller's probe stands before it is read again.
TTL_SECONDS = 120.0
MAX_PERIOD_DAYS = 400
_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}


#: Why AI editing is not offered, by the code the route gives.
AI_REASONS = {
    "switched_off": ("AI editing is switched off for this installation; reports are "
                     "rule-written.", "本系统已关闭 AI 编辑；报告由规则撰写。"),
    "role": ("Your role does not include AI analysis; reports are rule-written.",
             "您的角色不含 AI 分析；报告由规则撰写。"),
    "no_key": ("No AI provider key is configured; reports are rule-written.",
               "未配置 AI 服务密钥；报告由规则撰写。"),
}


def _role_ok(principal) -> tuple[bool, str]:
    from eurogas_nexus.application.reports.lang import T
    from eurogas_nexus.security.identity import role_allows

    role = getattr(principal, "role", "VIEWER")
    if role_allows(role, "ANALYST"):
        return True, ""
    return False, T(f"Generating a report needs the analyst role; your role is "
                    f"{str(role).lower()}. Ask an administrator, or open a stored report.",
                    f"生成报告需要分析师角色；您的角色为 {str(role).lower()}。请联系管理员，"
                    "或打开已存报告。")


def probe_sections(session, caller: Caller, now: datetime,
                   balance_reader=None) -> dict[str, dict[str, Any]]:
    """Each section's state for today's daily scope: ``ok`` or ``not_held`` with the reason
    the report would print, or ``unavailable`` when the read failed."""

    from eurogas_nexus.application.reports.catalogue import SECTIONS, validate_plan
    from eurogas_nexus.application.reports.engine import book_scope_of
    from eurogas_nexus.application.reports.sections import BUILDERS, Ctx

    out: dict[str, dict[str, Any]] = {}
    keys = [s.key for s in SECTIONS if s.key != "situation_event"]
    plan = validate_plan({"kind": "daily", "audience": "internal", "sections": keys}, now=now)
    ctx = Ctx(session=session, caller=caller, now=now, plan=plan, balance_reader=balance_reader)
    with book_scope_of(caller):
        for key in keys:
            try:
                built = BUILDERS[key](ctx)
            except Exception as exc:  # noqa: BLE001 - a failing read is reported, not raised
                session.rollback()
                out[key] = {"state": "unavailable",
                            "reason": f"The read failed ({exc.__class__.__name__}); the "
                                      "report will list it as not available."}
                continue
            if built.empty:
                out[key] = {"state": "not_held", "reason": built.empty["reason"],
                            "action": built.empty.get("action")}
            else:
                out[key] = {"state": "ok", "reason": None}
    return out


def availability(session, caller: Caller, *, now: datetime | None = None,
                 ai: tuple[bool, str] = (False, ""), balance_reader=None,
                 language: str = "en") -> dict[str, Any]:
    """What this caller's report form may offer (see the module text), its reasons written in
    ``language``."""

    from eurogas_nexus.application.reports.lang import writing

    with writing(language):
        return _availability(session, caller, now, ai, balance_reader)


def _availability(session, caller, now, ai, balance_reader) -> dict[str, Any]:
    from eurogas_nexus.application.reports.lang import T
    from eurogas_nexus.application.reports.render import omitted_reason

    now = (now or datetime.now(UTC)).astimezone(UTC)
    principal = caller.principal
    key = (caller.principal_id, getattr(principal, "role", ""),
           tuple(getattr(principal, "data_scopes", ()) or ()), now.date().isoformat())
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        sections = hit[1]
    else:
        sections = probe_sections(session, caller, now, balance_reader)
        _CACHE[key] = (time.monotonic(), sections)
    sections = {k: {**v, "reason": omitted_reason(v["reason"]) if v.get("reason") else None}
                for k, v in sections.items()}
    may, why = _role_ok(principal)
    ai_why = AI_REASONS.get(ai[1])
    ai_text = (T(*ai_why) if ai_why else ai[1]) or None
    return {
        "can_generate": may,
        "reason": why or None,
        "sections": sections,
        "audiences": {
            "internal": {"allowed": True, "reason": None},
            "shareable": {"allowed": True,
                          "reason": T("Book sections are not available in a report for "
                                      "distribution; they are left out.",
                                      "对外分发的报告不含账簿章节，已略去。")},
        },
        "period": {"max_days": MAX_PERIOD_DAYS, "latest_end": now.date().isoformat()},
        "ai": {"available": bool(ai[0]), "reason": ai_text},
        "languages": ["en", "zh-CN"],
    }


__all__ = ["availability", "probe_sections"]
