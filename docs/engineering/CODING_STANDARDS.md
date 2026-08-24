# Coding Standards（代码规范）

本文件是 Eurogas Nexus 的代码规范权威（中英双语）。基准为
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) 与
[PEP 8](https://peps.python.org/pep-0008/)，并按本仓库实际情况特化。
规范执行由 `ruff` 规则集与 `tests/contract/test_docstring_policy.py` 契约测试
强制；本文件是人工评审与新增代码的依据。

This file is the code-standards authority for Eurogas Nexus (bilingual).
Baseline: the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
and [PEP 8](https://peps.python.org/pep-0008/), specialized for this repo.
Enforcement: the `ruff` rule set plus `tests/contract/test_docstring_policy.py`;
this file is the reference for review and for new code.

---

## 1. 风格基线 / Style Baseline

- **行宽 / Line length**：100 列（`pyproject.toml` `line-length = 100`；
  Google 默认 80 不适用本仓库，列宽以项目配置为准）。
- **规则集 / Rule set**：`ruff` `select = ["E", "F", "I", "B", "UP"]`——错误、
  未使用、导入排序、bug-prone、pyupgrade。禁止新增 `# noqa` 掩盖规则；确需
  例外时在同行注明原因。
- **格式化 / Formatting**：遵循 ruff 自动修复（`ruff check --fix`）；格式化
  争议以 ruff 输出为准，不做人工辩论。

## 2. 命名 / Naming

| 对象 | 规范 | 示例 |
|---|---|---|
| 模块 | `snake_case` | `route_cost_service.py` |
| 类 | `CapWords` | `PortfolioOptimizationResult` |
| 函数/方法 | `snake_case` | `optimize_resource_pool` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_ARCHIVE_BYTES` |
| 私有 | 单下划线 `_` 前缀 | `_resolve_gie_key` |
| 类型变量 | `T`, `TResult` | `SdkResult[T]` |

规则要点 / Key rules：
- 私有成员用 `_` 前缀；`__` 双下划线仅用于避免继承冲突，不用于"隐藏"。
- 布尔函数/谓词用 `is_`/`has_`/`can_` 前缀（`is_gas_price_observation`）。
- 缩写词保持全大写或全小写，不混用（`HTTPError`，`http_client`）。
- 避免与内置函数同名（不用 `list`、`input` 作变量名）。

## 3. 类型注解 / Type Annotations

- 公共 API 全量注解：函数参数、返回值、数据类字段。
- 可空类型用 `X | None`（Python 3.11+，本仓库 `target-version = "py311"`）；
  不使用 `Optional[X]` 旧写法。
- 集合元素类型必须标注：`list[str]`，不写裸 `list`。
- 返回"可能失败"的读取函数返回 `X | None`，调用方必须处理 None。

## 4. Docstring（Google 风格）

所有公共模块、类、函数必须有 docstring。模板：

```python
def evaluate_freshness(
    expectation_minutes: int,
    last_observed_at_utc: datetime | None,
    now_utc: datetime | None = None,
) -> FreshnessStatus:
    """Evaluate whether the newest observation satisfies the expectation.

    评估最新观测是否满足来源的新鲜度期望（中英双语规范示范）。

    Args:
        expectation_minutes: Positive expectation window in minutes;
            non-positive means no expectation declared (unknown).
        last_observed_at_utc: Newest observation time; None when absent.
        now_utc: Evaluation clock; defaults to ``datetime.now(UTC)``.

    Returns:
        ``LIVE`` when the observation is inside the window, ``STALE`` when
        older, ``UNKNOWN`` when no observation or no expectation exists.

    Raises:
        ValueError: When ``expectation_minutes`` is not an integer-like value.
    """
```

规则要点 / Key rules：
- Summary 行：祈使句或陈述句，句号结尾，一行内。
- `Args`/`Returns`/`Raises` 只在存在对应内容时书写；参数类型已在签名标注，
  docstring 内不重复类型（描述语义与约束）。
- 私有函数（`_` 前缀）docstring 可精简为一行 Summary。
- 数据类字段语义写进类 docstring，不逐字段写。

## 5. 注释语言政策 / Comment Language Policy

- **Docstring 用英文**（工具链、国际协作、与 OpenAPI/契约一致）。
- **行内关键注释用中文**，解释"为什么"而不是"是什么"：
  ```python
  # 审计项 3：有记录不等于活跃——超期数据必须显式标记 stale。
  if source.get("freshness_status") == "stale":
      return "stale"
  ```
- 复杂业务规则（法规、市场惯例）给中英双语说明，中文在前或后均可，保持
  同一文件内一致。
- 注释禁止转述代码本身（`i += 1  # 自增`）；注释应给出代码无法表达的信息：
  约束来源、权衡、反例、审计编号。

## 6. 结构与职责 / Structure & Responsibility

- 模块单职责；超过 ~700 行的文件应拆出纯数据/纯逻辑子模块（如
  `sources.py` → `domain/ingestion/source_registry.py`）。
- 函数短小（优先 < 40 行）；复杂算法拆私有辅助函数并各自单测。
- 导入顺序由 ruff isort 强制；禁止 `import *`。
- 领域模块（`domain/`）不得导入 web 框架与 DB 会话（import-boundary
  契约测试强制）；DB 访问只在 `db/repositories/`。
- 客户端（Web/SDK/CLI）只通过 API/SDK 边界取数，不直连 PostgreSQL、
  不导入后端领域模块。
- SDK 内部 HTTP 辅助（`_get`/`_post`）统一返回**完整信封**
  `{data, meta}`，由各 fetch 函数按端点形状解包 `["data"]`——不做
  两种解包约定并存（2026-08 已统一 route_cost/research 两个历史模块）。
- pydantic 字段默认值一律 `Field(default_factory=...)`，禁止
  `list[str] = []` 类可变默认值写法（pydantic v2 虽深拷贝，但风格
  必须统一）。

## 7. 前端 TypeScript / Frontend TypeScript

- 遵循 Google TypeScript Style Guide 要点：显式类型、`interface` 优先于
  `type`、组件文件 `PascalCase.tsx`、工具函数 `camelCase.ts`。
- 状态更新不可变（zustand `set` 用新对象/展开）。
- 业务推导逻辑集中在 `clients/web/src/app/*.ts` 纯函数，组件只做渲染。
- DTO 类型与后端契约一致；新增字段必须同步
  `tests/contract/test_sdk_backend_parity.py` 风格的契约测试。

## 8. 测试 / Testing

- 测试命名 `test_<行为>_<条件>`；断言只验证契约行为，不验证实现细节。
- 网络/DB 依赖一律 mock（monkeypatch）或走契约夹具；禁止测试触达外部 API。
- 契约测试（`tests/contract/`）钉死跨端约定；行为变更必须同步契约。
- 测试是规范的一部分：修改规范时同步修改
  `tests/contract/test_docstring_policy.py` 的受检模块列表。

## 9. 规范执行 / Enforcement

```powershell
ruff check .                          # 风格/导入/错误
pytest -q tests/contract             # 契约（含 docstring 政策）
python -c "from apps.api.main import app; print('app import ok')"
```

新增代码在提交前必须通过上述命令。核心模块的 docstring 政策由
`tests/contract/test_docstring_policy.py` 强制：受检模块的公共函数/类缺失
docstring 即失败，提示先阅读本文档第 4 节。
