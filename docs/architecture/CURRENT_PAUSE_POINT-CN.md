# 当前暂停点

英文主文档：[CURRENT_PAUSE_POINT.md](CURRENT_PAUSE_POINT.md)

## 状态

检查日期：2026-07-18

Eurogas Nexus 当前是 `0.5.0` 预览发布版本，已经包含 FastAPI 后端、PostgreSQL 运行数据库、Python SDK、CLI、React/Vite Web 客户端、Tauri Windows/Linux 客户端以及按角色部署工具。

产品定位是欧洲天然气市场情报、优化和决策支持。它不是交易场所、订单路由器、提名提交系统、结算平台、法律咨询工具或 ETRM。

## 已验证基线

```text
alembic_revision: 0013_gie_lng_dtmi_energy
required_tables: 33
missing_tables: 0
source: runtime-postgresql

app import ok
82 routes
```

仓库数据结构 head 现为 `0014_intraday_decision_feed`，要求 36 张表。上面的本地 PostgreSQL 基线仍停留在 `0013`；本次实现没有对在线数据库执行迁移，必须由运营人员显式执行。

客户端只通过 `/api` 或 SDK 获取 PostgreSQL 中的数据，不直连数据库、不读取后端本地文件，也不直接调用数据提供商。数据源密钥由后端管理，任何读取接口都不得返回明文。

## 当前产品结构

- 公共 API：无版本号的稳定 `/api`。
- 运营接口：`/api/internal`，已实现的端点要求后端内部令牌和主体标识。
- 开发接口：`/api/dev`，受运行配置限制。
- 数据权威来源：PostgreSQL 和 Alembic。
- 客户端：共享的 Web 工作区，以及 Windows x64、Linux x64/ARM64 Tauri 外壳。
- 部署角色：Server、Client、AllInOne。生产级身份认证完成前，服务器部署只允许用于私网或 VPN 预览环境。
- 预览价格：仿真数据源把与真实提供商同形的数据写入 PostgreSQL，并完整经过后端、API、SDK/客户端链路。
- 日内决策：标准化 L1 报价触发后端路径净价差扫描；已持久化机会通过 API/SDK 提供，Network、Market 和 Strategy 工作区每 10 秒读取一次。过期快照不会继续显示为可审阅机会。

## 当前优化能力

稳定的操作员输入端点：

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
```

共享管容网络流已经改为带反向弧的残量网络算法，并校验最终流量、管容、成本和节点流守恒。储气调度和提名窗口评估是已测试的内部原型。在完成 PostgreSQL 输入组装、数据来源追踪、API DTO 和 SDK 合同之前，这三项不会作为客户 API 暴露。

## 发布状态

- 普通 CI 执行 Python、优化器、API 导入和 Web 验证，并在 PR 上构建桌面包。
- 每次 `main` 提交由 Build and Release workflow 构建 Web、Windows x64、Linux x64、Linux ARM64、部署包和 amd64/arm64 API 镜像。
- Linux Tauri 依赖安装使用 Ubuntu 官方 HTTPS 镜像和有限重试，降低 ARM runner 的瞬时网络故障影响。

## Web 应用架构

React 的 `App.tsx` 现为九行组合入口，只创建应用 controller 和 shell。工作流
状态位于 `app/hooks`，组合决策派生模型位于 `app/model`，长期存在的界面框架
位于 `app/shell`，页面选择位于 `app/workspaces`。Contract test 会强制保持
入口简洁，并按真实模块 owner 验证功能，不再要求所有实现都出现在
`App.tsx` 文本中。

详见 [WEB_APPLICATION_ARCHITECTURE-CN.md](../clients/WEB_APPLICATION_ARCHITECTURE-CN.md)。

## 尚未完成的正式交付条件

1. 多用户身份认证、授权和公司 SSO 尚未实现；服务器角色目前只支持私网/VPN 预览部署。
2. 商业数据源必须由客户提供密钥、授权和许可，并经过运营验证。
3. 公共数据源调度、告警、审计深度、导出治理和保留策略仍需生产化。
4. 路径级日内机会已从 PostgreSQL 组装报价、路径、费率、管容、TSO 权限和 FX。正式组合优化仍需在共享和替代路径之间分配资源，并完成合同级 PnL 归因。
5. 储气和提名原型还不是客户工作流。
6. 订单和 PnL 是只读导入观测；系统不创建、修改、取消、路由或执行订单，也不做交易捕获。

## 下一步

按照 [NEXT_DEVELOPMENT_QUEUE-CN.md](NEXT_DEVELOPMENT_QUEUE-CN.md) 推进基于 PostgreSQL 的组合网络优化。在 API/SDK 暴露前，先完成数据合同、来源追踪和阻断逻辑。
