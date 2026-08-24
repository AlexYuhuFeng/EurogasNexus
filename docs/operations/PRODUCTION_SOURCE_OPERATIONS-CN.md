# 生产数据源运营手册

英文版：[PRODUCTION_SOURCE_OPERATIONS.md](PRODUCTION_SOURCE_OPERATIONS.md)

## 范围

R33 为公共数据源摄入增加生产化控制。Provider 仍只由后端脚本/连接器调用，
客户端不得直连 provider。

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

`evaluate_source_sla(source_system, last_success_at_utc)` 依据上表返回
`live`、`stale` 或 `unknown`。Source Center 继续按来源展示
`freshness_status`。

## 剩余生产工作

- 部署调度器（systemd/Kubernetes/Windows 任务）不属于本仓库。
- 商业 provider 仍受凭据、entitlement 和 `provider_certifications` live 验证
  门控。
