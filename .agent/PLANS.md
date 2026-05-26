# Eurogas Nexus Plans

## V1.0 Bootstrap

Status: active.

Goals:

- Establish repository topology and product boundaries.
- Provide a minimal import-safe FastAPI app shell.
- Add architecture contracts and boundary tests.
- Defer all business features and live integrations.
- Keep milestone ExecPlans under `.agent/plans/`.

## Active ExecPlans

- `.agent/plans/V1_BOOTSTRAP_EXECPLAN.md`

## ExecPlan Required Sections

Every complex milestone plan must include:

1. Goal
2. Non-goals
3. Product boundary
4. Files to create/modify
5. Dependency policy
6. Data policy
7. API impact
8. DB impact
9. Tests
10. Validation commands
11. Acceptance criteria
12. Rollback notes

## Next Candidate Milestone

Define database migration conventions, typed domain value-object templates, and
workflow interface examples without connecting to live systems.
