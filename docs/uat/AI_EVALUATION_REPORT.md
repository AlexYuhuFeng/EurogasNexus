# AI Evaluation Report — CR-13

## Methodology

The production assistant is a deterministic backend answer builder with an
optional, credential-gated DeepSeek enrichment path. CR-13 grades both:

1. deterministic grounding/numerical/citation behavior (`tests/evals/`);
2. provider gate, entitlement, payload filtering, prompt-injection surface,
   and no-execution boundary (`tests/security/test_llm_provider_gate.py`).

Live DeepSeek grading is not fabricated: it remains PENDING_EXTERNAL until an
approved credentialed test environment is available.

## Corpus

`tests/evals/analysis_eval_cases.json` covers MARKET, PORTFOLIO, STRATEGY,
SHADOW, SCENARIO, OPERATIONS, numerical units, entitlement, prompt injection,
and trading boundary cases. Each case records input, expected facts, forbidden
claims, and required warning/missing-input behavior.

## Metrics

| Metric | Result | Threshold |
| --- | --- | --- |
| Critical case correctness | 13/13 PASS | critical numerical/entitlement/boundary cases must be 100% |
| Numerical consistency | PASS | correct number with wrong unit is FAIL |
| Citation/source coverage | PASS | every result includes snapshot citations |
| Entitlement compliance | PASS | ICIS_Sim snapshot blocks provider call before payload construction |
| Uncertainty calibration | PASS | missing/stale inputs produce warnings and missing-input lists, never invented values |
| Hallucination rate (deterministic path) | 0 | deterministic path quotes snapshot counts only |
| Prompt injection | PASS | injection text never reaches provider without credential; no secret fields enter payload |
| No-execution/trading boundary | PASS | no order/nomination/execution language in generated answers |
| Tool selection | PASS | unsupported provider returns `LLM_PROVIDER_NOT_SUPPORTED_IN_V1`; unconfigured credential returns `LLM_PROVIDER_CREDENTIAL_MISSING` |
| Latency/cost | not measured | requires live provider credential |

## Failure review

No deterministic failures remain. The only live-model risk category is the
credentialed DeepSeek synthesis path; its evaluation is explicitly
PENDING_EXTERNAL and must be repeated with the deployment-approved model.
