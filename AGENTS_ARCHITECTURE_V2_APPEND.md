<!-- EUROGAS_ARCH_V2_AUTONOMY_BEGIN -->
# Eurogas Nexus Architecture V2 autonomous-development rules

1. Read `docs/engineering/Architecture-V2/CODEX_ENTRYPOINT.md` first.
2. Read `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` before planning work.
3. GPT-6 Astra is the planner/architect/integration reviewer; routine implementation belongs to DeepSeek.
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
