# 生产数据源运营手册

英文版：[PRODUCTION_SOURCE_OPERATIONS.md](PRODUCTION_SOURCE_OPERATIONS.md)

## 范围

R33 为公共数据源摄入增加生产化控制。Provider 仍只由后端脚本/连接器调用，
客户端不得直连 provider。

## 公共数据源批准

**为什么全新安装读不到 ENTSOG 或 GIE 数据。** `scripts/ops/ingest_public_sources.py` 在每次实时读取前检查一道默认拒绝的闸门：数据源族须在授权基线内、其运行操作未被停用；对于 ENTSOG、GIE（以及需许可的 EEX）还须存在 `live_validated` 且包含两项必需检查的认证记录。ECB 无需认证；EIA、ENTSO-E、Elexon、National Gas、利率与 REMIT 采集脚本不经过此闸门。此前产品中没有任何步骤生成 ENTSOG/GIE 记录：2026-11-12 实时上线时是用客户镜像中不存在的工程命令手工认证的，因此每个全新安装（包括演示）都显示 `source_gate_blocked`。另有两项配置缺陷：客户 worker 运行 ENTSOG 时未设窗口（被拒绝），且使用 100 的样本页大小（读取 200 条占位记录后停止，`entsog_empty_normalization`）；现均改用调度器的读取边界。

**产品步骤。** 闸门保留。由管理员代表公司批准 ENTSOG 与 GIE：管理 → 数据源（“需要您批准的公共数据源”）、`POST /api/sources/{source_id}/approve`（ADMIN；请求体 `reason`、`accept_terms`）或 `scripts/ops/approve_public_source.py`（`--list`、`--source`、`--all-open`，幂等）。批准前先显示提供方条款摘要；记录批准人、时间、原因及所接受的摘要版本，写入审计事件 `source.approval`，并执行有界实时验证（少量实时样本、规范化器试运行、字段结构检查；不存储任何数据）。GIE 若在密钥之前获批，状态为“已批准，等待密钥”，密钥到位后的首次读取会以批准人的记录执行验证。批准之前，运行以稳定原因码 `source_not_approved` 被拒绝，`/api/sources`、交易台页面与 `/api/health/ready`（`attention`）均会显示。

| 类别 | 数据源 | 全新安装需要 |
|---|---|---|
| 无需批准 | ECB 汇率、€STR、SONIA、SOFR、Elexon、National Gas、ENTSOG UMM、ECMWF Open Data | 无 |
| 仅需密钥 | EIA、ENTSO-E、GIE IIP REMIT | 密钥 |
| 需要批准 | ENTSOG 流量、容量、参考网络 | 管理员批准 |
| 需要批准与密钥 | GIE AGSI/ALSI | 批准与 GIE 密钥 |
| 仅限许可 | EEX、ICE Endex、ICE OCM、CME、NGX、Trayport、Platts、ICIS、Argus、Kpler、天气供应商、WM/Reuters、BFIX | 客户自有许可、凭据与数据范围 |
| 非数据馈送 | TSO 费率登记、`*_Sim` 演示源、模型服务 | — |

## 重试策略

`src/eurogas_nexus/application/source_operations.py` 是受限指数退避策略的
唯一 owner：

| 来源 | 最大重试 | 首次退避 | 新鲜度 SLA |
|---|---|---|---|
| ENTSOG | 3 | 30s | 60 min |
| GIE | 3 | 60s | 360 min |
| ECB | 3 | 300s | 1440 min |
| NationalGasNTS / BBL / IUK | 2 | 60s | 43200 min |
| Weather | 3 | 60s | 360 min |

未知来源使用安全默认值（3 次重试、30s 退避、24h SLA）。

## Worker

```bash
python scripts/ops/run_public_ingestion_worker.py \
  --source entsog --source gie \
  --limit 10000 \
  --interval-seconds 3600 \
  --retry-max 3 \
  --retry-backoff-seconds 30
```

每个 interval 在重试策略下运行 `ingest_public_sources.py`。失败 iteration
只记录并继续监督；`ingestion_runs` 仍是每次运行的证据真相。

## 新鲜度 SLA

新鲜度阈值以连接器清单为唯一来源（FRESH-01，见 [DATA_FRESHNESS.md](DATA_FRESHNESS.md)）：
`/api/sources` 为每个来源返回按数据集的 `freshness_contract`（预期、最近接收、下次预期、状态）。
TSO 费率来源为人工登记（`manual_register`），不会触发延迟或过期告警。下文旧表
（`evaluate_source_sla`）在产品中无调用方，不是实际生效的阈值。

`evaluate_source_sla(source_system, last_success_at_utc)` 依据上表返回
`live`、`stale` 或 `unknown`。Source Center 继续按来源展示
`freshness_status`。

## 剩余生产工作

- 部署调度器（systemd/Kubernetes/Windows 任务）不属于本仓库。
- 商业 provider 仍受凭据、entitlement 和 `provider_certifications` live 验证
  门控。
