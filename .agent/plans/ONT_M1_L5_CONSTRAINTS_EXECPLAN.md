# ONT-M1: 集中式 L5 可计算约束模块 ExecPlan

## 1. Goal

把散落在各 domain 里的 **L5 可计算约束**（正确性规则）抽取为一个 import-safe、
声明式、可单测的集中模块，让确定性引擎与 LLM 校验读同一份约束，兑现
`docs/ontology/europe-natural-gas.md` §3 的"正确性归校验器"分工。

范围（首批抽取，均已存在代码与测试，属于"集中化"而非"新能力"）：

- 净回值 / 路线成本公式（现散在 `domain/route_cost/`）
- 容量守恒 + 方向性容量（现散在 `domain/route_cost/route_optimizer.py`、`resource_pool.py`）
- 止损（累计口径，现散在 `domain/strategy_lab/evaluation.py`）
- 单市场上限 / 最小毛利（现散在 `domain/strategy_lab/evaluation.py`）
- fail-closed entitlement（已在 `governance/entitlement.py`，本切片仅"接引"不改逻辑）

## 2. Non-goals

- 不新增任何业务能力或行为变化；只**集中现有规则**。
- 不抽取 L4 制度（审计/出口治理）——它们已在 `governance/`，后续单独评估。
- 不动 no-execution（动作白名单）——它是枚举/语言纪律，属 S4，不在本切片。
- 不新建 DB 表、不加迁移、不新增 API 端点（除非为了读取约束的只读端点，本轮不做）。
- 不做 MarketArea/zone 聚合层（那是 S2，另行）。

## 3. Product boundary

约束模块是**纯函数/声明式**领域层，import-safe（import 不连库、不连网络），被
domain 计算路径调用。输出仍是 decision-support + human-review，无任何执行语义。

## 4. Files to create/modify

- Create `src/eurogas_nexus/domain/constraints/__init__.py`
- Create `src/eurogas_nexus/domain/constraints/route_economics.py`（净回值/路线成本公式）
- Create `src/eurogas_nexus/domain/constraints/capacity.py`（容量守恒、方向性）
- Create `src/eurogas_nexus/domain/constraints/risk.py`（止损、单市场上限、最小毛利）
- Modify `src/eurogas_nexus/domain/route_cost/route_cost_service.py`（改为引用 route_economics）
- Modify `src/eurogas_nexus/domain/route_cost/resource_pool.py`（改为引用 capacity）
- Modify `src/eurogas_nexus/domain/strategy_lab/evaluation.py`（改为引用 risk）
- Create `tests/unit/test_constraints_route_economics.py`
- Create `tests/unit/test_constraints_capacity.py`
- Create `tests/unit/test_constraints_risk.py`

## 5. Dependency policy

零新增依赖。仅用现有允许栈（Python/Pydantic/SQLAlchemy，但约束模块本身不 import
SQLAlchemy/FastAPI，保持纯函数）。

## 6. Data policy

约束模块不读 DB、不写 DB、不读文件。它是声明式规则 + 纯函数校验器。运行时真相
仍是 PostgreSQL；约束只校验由上层传入的已装载事实。

## 7. API impact

无新端点、无路由变更。现有端点行为不变（约束被引用后结果应完全一致）。

## 8. DB impact

无迁移、无新表。

## 9. Tests

- 单元：每个约束独立测试（净回值公式、容量守恒、止损累计、单市场上限、最小毛利）。
- 回归：现有 `tests/unit/test_route_cost_*`、`tests/unit/test_strategy_lab_evaluation.py`
  必须全绿（证明"集中化"未改变行为）。

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/unit/test_constraints_route_economics.py tests/unit/test_constraints_capacity.py tests/unit/test_constraints_risk.py tests/unit/test_route_cost_tariff_selection.py tests/unit/test_route_cost_multileg_europe.py tests/unit/test_route_cost_capacity_requirement.py tests/unit/test_strategy_lab_evaluation.py
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- 净回值/路线成本/容量守恒/止损/单市场上限/最小毛利集中到 `domain/constraints/`。
- domain 计算路径改为调用约束模块，行为与抽取前一致（现有测试全绿）。
- 约束模块 import-safe（import 不触发 DB/网络/FastAPI）。
- ruff 通过，app import 通过，路由数不变（90）。

## 12. Rollback notes

- 纯抽取，无 schema/API 变更；回滚 = 还原 domain 文件到抽取前。
- 若某约束的抽取导致行为漂移，先回退该文件、保留其余，不整批回滚。

---

## 依赖的决策（需要用户拍板，排在 S3 之后）

**S1「单一本体源」需要选一套保留**：建议保留 `glossary_terms` 表为词表真相、
把 `business_logic_ontology()` 升级为 DB 驱动的类型化 L1、下线或接入孤儿表
`business_ontology_terms`。此决策确认后我再写 S1 的 ExecPlan。
