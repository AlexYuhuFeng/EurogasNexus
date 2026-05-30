# V1 R6 Research Workflow Models ExecPlan

## 1. Goal

Define research workflow dataclass models and read-only API routes for the core
V1 research workflows: route cost, indicative netback, feasibility, allocation
scenario, monitoring/alerts, weather-adjusted nowcast, strategy backtest, shadow
run, LLM-assisted analysis, and research brief. All models are research-only with
required metadata fields. All data is synthetic fixtures.

## 2. Non-goals

- No live workflow execution or calculation logic.
- No DB persistence for workflow results.
- No LLM provider calls.
- No trade execution, order entry, or nomination logic.

## 3. Files to create/modify

- `src/eurogas_nexus/workflows/__init__.py`
- `src/eurogas_nexus/workflows/models.py` — all workflow result models
- `src/eurogas_nexus/api/routes/v1/workflows.py` — API routes
- `src/eurogas_nexus/api/routes/v1/glossary.py` — glossary routes (English/Mandarin)
- `src/eurogas_nexus/api/route_registration.py` — register new routers
- `data/release_v1/r6_research_workflow_models_report.md`
- `tests/contract/test_workflow_models.py`
- `tests/api/test_workflows_api.py`

## 4. API impact

~14 new routes across workflows and glossary.

## 5. DB impact

None. Pure dataclass models with synthetic fixtures.

## 6. Validation
```
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 7. Acceptance

- All workflow models have research_only, human_review_required, assumptions,
  missing_inputs, warnings, source_references fields.
- Glossary supports English and Mandarin terms.
- No DB dependency.
- App import DB-free.
