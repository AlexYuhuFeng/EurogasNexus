# Web 应用架构

英文主文档：[WEB_APPLICATION_ARCHITECTURE-EN.md](WEB_APPLICATION_ARCHITECTURE-EN.md)

## 目的

本文是 `clients/web/src` 下 React 应用结构的实现规范。它明确每类行为的
归属，防止组合入口、UI 组件或浏览器包演变成第二套后端或运行数据仓库。

## 运行边界

```text
PostgreSQL -> FastAPI /api -> api/client.ts -> stores/api.ts
           -> app hooks/models -> shell/workspaces -> components
```

浏览器不得读取 PostgreSQL、后端本地文件、`.env`、外部数据商接口或密钥。
模拟和预览数据必须与授权数据一样，先进入 PostgreSQL，再经过后端 API。

## 目录职责

| 路径 | 唯一职责 |
| --- | --- |
| `App.tsx` | 只创建应用 controller 并渲染 shell。 |
| `app/hooks/` | 按工作流管理交互状态和生命周期。 |
| `app/model/` | 把 API 状态组合成页面可用的派生决策模型；不请求数据、不渲染 JSX。 |
| `app/shell/` | 长期存在的应用框架、顶栏和地图驾驶舱组合。 |
| `app/workspaces/` | 工作区 ID 与页面组件的唯一映射。 |
| `app/*.ts` | 纯构建器、标准化、元数据和派生数据函数。 |
| `components/` | 领域页面和局部展示交互。 |
| `api/client.ts` | HTTP DTO、响应解析和 `/api` 传输。 |
| `stores/api.ts` | 后端请求动作和 API 状态。 |
| `stores/theme.ts` | 仅管理主题偏好。 |
| `i18n/` | 中英文显示文案。 |
| `styles/` | 共享视觉变量和有序样式。 |

## 当前模块

- `useWorkspaceNavigation`：URL、历史记录和前进后退导航。
- `useWorkspaceRuntime`：首次加载和市场页面刷新周期。
- `useCockpitControls`：地图图层、搜索、gas day 和产品。
- `useContractEditor`：EFET 风格资源条款草稿和导入。
- `useSourceCenterController`：数据源分类、选择、诊断和密钥提交。
- `useGlossaryExplorer`：术语筛选、时间区间和上下文请求。
- `useReviewAnalysis`：报告问题和后端 LLM 调用请求状态。
- `usePortfolioDecisionModel`：来自 PostgreSQL/API 的资源池、销售选项、优化请求、地图路径、证据和决策指标。
- `AppShell`：顶栏和 Network 地图驾驶舱。
- `WorkspaceRenderer`：工作区页面的唯一选择器。

## 依赖规则

允许：

```text
App -> controller -> hooks/models -> 纯 app helpers
App -> shell -> workspace renderer -> components
hooks/models -> API DTO 和 API store contract
```

禁止：

- 前端组件导入后端 DB、domain、connector、ingestion 或 runtime-store；
- 纯构建器调用 React hook、Zustand action、`fetch` 或 Tauri API；
- 页面组件生成权威价格、管容、费率、拓扑、合同或 PnL 数据；
- 在 `workspaceNavigation.ts` 之外建立第二份页面 ID 清单；
- 把页面判断、轮询或业务派生重新塞回 `App.tsx`。

## 规模与拆分标准

- `App.tsx` 不得超过 20 行，并由 contract test 强制检查。
- 一个 hook 只管理一个工作流；混入无关生命周期或表单时必须拆分。
- 复杂派生模型原则上不超过约 350 行，确定性计算优先移入纯函数。
- workspace renderer 原则上不超过约 300 行，页面内容应拆成独立组件。
- 超过约 450 行的组件视为需要审查的技术债，不能作为新增代码模板。
- 不能只为缩短行数制造抽象；每次拆分必须形成清晰且稳定的职责边界。

## 新增能力流程

1. 新运行数据先更新后端、API 和 SDK 合同。
2. 增加 DTO 和 API store 状态，不得嵌入前端业务兜底数据。
3. 确定性转换放入 `app/*.ts` 或领域子目录。
4. 工作流状态放入一个专用 hook。
5. 页面组件放入 `components/`，只在 `WorkspaceRenderer` 接线一次。
6. 同时增加中英文文案。
7. 更新模块 owner 测试并执行 Web 生产构建。

## 已知结构债务

`styles/app.css` 是多轮预览改版形成的有序兼容级联。本轮 R30A 不机械拆分，
以免破坏 light/dark 和响应式效果。后续应以独立样式 ExecPlan 按
tokens/base/layout/workspace 分层，并用截图回归保证级联顺序和视觉一致性。
