# New File Template

Use this checklist before adding a new source file.

## Required Header Review

- Package:
- Layer:
- Owner:
- Contract file:
- Import direction:
- Side effects at import: none
- External calls: none unless contract-approved
- Persistence access: none unless contract-approved
- Tests:
- ExecPlan updated for large change:

## Questions

1. Does the file fit an existing contract?
2. Does it import only lower or allowed layers?
3. Does it avoid live network, DB, secrets, and provider calls at import time?
4. Does it need a contract or boundary test update?
5. Is it adding business behavior that belongs to a later milestone?
