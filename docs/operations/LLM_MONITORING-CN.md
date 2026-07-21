# DeepSeek 实时监控与交互

## 目的

Eurogas Nexus 将 DeepSeek 作为确定性监控结果之上的受控分析层。价差发现、
管容可行性、路径成本、策略规则、数据质量和风险判断由后端确定性引擎完成，
并以 PostgreSQL 为唯一运行时事实来源。DeepSeek 只负责解释、关联和回答用户
问题，不负责产生事实数据，也不能执行任何业务动作。

V1 固定使用 **DeepSeek V4 Flash**，API 模型 ID 为
`deepseek-v4-flash`。后端使用 `https://api.deepseek.com` 及其兼容 OpenAI
的 Chat Completions 接口；客户端不得覆盖模型或供应商 Base URL。

固定工作流如下：

1. 后端把报价、机会、策略告警、数据更新记录、证据、假设和警告写入 PostgreSQL。
2. `monitoring-worker` 每 10 秒扫描一次数据库。
3. 当前有效条件按稳定指纹归一化写入 `monitoring_alerts`。
4. 新告警、重新出现的告警或严重度升级的告警可以调用真实 DeepSeek API 生成解释。
5. Web 和桌面客户端每 10 秒通过 API 读取告警，并在顶部“告警”中心展示。
6. 用户可以确认告警，或针对该告警向 DeepSeek 继续提问；只有点击“发送”才会调用。

所有结果都要求人工复核。大模型不能下单、提交提名、预订管容、审批合同或修改源数据。

## 配置 DeepSeek API Key

实时大模型功能需要服务器能够访问 `https://api.deepseek.com`。API、PostgreSQL
和 `monitoring-worker` 必须处于运行状态。

1. 打开 **Workspace > Operations > Data Sources（数据源）**。
2. 选择 **LLM** 分类和 **DeepSeek LLM** 数据源。
3. 供应商选择 `DEEPSEEK`。
4. 输入不含秘密的标签，例如 `operator-default`。
5. 在密码输入框中输入客户自己的 DeepSeek API Key。
6. 点击 **保存凭据**。
7. 点击 **测试实时连接**。
8. 确认状态变为 `connection_test_success`。

客户端只向后端提交一次明文。后端加密后写入 `provider_credentials`；API 只返回
脱敏预览和测试状态。密钥不得写入 Git、提交到仓库的 `.env`、命令历史、截图、
报告、工单或客户端本地存储。

AllInOne/Server 安装会生成 `EUROGAS_NEXUS_SECRET_KEY`，用于保护数据库中的供应商
凭据。该加密密钥丢失后，原有凭据行无法解密，应在恢复运行时后轮换供应商密钥。

## 调用频率与费用控制

worker 不会每 10 秒对同一条件重复调用 DeepSeek：

- 新告警：调用一次；
- 同一告警且严重度未变化：不重复调用；
- 严重度升级：重新调用一次；
- 已解决告警再次出现：重新调用一次；
- 供应商调用失败：最早五分钟后重试；
- 每次 worker 扫描：最多补充分析三条告警；
- 用户追问：每次点击“发送”调用一次；
- Review 分析或组合报告：用户明确提交后调用一次。

告警稳定指纹不包含报价 ID 和扫描 ID，因此连续重新计算的同一价差不会每个 tick
都创建新告警。

## 可见状态

顶部告警中心展示：

- 活动、已确认、严重和警告数量；
- 确定性引擎生成的中英文标题和证据摘要；
- 分类、更新时间、出现次数和模拟价格输入标记；
- DeepSeek 状态及双语解释；
- 确认按钮；
- 每条告警独立的 DeepSeek 对话输入框。

大模型状态含义：

| 状态 | 含义 | 操作建议 |
| --- | --- | --- |
| `success` | DeepSeek 已返回结果。 | 对照证据和来源人工复核。 |
| `pending` | 新告警或升级告警等待分析。 | 等待下一次 worker 周期。 |
| `missing_credential` | 无法取得已启用的 DeepSeek/LLM 凭据。 | 在数据源页面保存并测试密钥。 |
| `provider_http_error` | 供应商拒绝、鉴权失败或限流。 | 检查账户、额度和服务状态。 |
| `provider_call_failed` | 网络、超时或响应解析失败。 | 检查服务器出站 HTTPS/DNS，五分钟后重试。 |

同一数据源连续三次更新失败后，告警从 warning 升级为 critical。即使 DeepSeek
不可用，市场机会和策略事实仍由数据库中的确定性结果持续展示。

## API

所有客户端只使用稳定的 `/api`：

- `GET /api/monitoring/alerts`
- `GET /api/monitoring/summary`
- `POST /api/monitoring/alerts/{alert_id}/acknowledge`
- `POST /api/monitoring/alerts/{alert_id}/analysis`
- `POST /api/credentials/DEEPSEEK/connection-test`
- `POST /api/analysis/query`
- `POST /api/reports/portfolio`

客户端不得直连 PostgreSQL，也不得直接调用 DeepSeek。

Python SDK 从 `eurogas_nexus.sdk.monitoring` 导入：

```python
from eurogas_nexus.sdk.monitoring import (
    analyze_monitoring_alert,
    fetch_monitoring_alerts,
    fetch_monitoring_summary,
)

alerts = fetch_monitoring_alerts("https://nexus.example")
summary = fetch_monitoring_summary("https://nexus.example")
analysis = analyze_monitoring_alert(
    "https://nexus.example",
    alerts[0].alert_id,
    question="交易台下一步应复核哪些证据？",
    language="zh-CN",
)
```

SDK 只调用同一后端 API，不接收 DeepSeek API Key。

## 运维验证

以下命令不包含密钥。禁止把 API Key 作为命令行参数：

```powershell
docker compose --env-file .env -f compose.yaml --profile monitoring ps
docker compose --env-file .env -f compose.yaml logs --tail 100 monitoring-worker
```

通过数据源页面录入密钥并执行实时连接测试，通过顶部告警中心执行一次真实问答。
确认 `provider_status` 为 `success`、结果可见，并确认 API 响应和日志中没有密钥。

自动化测试会替换供应商 callable，不会访问 DeepSeek。
