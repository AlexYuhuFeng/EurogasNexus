# 功能引擎改进

F01 已通过 PR #46 合入。F02–F09 的实现与验证见 `feature/functional-engine-followup`。另有[英文说明](FUNCTIONAL_ENGINE_IMPROVEMENTS.md)。

| 阶段 | 交付内容 |
| --- | --- |
| F01 | 对比有天气输入与无天气输入时的平衡预测，并保存可重放的输入。 |
| F02 | 从运行库读取平衡历史和经认证的 ECMWF 预报，记录区域权重、预报批次、可用时点和覆盖情况。 |
| F03 | 保存输入、依赖版本、计算环境和结果。既有优化与回测也记录统一的计算清单。 |
| F04 | 按实体、产品、单位、时间窗、时效与修订检查数据，列出回补区间并标记需要重算的结果。 |
| F05 | 明确各引擎的适用约束。二阶段资源池与跨日联合优化共用求解核心，保留不可行场景的诊断。 |
| F06 | 按时间滚动验证天气模型，对照基准，分开校准区间与评估表现。合格模型可冻结并做影子运行和事后评价。 |
| F07 | 联合优化合同资源、共享管容和跨日储气，输出各期库存、成本收益明细、瓶颈和容量边际价值。 |
| F08 | 资源分配、联合优化和回测共用按实际天数计算的单利口径，支持合同各自的利率与计息基础。 |
| F09 | 通过 API、SDK 和命令行提交任务、查询进度、取消、恢复、比较和重放。 |

运行库需要迁移到 `0059_functional_runs`。使用具名分析师身份提交任务。请求包含
`kind`、`inputs` 和 `idempotency_key`。提交后用运行 ID 查结果，用 Job ID 取消。
重放沿用原始输入和计算版本，使用新的幂等键。

```text
eurogas-nexus --base-url https://nexus.example.com functional submit --input run.json
eurogas-nexus --base-url https://nexus.example.com functional status --id <run-id>
eurogas-nexus --base-url https://nexus.example.com functional cancel --id <job-id>
eurogas-nexus --base-url https://nexus.example.com functional replay --id <run-id> --input replay.json
```

西北欧平衡的目标是挪威管道气、LNG 气化外输和储气净提取的合计需求。使用
`use_runtime_history` 可在服务端冻结当前聚合历史及换算假设，`persisted_weather`
读取符合认证、权限和时点要求的天气窗口。区域权重配置可单独冻结，由有复核权限的
所有者确认后通过 `weather_profile_id` 引用。停运预测按未来与近期停运容量的差值
调整，持续停运不会从已经下降的近期流量中再扣一次。

模型验证需要保留预报和实测各自的可用时间。合格模型可冻结后做影子预测，待实测
到达再计算偏差与误差。生产采用仍需用部署环境中的真实数据验证样本外表现。
联合优化支持连续数量和能量守恒的库存模型，注采效率为 1。涉及损耗的单设施场景
仍可使用现有储气调度引擎。

数据就绪任务返回可回补的区间。通过版本对账标记需要重算的历史结果，再走现有数据源
回补流程。任务进程重启后，可用 `python scripts/ops/run_functional_worker.py`
继续处理数据库中排队的工作。
