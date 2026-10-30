<!-- EUROGAS_ARCH_V2_AUTONOMY_BEGIN -->
# Eurogas Nexus Architecture V2 autonomous-development rules

1. Read `docs/engineering/Architecture-V2/CODEX_ENTRYPOINT.md` first.
2. Read `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` before planning work.
3. Codex retains planning, architecture and integration review. Per the owner's 2026-10-28 instruction, use the approved local DeepSeek Harness with DeepSeek V4.1 Flash1017 (`deepseek-flash`), max reasoning, for bounded implementation; parallel DeepSeek tasks are authorized. Keep credentials outside the repository and review/test changes before committing.
4. No big-bang rewrite.
5. No new microservices/Kubernetes/Kafka/service mesh/datastore without reviewed ADR and measured need.
6. Preserve FastAPI, React, Tauri, PostgreSQL/Alembic and existing security/release/DR foundations unless an approved migration says otherwise.
7. Work mode/persona never grants backend authority.
8. No trade execution/order entry/nomination/settlement.
9. A new capability does not automatically earn a new page.
10. Use bounded tasks, focused tests, explicit checkpoint updates and deterministic gates.
11. Stop for Architecture V2 hard STOP conditions.
12. Never commit secrets. `DEEPSEEK_API_KEY` stays outside the repository.
13. Never run two active autonomous supervisors against the same working tree.
14. No automatic push/merge unless separately authorised by a human.
<!-- EUROGAS_ARCH_V2_AUTONOMY_END -->
15. Before every push run `scripts/ci/pre_push_check.sh` (install it as `.git/hooks/pre-push`).
    It refuses untracked source files and runs the fast gates a clean checkout runs; `main`
    broke on 2026-10-30 because a pushed commit imported a module that existed only in the
    worker's tree.
16. A push to `main` is not done until the hosted CI run for that commit is green. If it is
    red, fixing it comes before any new feature work. Prefer a pull request with required
    checks (see `docs/engineering/CI_AND_BRANCH_PROTECTION.md`).
17. Users are commercial gas traders, analysts and risk staff who trade on Trayport or
    exchange screens. Follow `docs/product/UX_REFERENCE.md` "Trader-first presentation
    rules": desk names and native units, prices first, provenance on demand, and no
    simulated price that can be read as a market price.
18. The product is sold commercially: no dependency, dataset, tile service or API whose
    terms exclude commercial use (see `docs/legal/`). Licensed market data comes only
    through the customer's own entitlement.
