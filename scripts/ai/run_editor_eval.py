"""Send the editor evaluation sheets to the provider and report how the plans fare.

    python scripts/ai/run_editor_eval.py [--repeat 2] [--json report.json]

Only the recorded sheets in tests/evals/editor_cases.json are sent (demo or public data);
it refuses in trial or release profiles and when any case is not marked demo or public.
Reports: the share of plans that are valid JSON objects, the share of elements kept
(passed the checks) against fallen back, the agreement of the lead finding with the case's
expected lead, and the median latency. Needs DEEPSEEK_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "evals"))


def main() -> int:
    from test_editor_evals import CASES, build_sheet, rule_for, sections_of

    from eurogas_nexus.application.reports import editor
    from eurogas_nexus.application.reports.catalogue import validate_plan
    from eurogas_nexus.core.config import get_settings
    from eurogas_nexus.llm import invoke_deepseek

    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--json")
    args = parser.parse_args()
    if str(getattr(get_settings(), "environment", "")).lower() in {"trial", "release"}:
        print("refused: trial or release profile")
        return 2
    if any(case["data_class"] not in {"demo", "public"} for case in CASES):
        print("refused: a case is not demo or public data")
        return 2
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("DEEPSEEK_API_KEY is not set")
        return 2
    runs = []
    for case in CASES:
        sheet = build_sheet(case)
        sections = sections_of(sheet)
        asked = bool(case.get("rule_answer"))
        plan = validate_plan({"kind": "ask" if asked else "daily", "audience": case["audience"],
                              "question": case.get("question"),
                              **({"sections": sorted({f["section"] for f in sheet}
                                                     & {"prices", "pipeline_supply", "lng",
                                                        "storage", "outages", "balance"})}
                                 if asked else {})},
                             now=datetime(2026, 11, 16, 8, tzinfo=UTC))
        rule = rule_for(case, sheet, sections)
        for _ in range(args.repeat):
            payload = editor.fact_sheet_payload(sheet, sections, plan, case["language"],
                                                rule.get("cannot_tell"))
            started = time.monotonic()
            result = invoke_deepseek(api_key=key, messages=editor.editor_messages(payload),
                                     **editor.EDITOR_CALL)
            latency = time.monotonic() - started
            raw = editor.parse(result.content if result.status == "success" else None)
            out = editor.apply_plan(raw, sheet, sections, dict(rule), "deepseek",
                                    report_days=(plan.period_start, plan.period_end),
                                    audience=case["audience"])
            elements = out["record"]["elements"]
            lead_ids = (out["findings"][0]["fact_ids"] if out["findings"] else [])
            lead = next((f["key"] for f in sheet if lead_ids and f["id"] == lead_ids[0]), None)
            if out["findings"] and out["findings"][0]["text"].lower().startswith(
                    ("flows", "no ", "prices and flows")):
                lead = "NO_NEWS" if case["expected_lead"] == "NO_NEWS" else lead
            runs.append({
                "case": case["id"], "valid": raw is not None, "latency_s": round(latency, 1),
                "elements": len(elements), "kept": sum(1 for v in elements.values() if v["ok"]),
                "lead": lead, "expected_lead": case["expected_lead"],
                "lead_from_model": bool(out["findings"]) and
                out["findings"][0].get("basis") == "model",
                "refused": {k: v["detail"] for k, v in elements.items() if not v["ok"]},
                **({"answer": (out.get("answer") or {}).get("text"),
                    "answer_basis": (out.get("answer") or {}).get("basis")} if asked else {}),
            })
            print(json.dumps(runs[-1], ensure_ascii=False))
    valid = [r for r in runs if r["valid"]]
    total = sum(r["elements"] for r in valid)
    summary = {
        "runs": len(runs),
        "valid_plans": f"{len(valid)}/{len(runs)}",
        "elements_kept": f"{sum(r['kept'] for r in valid)}/{total}",
        "lead_agreement": f"{sum(1 for r in valid if r['lead'] == r['expected_lead'])}/"
                          f"{len(valid)}",
        "median_latency_s": statistics.median(r["latency_s"] for r in runs) if runs else None,
    }
    print(json.dumps(summary))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "runs": runs}, indent=1,
                                              ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
