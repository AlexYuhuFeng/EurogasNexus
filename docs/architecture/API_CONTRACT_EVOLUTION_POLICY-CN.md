# API 契约演化策略

2026-11-26 新增计划输入读取：一条路径、一个操作，为 READ：`GET /api/optimization/planning-inputs`。创新分支接口统计：
316 条路径 / 352 个操作（在 315 / 351 基础上 +1 / +1）。

2026-11-26 新增拓扑读取：一条路径、一个操作，为 READ：`GET /api/reference-network/supply-corridors`（参考管网的供应走廊；
参考数据，不含账簿数据）。创新分支接口统计：315 条路径 / 351 个操作（在 314 / 350 基础上 +1 / +1）。

2026-11-26 新增天然气期权结算价读取（自基于 main 的演示评审移植）：两条路径、两个操作，均为 READ：
`GET /api/market/options/surface` 与 `GET /api/market/options/metrics`。创新分支接口统计：314 条路径 / 350 个操作
（在 312 / 348 基础上 +2 / +2）。

2026-11-26 新增 `GET /api/stream/live?topics=...`（服务器推送事件，按调用方自身权限过滤）：按订阅主题
推送 `change` 变更通知（`topic`、`changed_at`，不含数据行与数值）。市场事件发件箱（`market_events`，经
变更流读取）提供价格（含汇率、利率）、停运、费率、船货、账簿（合同、估值、限额、假设、运费）、容量、
数据源与新闻；屏幕报价、成交、告警、提名、费率公告及地图的停运、流量、船货、窗口与机会读自各自的表。
`jobs` 事件推送调用方自己的作业进度（`job_id`、`kind`、`status`、`progress`、`step`）；每 5 秒一次
`heartbeat`。支持 `Last-Event-ID` 或 `last_event_id` 断点续传（`live|<时间>|<发件箱游标>`，时间最多回溯
15 分钟）。创新分支接口统计：312 条路径 / 348 个操作（在 311 / 347 基础上 +1 / +1）。

2026-11-26 新增每位用户自己的告警标记（演示测试告警中心）：一条路径、两个操作，均为 READ。`GET /api/me/alert-state` 返回调用方对其可见的未解决告警的已读与忽略标记；`POST /api/me/alert-state` 仅为调用方将告警标记为 `read`、`dismiss` 或 `restore`（1-500 个 id），未知或不可见的 id 列在 `not_found` 下。共享且有审计的告警状态不受影响；告警复发或升级时标记失效。存于 `monitoring_alert_reader_state`（迁移 `0089_alert_reader_state`）。接口统计：311 条路径 / 347 个操作（在 310 / 345 基础上 +1 / +2）。

2026-11-26 新增带影响的方案、按合同计算的滞期费与管道供应的 REMIT 停运（Commercial Intelligence V3
LNG-4，ADR 决策 37）：两条路径、两个操作，其余变更均为新增字段。
`GET /api/lng/cargoes/{cargo_id}/disruption-options`、`GET .../disruption-options/{option_id}` 与
`GET /api/lng/disruption/frontier` 接受可选查询参数 `reporting_currency`（EUR|GBP|USD）、`fx_source`
（ECB|WMR|BFIX|manual，默认 ECB）、`fx_fixing`、`fx_rate_date`、`fx_rate`（与 `manual` 同用，为每 1 欧元
折合的 `fx_currency` 数量）与 `fx_currency`（USD|GBP）；无法使用的汇率选择为 422 `fx_choice_invalid`，
主体未持有有权使用的定盘价的授权来源（WMR、BFIX）为 403 `fx_source_entitlement_denied`。每个方案新增
`possible`（实物上可行；`feasible` 含义不变）、`rank`（按交易台排序权重，1 为首位）、`flags`
（`physically_possible`、`contract_breach`、`disrupts_normal_cargo`）、`breaches[]`（义务、合同、对手方、交付点、
逐燃气日短缺量、`penalty_eur_mwh` 及 `penalty_held` 与 `penalty_terms`，或“未持有罚则”，以及
`exposure_eur`）、`disrupts[]`（方案调整的按计划运行的船货或供应及原因）、`recommended_as[]` 与
`recommended_why[]`、`covers[]`（为短缺义务购买的替代供应）、`direct_pnl_expected`、
`opportunity_cost_expected`（预期损益 = 直接损益 − 机会成本）、`opportunity[]`（延误的靠泊、放弃的容量或
储气，各含 `value_eur`、`sources[]` 及受影响的船货）与 `reporting`（按报告币种的数值），每条供应腿新增 `demurrage`（条款及按合同币种与欧元并列的金额）；方案类型新增
`substitute` 与 `spot`；每个情景新增 `direct_pnl` 与 `opportunity_cost`。读取结果新增
`recommended_set[]`（`option_id`、`key`、`title`、`basis` clean|best_expected|overall、`reason`）、
`valuation`、`demurrage`（租船合同或确认通知所载费率、币种、来源与条款、装卸时间、`eur_per_day` 及含来源、
名称与汇率日期的 `fx` 换算）、`fx`（所用选择、汇率日期与来源）与 `pipeline_outages[]`。单个方案的
`arithmetic` 算式行新增 `sources[]`（所用价格、汇率与费率）与 `basis`（direct|opportunity）。
`POST .../choose` 的请求体接受同样的汇率字段；违约方案可以选择（仅实物上不可行的方案为 409
`option_infeasible`），返回的决定新增 `recommended_set`、`consequences`（标记、违约、被调整的船货、机会成本、
替代供应、排名）与 `fx`。新增 `GET /api/lng/pipeline-supplies/{supply_id}/outage-links`（READ，
PORTFOLIO_READ，按账簿范围）返回关联到该供应的 REMIT 消息（消息编号、版本、状态
applied|unsized|withdrawn|ended、匹配依据与原因、不可用比例及逐燃气日削减量）、`outage_mode`（auto|manual）、
手动输入的日期，以及估值所用削减量及每日来源；未知或超出范围的供应为 404 `pipeline_supply_not_found`。
新增 `PUT /api/lng/pipeline-supplies/{supply_id}/outage-override`（GOVERNED，PORTFOLIO_WRITE，审计
`lng.pipeline_outage_override`）接受 `outage_mode`、`curtailed`（[燃气日, MWh] 对，最多 400 个）与
`reason`；超出供应期间或高于日量的日期为 422 `curtailment_invalid`，未知模式为 422 `outage_mode_invalid`。
推荐方案集变化的通知标题为“Recommended options changed”。ETRM 船期导入新增可选列 `laytime_hours`、
`demurrage_rate_per_day`、`demurrage_currency` 与 `demurrage_terms`。不预订、不交易、不提名、不发送任何内容。
接口统计：305 条路径 / 340 个操作（在 303 / 338 基础上 +2 / +2）。设计见
`docs/engineering/Commercial-Intelligence-V3/17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md`。

2026-11-25 新增公开费率与容量窗口（Commercial Intelligence V3 TAR-1，ADR 决策 34）：三条路径、三个操作，均为 READ
且只读。新增 `GET /api/tariffs`（筛选 `publisher`、`facility`、`operator`、`direction` ENTRY|EXIT、`product`、
`status` INDICATIVE|FINAL、`on` 某燃气日、`key`；`as_of` 为 ISO 8601 UTC；`history` 为 true 且带 `key` 或
`facility` 时返回全部版本；`limit` 1 至 2000、`offset`）：`rows[]` 为费率版本（`tariff_key`、`version`、
`version_id`、`change_kind` first|revised|status_change|withdrawn、`status`、`status_basis`、`status_change`、
发布方、设施、运营商、方向、产品、期限、可中断性、`value` 或 `by_class`、单位、币种、费率期、`published_at_utc`、
`retrieved_at_utc`、`recorded_at_utc`、`superseded_at_utc`、`source_url`、`content_hash`、`event_id`、`withdrawn`），
以及 `total`、`as_of`、`history`。新增 `GET /api/tariffs/publishers`：发布方登记（页面、频率、格式、`manual` 或
`parsed`、条款状态），附已持有的内容、最近读取时间、下次轮询、`missed_publications`，以及条款要求许可的接收站的
`firm_permission`。新增 `GET /api/capacity/notices`（`kind` auction|lng_slot|secondary_capacity、`product`、
`facility`、`publisher`、`days` 1 至 400、`past_days` 0 至 31）：按 CAM 网络规则推导的容量拍卖（`basis`
`rule_derived`）与运营商发布的窗口期和开放季（`basis` `published`），各附开放与截止时间、提供内容与来源。行仅限调用方
可读的发布方来源族；条款需公司许可的接收站在记录许可前不返回。422 `history_needs_scope`、`as_of_invalid`、
`as_of_in_future`；无运行时数据库时三者返回空结果并附警告；已配置但不可读时返回 503 `runtime_db_unavailable`。其他新增：
市场事件类型 `tariff.changed`（每个新版本一条，`source_id` 为发布方来源族，载荷含版本标识、状态、`previous_status`、
`status_change`、数值、单位、费率期、`source_url`、`content_hash`），按市场规则经 `GET /api/market/changes` 提供；
监控告警类型 `tariff_publisher_stale` 与 `tariff_publication_missed`（类别 `data_source`）及
`capacity_window_opening`（新类别 `capacity`，路由至通知类别 `nomination`）；估值快照的费率输入新增
`detail.tariff_version`、`detail.tariff_status_basis`、`detail.tariff_source_url`；公开数据源导入报告的 ENTSOG 费率
明细新增 `tariff_versions` 与 `tariff_events`。迁移 `0083_tar1_tariff_book`（表 `tariff_versions`、`capacity_notices`，
仅扩展）。统计：299 条路径 / 334 个操作（在 296 / 331 上 +3 / +3）。登记：`docs/data/TARIFF_PUBLISHER_REGISTRY.md`。

2026-11-25 新增燃气日对账（Commercial Intelligence V3 SCHED-1）：一条路径、一个操作。新增
`GET /api/desk/gas-day/{gas_day}/reconciliation`（READ，需 `portfolio.read`，否则 403 `permission_denied`）：
按枢纽（交接点）与交易对手给出该燃气日的交易、对手确认、提名与 TSO 匹配数量；`groups[]`（`hub`、`point`、
`counterparty`、`shipper_codes`、`traded`、`confirmed`、`nominated`、`tso`，各为 `{value, unit, mwh, kwh_h}` 或 null，
`held`、`state` break|matched、`urgency`、`cutoff`、`minutes_left`、`mwh_at_risk`、`break_ids`、`book_ids`、
`trades[]`、`nominations[]`、`simulated`）与 `breaks[]`（`id`；`kind` 为 not_nominated、nomination_without_trade、
quantity_mismatch、counterparty_mismatch、shipper_code_mismatch、wrong_direction、lesser_rule_cut、late、
unit_mismatch、gas_day_misaligned、not_confirmed 之一；`explanation`、`explanation_zh`、`next_step`、`next_step_zh`、
`gap_mwh`、`mwh_at_risk`、`quantity`、`figures`、`urgency` due_soon|open|passed|closed、`severity`、`cutoff`、
`minutes_left`、`cash_out`（`basis` 为 indicative|missing|not_an_imbalance）、`trade_ids`、`line_refs`、`book_ids`），
按距该枢纽下一截止时间、再按风险 MWh 排序；另有 `hubs[]`（含截止时间）、`counts`、`kinds`、`mwh_at_risk`、
`exchange_trades[]`（只计数，不对账）、`empty` 与 `execution`（不提名、不确认、不发送）。筛选 `hub`、
`counterparty`（子串）、`kind`、`book_id`、`breaks_only`；`format` 为 `json`（默认）或 `csv`（每项差异一行，表头固定，
适用 GOV-1 导出决定）。404 `book_not_in_scope`；422 `unknown_kind`、`gas_day_out_of_range`（距今超过 31 天）。
范围同燃气日读取（授权账簿，否则调用方可见的全部账簿）。`GET /api/desk/today` 的"需要我处理"可含 `kind` 为
`reconciliation` 的条目（`break_kind`、`hub`、`gas_day`、`explanation`、`explanation_zh`、`quantity`、`deadline_utc`、
`target`）；`GET /api/monitoring/alerts` 可含类别 `gas_day_break`（按账簿范围；通过现有 `nomination` 类别通知）。
导入契约 `etrm.nominations.v1` 新增可选列（`counterparty`、`direction`、`point`、`shipper_code`、
`counterparty_shipper_code`、`counterparty_quantity_mwh`）、步骤 `trade_confirmation` 与行前缀 `counterparty:`；
不含这些列的文件照旧读取（迁移 `0085_sched1_nomination_matching`，仅新增可空列）。路径统计：296 条路径 / 331 个操作
（在 TAR-1 之后的 295 / 330 上 +1 / +1）。

2026-11-25 新增新闻与事件（Commercial Intelligence V3 NEWS-1，ADR 决策 35）：三条路径、三个操作。新增
`GET /api/news`（READ；`/api/news/` 属于商业数据边界）：来自登记公开来源的条目（平台已持有的 REMIT 消息、
条款允许再利用的官方订阅源），筛选参数 `hub`、`country`、`type`（`outage`、`sanction`、`policy`、`weather`、
`strike`、`geopolitical`）、`source`、`since`、`mine`、`order`（默认 `relevance`，触及调用方账簿的条目优先；
或 `time`）与 `limit`（1 至 200）；每条含来源、URL、发布方、发布与获取时间、内容哈希、语言、许可说明、标签与
`relevance`；`meta.sources` 列出来源登记及各来源条款与最近一次轮询。新增 `GET /api/news/{item_id}`（READ）：
条目及其来源登记行、`linked_exposures`（触及的合同、船货与提名，仅限调用方可见账簿且仅对可读取组合的调用方）、
`related` 相关条目与规则 `note`（逐句引用证据编号，并附 `citations`）。新增 `POST /api/news/{item_id}/note`
（GOVERNED；请求体 `language` 为 `en` 或 `zh-CN`）：在组织、部署与调用方均允许且每句话通过依据校验时，返回
AI 用途 `news_note` 的 AI 说明（"对我的账簿意味着什么"），标注 `AI-generated` 与提示词版本；否则返回规则说明，
`ai.status` 为 `off`、`refused`（附未通过的检查）或 `unavailable`；每次 AI 请求记入审计（`ai.news_note`）。
422 `type_unknown`、`source_unknown`、`since_invalid`、`order_unknown`；404 `not_found`；503
`runtime_db_not_configured`。市场事件类型 `news.published`（来源 `src-news`）。迁移 `0084_news_items`。
统计：299 条路径 / 334 个操作（在 296 / 331 上 +3 / +3）。来源与条款：`docs/integration/NEWS_SOURCE_REGISTRY.md`。

2026-11-24 变更与新增（限额与参考数据的双人复核，Commercial Intelligence V3 P-17，ADR 决策 32）。**状态码变更：**
当该写入启用四眼复核（默认启用）时，`PUT /api/portfolio/credit-lines/{id}`、`PUT /api/portfolio/trader-mandates/{id}`、
`PUT /api/portfolio/hedge-approvals/{id}`、`PUT /api/portfolio/lng-terminal-terms/{id}`、`PUT /api/market/firm-marks`
与 `PUT /api/lng/freight-routes/{route_id}` 返回 **202**（而非 200），附 `pending_approval: true`、`changed`（将变更的字段）
与 `change`（提议），在另一位有权限的人批准前不保存任何内容；未作修改的保存返回 200 且 `pending_approval: false`；
同一记录的第二个提议返回 409 `change_pending`。某写入关闭四眼复核时仍返回 200，并附 `pending_approval: false`。
把任何 2xx 视为成功的客户端仍可工作，但不得把 202 当作已生效。上述请求体均接受可选的 `change_reason`（最多 500 字符）。
新路径：`GET /api/portfolio/change-requests`（READ；`state` 为 pending、decided 或 all；`resource`；`limit`）返回
`changes[]`（`change_id`、`action`、`kind`、`label`、`label_zh`、`subject`、`target_key`、`new_record`、
`fields[]`（`name`、`before`、`after`）、`reason`、`state`、`proposed_by`、`proposed_by_name`、`proposed_at_utc`、
`decided_by`、`decided_by_name`、`decided_at_utc`、`decision_note`、`own`、`may_approve`、`may_reject`、
`may_withdraw`、`approver`）与 `four_eyes[]`（各写入、其审批人及当前是否需要）；
`POST /api/portfolio/change-requests/{change_id}/approve`、`.../reject`（请求体 `note`，必填）与 `.../withdraw`
（REVIEW；403 `four_eyes_required`、`own_mandate`、`segregation_of_duties` 或 `not_the_proposer`；409
`change_not_pending` 或 `change_stale`；422 `note_required`）。新增 `provenance`（`second_approval`、`set_by`、
`set_by_name`、`set_at_utc`、`approved_by`、`approved_by_name`、`approved_at_utc`、`change_id`、`reason`），见于
`GET /api/portfolio/credit-lines/{id}` 以及信用敞口、交易员授权使用、套保审批、LNG 接收站条款、公司估值标记和航运路线的各行。
`PUT /api/settings/organisation` 接受 `four_eyes`（上述六个动作到 true 或 false 的对象；ADMIN，记入审计）。审计动作
`change_request.propose`、`.approve`、`.reject`、`.withdraw` 与 `lng.freight_route` 为受治理写入（审计行无法写入时返回
503 `audit_unavailable`）。迁移 `0081_change_requests`。路径统计：288 条路径 / 323 个操作（此前 284 / 319）。

2026-11-24 新增 ETRM 与 ERP 导入契约（Commercial Intelligence V3 DATA-1）：两条路径、两个操作。新增
`GET /api/imports/contracts`（READ）：版本化文件契约（`etrm.deals.v1`、`etrm.physical_positions.v1`、
`etrm.nominations.v1`、`etrm.cargo_schedule.v1`、`erp.counterparties.v1`、`erp.invoices.v1`），各含列、
是否必填、键与落地表。新增 `POST /api/imports/{contract_id}/validate`（GOVERNED，ANALYST 起；
`/api/imports/` 属于商业数据边界）：`text/csv` 请求体至多 8 MB，`system`（必填）与 `on_error`（默认
`reject_file`，或 `skip_rows`）；返回报告（行数、接受数、`refused[]` 含行号、原因代码、说明与键，以及
写入将新增、更新、不变或删除的数量），不写入任何数据。404 `contract_unknown`；422 `column_missing`、
`column_forbidden`、`file_empty`、`encoding_invalid`；413 `file_too_large`。契约编号含版本；改变已接受
文件含义或拒绝曾接受文件的变更须发布新版本。统计：288 条路径 / 323 个操作（+2 / +2）。契约说明：
`docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md`。

2026-11-24 新增可刷新读取（Commercial Intelligence V3 DATA-1，经验 P7）：无新路径。`GET /api/market/prices`、
`GET /api/market/observations` 与 `GET /api/market/fx` 接受 `format`（默认 `json`，不变；或 `csv`）。CSV 为一行
固定顺序的表头，无论有无数据行、是否带 `as_of` 都相同（价格曲线按 `meta.columns` 顺序；观测与汇率按其 JSON
字段，版本列 `revision`、`revision_basis`、`published_at_utc`、`known_from_utc`、`revision_event_id`、
`as_of_utc` 位于 `metadata_json` 之前，不带 `as_of` 时为空），UTF-8 带字节序标记，嵌套值写为 JSON 文本。文件
按其数据行来源的授权数据族应用 GOV-1 导出决定（`X-Eurogas-Export-Decision`；条款未登记时 403
`export_denied`），并计为一次导出。未知 `format` 返回 422。接口统计不变：286 条路径 / 321 个操作。操作说明：
`docs/sdk/POWER_QUERY.md`。

2026-11-24 新增变更流（Commercial Intelligence V3 DATA-1，经验 P2）：一条路径、一个操作。
新增 `GET /api/market/changes`（READ，沿用 `/api/market/` 权限）：按游标返回其后记录的市场事件，从旧到新
（`after` 为本接口给出的游标，不给则从头开始，或 `latest`；`kinds` 可重复或以逗号分隔的事件类型；`subject`
为主题键前缀；`limit` 1 至 1000，默认 200）。每条变更只是摘要，列序稳定（`meta.columns`）：`cursor`、
`event_id`、`event_key`、`event_type`、`operation`（修订 1 为 `insert`，其后为 `update`）、`revision`、
`supersedes_event_id`、`subject_key`、`source_id`、`input_class`、`dependency_keys`、`content_hash` 以及
市场、发布、入库时间；从不返回事件数值，数值仍经授权读取接口获取。`meta` 含 `next_cursor`、`has_more` 与
`retention`。市场事件仅在调用者可读取其数据源族时返回（与市场读取一样计量）；交易台事件（合同、货船、估值、
假设、限额、运费）仅返回给持有 `portfolio.read` 且可见全部账簿的调用者。被隐藏的事件同样推进游标，且不向调用者
计数。游标无效 422 `cursor_invalid`，事件类型未知 422 `kind_unknown`。排序为（写入事务，`seq`），且只返回
写入事务已结束的事件，因此不会跳过任何已提交事件（迁移 0082 为 `market_events` 新增可空列 `writer_txid`，
仅扩展）。保留：`market_events` 不做清理，游标长期有效；将来若引入保留策略，过期游标须返回 410
`cursor_expired`。统计：286 条路径 / 321 个操作（+1 / +1）。设计：`application/change_feed.py`。

2026-11-24 新增按时点读取（Commercial Intelligence V3 DATA-1，经验 P1）：一条路径、一个操作。
`GET /api/market/observations` 与 `GET /api/market/fx` 接受 `as_of`（ISO 8601 UTC）：每个数值按该时刻
当时有效的修订返回，此后才首次入库的数值不返回；各行新增 `revision`、`revision_basis`（`market_event`
或 `stored_row`）、`published_at_utc`、`known_from_utc`、`revision_event_id` 与 `as_of_utc`。不带 `as_of`
时两者与此前完全一致。`as_of` 无法解析返回 422 `as_of_invalid`，晚于服务器时钟返回 422 `as_of_in_future`。
新增 `GET /api/market/prices`（READ，沿用 `/api/market/` 权限）：返回一个或多个枢纽的逐月价格曲线
（`hub` 可重复或以逗号分隔，`start` 为 YYYY-MM，`months` 1 至 36，`side`，`include_simulated` 默认 false，
`as_of`）：每个枢纽每个月一行平面数据，含 P-08 统一价格、类型、来源、时效与版本（`revision`、
`revision_basis`、`published_at_utc`、`known_from_utc`），`meta.columns` 给出稳定列序；无价格的月份仍有一行，
价格字段为空。未知枢纽 422 `hub_unknown`，未给枢纽 422 `hub_required`，月份错误 422 `start_invalid`。
权限过滤与许可数据计量同市场读取。接口统计：285 条路径 / 320 个操作（+1 / +1）。

2026-11-24 新增（货物变更送达各角色，Commercial Intelligence V3 LNG-2）：无新路径。
`GET /api/lng/cargoes/plans` 与 `GET /api/lng/cargoes/{cargo_id}/plan` 新增 `cargo.eta`
（`basis`、`confidence`、`source`、`recorded_at_utc`、`text`）；看板行新增 `attention[]`（每条未结角色消息一项：
`alert_id`、`role` trader|scheduler|risk|desk_head、`severity`、`title`、`title_zh`、`due_utc`、`mine`、
`updated_at_utc`），计划新增 `roles[]`（各角色关于最近一次变更的消息，含一天内撤回者，附 `lines`、`lines_zh`、
`items`、`inputs_as_of`、`withdrawn` 与 `mine`），均按货物所属账簿过滤。`GET /api/desk/today` 的“需要我处理”
可含 `kind` 为 `cargo` 的条目（附 `role` 与 `cargo_id`）。`PUT /api/settings/notification-channels/{id}`
接受类别 `cargo` 与 `desk_head`；`GET /api/monitoring/alerts` 可含类别 `lng_hedge`、`lng_schedule`、
`lng_exposure`、`lng_material`。LNG 头寸导入新增两个可选列 `eta_basis` 与 `eta_confidence`（迁移
`0080_lng_eta_basis`）。接口统计不变：282 条路径 / 315 个操作。设计见
`docs/engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md`。

2026-11-25 新增“先签约、后公开”的容量成本、费率年度与数据来源优先级（Commercial Intelligence
V3 TAR-2）：五条路径、五个操作，均为 READ，不写入任何数据。`GET /api/tariffs/years?facility=`
（可选 `direction`、`product`、`operator`、`as_of`；缺 `facility` 为 422）按费率年度返回
`years[]`：每项含 `tariff_year`（`label`、`convention`、首末燃气日）、方向、产品、`INDICATIVE`
与 `FINAL` 两个版本并列（与 `GET /api/tariffs` 的版本行相同，或为 null）、`versions`、`used`
（按 `as_of` 估值时采用的状态）与 `used_version_id`。`GET /api/capacity/bookings`（`kind`、
`facility`、`as_of`）列出调用方账簿内、在 `as_of` 时点持有的已导入订舱（获取方式、期间、数量与
单位、签约价格与单位、`price_recorded`、记录与释放时间等）。`GET /api/capacity/cost`（`kind`
pipeline|terminal、`facility`；管道需 `direction`、`first`、`last`、`mwh_per_day`，可选
`product`（默认 DAILY）、`premium`、`operator`；接收站需 `arrival`、`cargo_mwh`，可选 `product`
（默认 spot）；`as_of`）先按签约成本、再按公开费率计价，返回 `layers[]`（`layer`
contracted|public|not_held、数量、单位成本、成本、状态；签约层含 `booking_id`、`acquired_via`、
`contracted_price`；公开层含 `status_basis`、`tariff_year`、`version_id`、`published_at`
（发布方未注明时为 null）、`recorded_at`、`how_bought`、`premium`、`public_price`、`source`）、
`covered`、`total_cost`（不完整时为 null，绝不为零）、`complete`、`indicative`、`order`、
`order_source`、`sources[]`（按顺序列出各层级及是否采用、原因）与 `issues`；输入不符为 422
`capacity_cost_input_missing`、`period_too_long`（超过 400 个燃气日）或 `period_reversed`。
`GET /api/pricing/fx-rate?from=&to=`（`as_of`、`context`、`rate_type`）按企业的来源顺序解析一个
汇率，返回 `value`（每单位 `from` 折合多少 `to`，或 null）、`used_tier`、`source`、`order`、
`order_source`（`default`、`setting:<键>` 或 `calculation`）与 `sources[]`（各层级的 `used`、
`reason`：not_held|stale|not_covering|not_configured|not_entitled|not_tried|used、`note`，
采用的层级另含取值、来源、日期与方法）。`GET /api/pricing/source-precedence`（`context`）返回
各类数值的现行顺序 `kinds[]`、企业已配置的银行 `institutions[]`（不含任何凭据）与
`live_feed_terms`。其他新增字段：费率版本行增加 `tariff_year`、`status_rule`、`new`、
`published_at_stated`，`status_basis` 可为 `nc_tar_tariff_in_force`、
`nc_tar_yearly_auction_held`、`nc_tar_before_yearly_auction`（按所问时点重新判定；旧的
`period_started`、`period_not_started` 按同一规则重读）；发布方行增加 `tariff_year`、`cadence`、
`cadence_confirmed`；路径段增加 `indicative`、`version_id`、`version`、`tariff_year`、
`status_basis`、`published_at`、`recorded_at`、`cost_basis`（public|contracted|contracted+public）、
`layers` 与 `breakdown`；合同成本的 `basis` 可为 `contracted` 或 `contracted+public` 并附
`breakdown`；`POST /api/optimization/capacity` 接受可选 `held_capacity_mwh`（默认 0）与
`held_cost_gbp`，结果增加 `held_capacity_mwh`、`held_cost_gbp` 与 `layers`；
`PUT /api/settings/organisation`（ADMIN，审计 `settings.organisation.update`）接受
`source_precedence`（`kind` 或 `kind@context` 对应该类层级的有序列表）与
`financial_institutions`（键对应名称、是否签约、提供内容、接入方式 file|manual|api 等；api 需已
记录企业协议；任何凭据字段为 422 `setting_invalid`；值为 null 即删除）；告警可含类型
`tariff_final_published`；`tariff.changed` 载荷增加 `tariff_year`、`published_at_utc`、
`recorded_at_utc` 与 `new_final`。不进行任何订舱、竞拍、提名或发送。接口统计：308 条路径 / 343
个操作（在 303 / 338 基础上 +5 / +5）。

2026-11-25 新增组合扰动再优化（Commercial Intelligence V3 LNG-3）：四条路径、四个操作。
`GET /api/lng/cargoes/{cargo_id}/disruption-options`（READ，PORTFOLIO_READ，按账簿范围）围绕
账簿内所有受扰动的供应（晚于其时段开始到港的船货、有削减日的管道供应）重新优化，返回
`cargo`（含时段逐日 `entitlement`）、`status`（disrupted|affected|as_planned）、`scenarios[]`
（基准、按置信度前后移动 ETA、价格上下浮动）、`objectives[]`、涉及该船货的 `options[]`（每项含
可行性与原因、是否在帕累托前沿、被谁支配及原因、目标值、各情景损益、套保调整腿、各供应腿、
交付义务是否满足）、`frontier`、`recommended`、`preference`（权重、规则及来源）、`inputs`、
`warnings`、`timeline`（消费者的运行记录）与 `decision`（最近一次记录的选择）。
`GET /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}`（READ）返回单个方案的分项、
算式、各情景明细与授权使用变化；当前运行已无此方案时为 404 `option_not_found`。
`GET /api/lng/disruption/frontier?book_id=`（READ）返回整个账簿的方案与前沿；
`curtail_supply`、`curtail_from`、`curtail_to`、`curtail_mwh_per_day` 四者同时给出时，按削减
做一次只读假设（缺一为 422 `curtailment_incomplete`，最多 93 个燃气日）。
`POST /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose`（GOVERNED，
PORTFOLIO_WRITE，审计 `lng.disruption_choice`）仅记录所选方案及可选 `note`，返回
`booked: false`；不可行方案为 409 `option_infeasible`。不预订、不借气、不购买容量、不交易、
不提名。接口统计：296 条路径 / 331 个操作（在 292 / 327 基础上 +4 / +4）。

2026-11-24 新增 LNG 在途货物计划（Commercial Intelligence V3 LNG-1）：四条路径、四个操作。
`GET /api/lng/cargoes/plans`、`GET /api/lng/cargoes/{cargo_id}/plan` 与
`POST /api/lng/cargoes/{cargo_id}/plan/what-if`（READ）把一船货从 ETA、靠泊窗口、蒸发、
气代费、按燃气日的外输，一直连到各枢纽交割月的敞口、套保覆盖与建议（展期、卖出、买回、
短期补足、找窗口、滞期费）；what-if 不写库。`PUT /api/lng/cargoes/{cargo_id}/hedges`
（GOVERNED，PORTFOLIO_WRITE）替换该货物的套保腿，留审计并经市场事件发件箱发布
`cargo.changed`。仅作决策支持，不交易、不提名。接口统计：282 条路径 / 315 个操作。

2026-11-06 新增 `POST /api/portfolio/desk-replay`：按调用方提供的已授权证据，对单一账簿、枢纽与
燃气日做时点对账，并比较针对修订后停运的应对方案（#48-#50）。只读计算、不写数据库，位于商业
`/api/portfolio/` 前缀下，返回输入指纹与冻结输入以便重放，提供 Python SDK 方法与决策中心面板。
方案仅评估，从不执行。接口统计：241 条路径 / 261 个操作。

2026-11-05 新增 `POST /api/market/nwe-balance`，与原有 GET 并存，用于调用方显式提供
数据的天气情景对比。要求 governed 权限，不写数据库，返回输入指纹并提供 Python SDK。
详见[功能引擎改进计划](../engineering/FUNCTIONAL_ENGINE_IMPROVEMENTS-CN.md)。

英文版：[API_CONTRACT_EVOLUTION_POLICY.md](API_CONTRACT_EVOLUTION_POLICY.md)

## 目的

公开 `/api` 表面是五个消费方共享的产品契约：Web、Python SDK、CLI、
Windows/Linux 桌面外壳和双语运营文档。所有消费方都是同一契约的薄客户端，
因此契约只能通过审慎、有测试保障的流程演化。

本文档是契约演化的唯一策略，收敛路线图问题 D（stable unversioned `/api`
无演化策略、五个表面靠自觉同步）。

## 原则

1. **稳定无版本 `/api`。** 公开表面保持无版本 `/api` 前缀；运营与开发路由
   保持受配置门控的 `/api/internal`、`/api/dev` 前缀。任何情况下不提供
   `/v1` 或 `/api/v1` 别名。
2. **默认只增不改。** 新端点和新的可选响应字段是常规演化路径；既有路径、
   参数和字段含义不得静默变更。
3. **破坏性变更是重大事件。** 删除、重命名或改类型任何路径/参数/响应字段，
   必须有书面迁移计划（弃用 → 双轨运行 → 至少跨一个版本后移除）并经
   ExecPlan 评审；不存在原地破坏性变更。
4. **弃用必须显式。** 被弃用的路径或字段须在 OpenAPI 操作上标记
   `deprecated=True`、在运行时信封 `meta.warnings` 中说明，并在本文档弃用表
   登记移除日期；移除前保持可用。
5. **后端是规范化的唯一所有者。** 派生字段（FX 换算、tenor、hub、价差）由
   后端计算，客户端只消费、不得重实现领域逻辑。

## 兼容门

以下测试在契约漂移时让 CI 响亮失败：

| 门 | 文件 | 钉住内容 |
|---|---|---|
| 表面稳定性 | `tests/contract/test_api_surface_stability.py` | 公开路径精确集合；无 `/v1` 别名；仅声明前缀 |
| 文档计数 | `tests/contract/test_architecture_alignment.py` | alembic head、表数、文档化路由数 |
| SDK 对齐 | `tests/contract/test_sdk_backend_parity.py` | SDK DTO 与后端载荷契约 |
| 实时契约 | `tests/contract/test_realtime_contracts.py` | SSE/流式语义；禁 Kafka/Redis 字样 |
| 验证一致性 | `tests/contract/test_validation_consistency.py` | 文档中的规范验证命令 |

## 变更流程

1. 使用 `docs/engineering/EXECPLAN_TEMPLATE.md` 编写公开 ExecPlan，列明
   API 影响与回滚，并更新 ExecPlan 索引；如果变更引入新的规范合同，先
   遵循 `docs/engineering/RFC_PROCESS.md`。
2. 新增路径：同一变更中把路径加入
   `tests/contract/test_api_surface_stability.py` 的
   `PINNED_PUBLIC_PATHS`，并更新文档化路由数（`RELEASE_READINESS.md`、
   `-CN.md` 及 `test_architecture_alignment.py` 断言）。
3. 弃用路径：在 router 标记 `deprecated`、在信封加 warning，并登记到下方
   弃用表。
4. 被拒绝字段：在模型中保持声明，对非空值以稳定 `422` 错误码拒绝并列出每个
   违规字段，登记到上方“被拒绝的请求字段”表，并在同一次变更中从所有客户端
   请求构建器与客户端请求 DTO 中移除。
5. 先补 API、SDK、契约测试，再视为完成。
6. 运行 `CONTRIBUTING.md` 中的完整验证命令集。

## 已声明的新增路径

| 路径 | 声明来源 | 契约 |
|---|---|---|
| `POST /api/optimization/portfolio-network` | 已接受的发布合同 | 仅 DB `RUNTIME_DECISION`；只接受决策元数据，绝不接受客户端网络/费率/管容/价格事实 |
| `POST /api/optimization/storage-dispatch` | 已接受的发布合同 | 仅评估的储气调度；RUNTIME_DECISION 组装 PostgreSQL master/观测 |
| `POST /api/optimization/nomination-window` | 已接受的发布合同 | 仅评估的提名窗口；RUNTIME_DECISION 读取 DB 窗口 master；无提交动作 |
| `GET /api/optimization/nomination-windows` | 交易台时钟读取（Architecture V2 日视图） | READ 级别读取某个气体日已声明的 `nomination_window_masters`，同时给出声明的时钟时刻与其在该气体日解析出的 UTC 时刻。它暴露的是"声明"而非"评估"：不含市场材料、不含调度结果、不含提交动作。未配置 runtime DB 时返回空列表并在 `meta.missing_inputs` 说明原因；runtime DB 已配置但没有任何生效 master 时返回"已测量的零"并携带 `NOMINATION_WINDOWS_MISSING`，因此"今天没有窗口关闭"与"窗口未被读取"不会被混为一谈 |
| `GET /api/data-products` | Architecture V2 Wave 4（统一数据平台） | READ 级别的 Data Product 目录声明：产品 id、业务名称、可用状态、时间基准、声明的来源/授权族与今日服务端点，外加按主体的授权判定与新鲜度/溯源摘要。绝不返回 API 密钥、密钥值、调度器内部或重试轨迹；调用方无权访问的产品标记为 `restricted` 且不返回溯源块，既不省略也不显示为 0 |
| `GET/POST /api/analysis-snapshots` | Architecture V2 Wave 4（统一数据平台） | `POST`（GOVERNED，ANALYST 门槛）按当前 Active Context 记录 Analysis Snapshot 描述符；`GET` 列出最近的描述符。`GET` 保持 READ 门槛，因为描述符是血缘/溯源元数据、不含商业数值；其引用的每个数值仍在各自的商业端点之后 |
| `GET /api/analysis-snapshots/{snapshot_id}` | Architecture V2 Wave 4（统一数据平台） | 按可复现引用读取单个 Analysis Snapshot；未知引用返回 404 |
| `POST /api/research/cash-valuation` | 共享现金流估值能力（2026-09-30） | 仅沙箱（GOVERNED、商业边界内 ANALYST 门槛）地适配全仓唯一的共享现金流引擎：业务上下文以调用方提供的规范 `concept:value` 引用声明（绝不解析、绝不断言权限——`meta.references_verified: false`），金额/FX 汇率/贴现因子一律为精确十进制字符串（拒绝 JSON number），日期为 ISO 日期，Decimal 一律以精确字符串序列化。拒绝均为类型化稳定码（线格式问题 `422 cash_valuation_input_invalid`；引擎拒绝 `422 cash_valuation_refused` 并在 `detail.codes` 给出引擎稳定码）。无持久化、无 provider、无审计记录、无交易/提名/结算语义；`meta.customer_approval` 恒为 `false`。详见 [CASH_VALUATION_CAPABILITY.md](CASH_VALUATION_CAPABILITY.md) |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` | 合同修订集成（2026-10-01） | GOVERNED 级别（ANALYST 门槛）、位于商业边界内：有界地读取单个合同已捕获的不可变经济修订历史，按修订号升序（`limit` ≤ 200，配合 `offset`）。每行在返回前都经过校验（受审的捕获来源、存储哈希、规范解码、合同 id 与 schema 版本）；未知合同返回 404 `upstream_contract_not_found`，而已存在但尚无捕获的合同返回空页、`revision_count` 为 0 并附带显式警告。读取不会创建捕获、也不会改写归属。仅为诚实的证据：捕获不是完整历史，存储的经济条款 `payment_terms` 恒为 `null`——不推导、不暗示任何付款日期、贴现因子或估值 |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}` | 合同修订集成（2026-10-01） | GOVERNED 级别（ANALYST 门槛）读取单条经过校验的已捕获修订，并显式限定于 `contract_id`：属于其他合同的修订 id 与未知 id 一样返回 404 `contract_revision_not_found`。完整性校验失败时返回结构化 409，仅携带仓库稳定码与固定消息（绝不回显存储行内容、驱动文本或 SQL）。响应保留捕获来源、schema 版本、内容哈希、捕获时刻、原始记录人与原始操作备注 |

## 已声明的附加字段

对既有路径的字段级新增。它们不引入新路径、不放松门槛、不改变状态码；未发送该可选字段的调用方保持原有行为。

| 路径 | 字段 | 契约 |
|---|---|---|
| `POST /api/route-cost/recommend` | `analysis_snapshot_id`（请求可选，`data` 回显） | Architecture V2 Wave 4：产出建议所引用的可复现引用。运行前对持久化的 Analysis Snapshot 校验——未知引用返回 `422 analysis_snapshot_not_found`，无法校验时返回 `503 runtime_db_not_configured` |
| `POST /api/route-cost/resource-pool/optimize` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 5 后续把 Wave 4 的范围扩展到该运行路径：校验方式与拒绝码同建议路径一致；未引用快照时 `data` 中不出现该字段，因此此类调用方的载荷保持不变 |
| `POST /api/strategy-runs`（`run_type=BACKTEST`） | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到策略回测运行：运行前对持久化的 Analysis Snapshot 校验（被拒绝时不创建运行行、不创建作业），并在响应中回显；未引用时不出现 |
| `POST /api/analysis/query` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到分析（AI 证据）路径：在加载输入快照之前、且在调用任何 provider 之前完成校验，因此无法校验的引用绝不会以一次外部请求作为代价。拒绝码与其他路径一致；未引用时 `data` 中不出现该字段，且该引用随分析记录一并持久化 |
| `POST /api/reports/portfolio` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到组合报告：运行前校验，在报告中回显，并作为该报告所依据的快照记入受跟踪的 `REPORT` 作业（未引用时记录为空引用）。已存储的报告记录仅保留其章节与来源引用，没有存放被引用快照的列——此处如实记录，不作暗示 |
| `GET /api/optimization/nomination-windows` | `next_gas_day`、`next_opens_at_utc`、`next_closes_at_utc`（每个窗口行，客户端可忽略） | 日视图的后续补充，且属于同一族：窗口 master 是按日生效的规则，因此当所请求气体日的窗口已关闭时，可行动的时点是同一时钟在次日的气体日发生。两个发生均由接口按气体日日历解析，而不是由客户端在时钟上加一天；忽略这三个字段的 JSON 客户端所见载荷与之前完全一致 |

| `GET /api/decision-cases/{case_id}` | `pack`（对象，附加字段） | 决策包：同一个决策案面向"签署人"的组合视图——上下文、证据（每条引用所引快照的**可解析性经实测**：`true`/`false`/`null`，`null` 表示该引用未引用任何快照）、假设、备选、AI 发现、告警、已记录的人类决策、该案的审计轨迹（其动作记录在 `decision_case:<case_id>` 之下）、决策包自身的阻塞项与案子本身的阻塞项并列、`signable`、平台"不持有签名"的声明，以及带基准说明的规范化 `content_hash`。它附着于本读取而非新增路径，因为它**就是**该资源本身，而不是关于它的第二个答案；忽略该字段的客户端所见载荷与之前完全一致。读取决策案本就需要 runtime DB，因此没有新增被拒绝的情形 |
| `GET /api/portfolio/position-ladder` | `rows[].cargoes`（仅 JSON）、`legs.cargoes`（2026-11-24，QA-L-03） | 每行按 `cargo_id` 列出其中的公司船货及其 `physical_mwh`（计划外输）与 `financial_mwh`（记录的对冲）；无船货的行为 `[]`。`legs.cargoes` 为阶梯上的船货数。CSV/XLSX/PDF 下载列不变 |

| `GET /api/portfolio/credit-exposure`、`GET /api/portfolio/mandate-usage` | 每行 `marks_as_of`、`state`、`freshness_state`（附加字段，2026-11-24，QA-R-07） | 估值所用日收盘价的日期（该行各枢纽最新收盘价中最旧者；授权按 MWh 计量，为 `null`），`state` 为 `current`、`late`（晚一个工作日）、`stale`（更早）、`never`（授权为 `current`），`freshness_state` 为同一判定的行情用语（FRESH、LATE、STALE、MISSING） |
| `GET /api/portfolio/position-ladder` | 每行 `marks_as_of`、`state`；顶层 `marks_as_of`、`marks_state`（附加字段，2026-11-24，QA-R-07） | 枢纽最新收盘价及其状态；顶层为所持枢纽中最不新者，盯市与 VaR 据此说明估值日期。监控扫描新增 `limits` 告警 `marks_stale`（指纹 `marks_stale:credit`，警告级，按账簿可见），任一信用额度的估值价延迟或过期时触发 |
| `GET /api/access/users`、`POST /api/access/users`、`PATCH /api/access/users/{id}` | `segregation_warning`（附加字段，2026-11-24，QA-R-03） | 授权同时含 ANALYST 与 REVIEWER 时为 `code` `segregation_of_duties`、`roles`、`message`，否则为 `null`；不拒绝授权，服务器拒绝该人的风控写操作 |
| `PUT /api/settings/notification-channels/{channel_id}`、`GET /api/settings/notification-channels` | `categories` 新增取值 `opportunity` 与 `nomination`（2026-11-24，M7） | 机会告警（新引擎，路由给交易员）与燃气日提名截止及交付告警（路由给运营）各有自己的类别，调度员可只订阅提名。订阅了 `alert` 的渠道仍会收到这两类（伞形类别），既有订阅不受影响；空列表仍表示全部类别 |
| `PUT /api/settings/notification-channels/{channel_id}`、`GET /api/settings/notification-channels` | `categories` 新增取值 `cargo` 与 `desk_head`（2026-11-24，LNG-2） | `cargo`：货物变更给 LNG 交易员的套保建议；`desk_head`：按 `lng.material_change_mwh` 判定为重大的货物变更。订阅 `alert` 的渠道不会收到这两类；调度与风控的货物消息分别使用 `nomination` 与 `limits` |
| `GET /api/lng/cargoes/plans`、`GET /api/lng/cargoes/{cargo_id}/plan` | `cargo.eta`（附加字段，2026-11-24，LNG-2） | ETA 的依据：`basis`（master_notice、ais_declared、feed_estimate、schedule、manual 或 `null`）、`confidence`（high、medium、low 或 `null`）、`source`（设定该 ETA 的源系统）、`recorded_at_utc`，以及英文表述 `text` |
| `GET /api/lng/cargoes/plans` | `[].attention`（附加字段，2026-11-24，LNG-2） | 调用者可见（按货物账簿）的该货物未结角色消息，无则为 `[]`；角色与调用者某一工作职能相符时 `mine` 为 true |
| `GET /api/lng/cargoes/{cargo_id}/plan` | `roles`（附加字段，2026-11-24，LNG-2） | 各角色关于该货物最近一次变更的消息，含一天内撤回者；其中任何内容均不执行 |
| `GET /api/desk/today` | `needs_me` 中 `kind` 为 `cargo` 的条目，附 `role` 与 `cargo_id`（附加字段，2026-11-24，LNG-2） | 调用者本人角色（工作职能）的未结货物消息，严重者在前；`target` 打开交易台 → 货物并定位该货物；`why` 指向该告警 |
| `GET /api/monitoring/alerts` | `category` 新取值 `lng_hedge`、`lng_schedule`、`lng_exposure`、`lng_material`；`entity_type` `lng_cargo`（2026-11-24，LNG-2） | 每个货物每个角色一条告警，与限额一样按账簿可见；后续变更使其失去意义时以 `evidence_snapshot.withdrawn` 关闭 |
| `GET /api/monitoring/alerts` | `category` 新取值 `capacity`；`alert_type` 新取值 `tariff_publisher_stale`、`tariff_publication_missed`、`capacity_window_opening`；`entity_type` 新取值 `tariff_publisher`、`capacity_notice`（2026-11-25，TAR-1） | 发布方读取晚于其频率、运营商在 7 月年度拍卖前 30 天仍未发布下一费率期保留价格、容量拍卖或窗口期在三天内开放（月度拍卖不告警）；不进行任何订舱或投标 |
| `GET /api/market/quotes` | 每行 `resolved_price` (`hub`, `period_start`, `period_end`, `side`, `value`, `unit`, `value_mwh`, `unit_mwh`, `kind`, `source_system`, `as_of_utc`, `state`, `freshness_state`, `simulated`, `basis`, `reference`)（附加字段，2026-11-24，P-08、QA-T-02、QA-L-22） | 读取时刻该行枢纽与交割窗口在所有页面上显示的同一价格，来自 `domain/market/price_resolution`（最新的在期行情点或结算价，否则公司估值价，否则持有的最新价格并标为 stale；仅限有权使用的数据源）。行自身的报价字段不变；该窗口无任何价格时为 `null` |
| `GET /api/desk/today` | `key_figures` 中 `price.<hub>` 项、`market.hubs[].front_month` 及 `book` 行的 `mark` 上的 `resolved_price`（附加字段，2026-11-24，P-08） | 与价格看板上近月的对象相同；无价格时为 `null`。`close_day` 仍为最后一个月前收盘日 |
| `POST /api/analysis/brief` | `resolved_prices`（顶层列表，附加字段，2026-11-24，P-08） | 价格段每个枢纽行一个 `resolved_price` 对象；各段结构不变 |
| `GET /api/portfolio/position-ladder` | `rows[].resolved_price`（仅 JSON，附加字段，2026-11-24，P-08） | 该行 `mark` 所依据的价格；无价格时为 `null`。`mark_method` 也可能为 `firm_mark`（见下） |
| `GET /api/research/spreads/board` | 实时读取（无 `as_of`）时月前腿的 `locational[].tenors[].legs[].resolved_price`（附加字段，2026-11-24，P-08） | 其他页面为该腿枢纽与月份显示的价格；价差本身仍按收盘价对收盘价比较 |
| 估值快照价格输入（机会评估、LNG 船货经济性） | `detail.price_kind`、`detail.state`、`detail.resolution`（附加字段，2026-11-24，P-08） | 评估所用价格在解析器中的类型、新鲜度状态与依据 |
| `GET /api/opportunities/{opportunity_id}`（`object.assumptions[]`，以及冻结它的版本载荷与决策案证据） | `book_id`、`set_id`、`set_name`、`set_version`（附加字段，2026-11-24，P-11） | 取值所依据的已批准假设集：`book_id` 为持有该值的账簿自有假设集，全公司假设集时为 `null`；`origin` 仍为 `firm_set`。账簿范围取值的 `input_key` 为 `assumption:<key>@book:<book_id>`，其依赖键仍为 `assumption:<key>` |
| `GET /api/settings/organisation`、`PUT /api/settings/organisation` | `ai_features`（对象：已登记的 AI 用途到布尔值；附加字段，2026-11-24，GOV-1） | 每项 AI 用途一个开关（`domain/ai/register.py`）；未列出的用途为开启；`PUT` 将所发送的开关合并到已存值之上；响应结构其余不变 |
| `POST /api/monitoring/alerts/{alert_id}/analysis` | `provider_status` 新值 `switched_off`，告警 `ai_use_switched_off:alert_analysis`（附加取值，2026-11-24，GOV-1） | 组织关闭了告警分析：不调用模型，`answer` 与 `analysis_id` 为 `null`，告警自身文本保留 |
| `POST /api/analysis/query`、`POST /api/reports/portfolio` | 模型状态新值 `AI_USE_SWITCHED_OFF`（附加取值，2026-11-24，GOV-1） | 组织关闭了分析用途：不调用模型，保留确定性答案 |
| AI 请求的审计行（解释、简报与市场报告的 `ai.explain`；`ai.ask`、`ai.spreads`、`ai.report_plan`、`ai.alert_analysis`；分析查询与组合报告的 `llm.invoke`；`monitoring.enrichment.provider_call`） | `after_summary.ai`（`use`、`prompt_version`、`prompt_fingerprint`、`model_id`、`model_evaluated`、`calls`、`hashes[]` 含 `input_sha256`、`output_sha256`、`status`）（附加字段，2026-11-24，GOV-1） | 调用了模型时写入；只有哈希，从不含文本；`GET /api/audit/events` 在显示 `after_summary` 处显示 |
| `GET /api/access/market-data-licences` | 每个许可的 `usage_30d`（`principals`、`reads`、`exports`、`last_read_utc`）（附加字段，2026-11-24，GOV-1，P6） | 该许可数据源族近 30 天的使用记录：不同人员数、请求次数、文件导出次数与最近读取时间；无记录时为零 |
| 所有报告文件（提供 `format=csv`、`xlsx`、`pdf` 的路由） | 响应头 `X-Eurogas-Export-Decision`（`allowed` 或 `restricted`）、`X-Eurogas-Licensed-Sources`、`X-Eurogas-Export-Restrictions`；XLSX 与 PDF 的说明行 `Licensed data` 与 `Use`（附加字段，2026-11-24，GOV-1，P6） | 依据文件各行所读取的许可数据源族得出的导出决策；列与行不变 |
| `GET /api/portfolio/map-situation` | `assets[]`（`asset_id`、`kind` 为 `lng_terminal` 或 `storage`、`name`、`country`、`eic`、`location`、`capacity[]`、`flow[]`、`stock`）、`asset_rule`、`flow_days[]`（`gas_day`、`flows[]`）、`cargoes[].eta` 与 `cargoes[].position_basis`（附加字段，2026-11-24，MAP-1） | 地图上的 LNG 接收站与储气库：按方向列出 ENTSOG 最新公布的确定技术能力（能量单位，附燃气日、来源与接收时间）、该点最新已关闭燃气日的流量，以及 GIE 库存（`basis` 为 `site` 或 `country_aggregate`）；`flow_days` 为地图燃气日滑块提供已授权流量的已存燃气日；`eta` 说明货船 ETA 的依据（LNG-2 的同一对象；已确认合同货物为 `contract_window`）；`position_basis` 在数据源报告了位置时为 `reported`，否则为 `null`。各列表沿用现有规则：账簿项目按组合隔离，市场数据按调用方的数据范围。无路径、状态码或现有字段变化；公开接口清单不变 |

## 有意收窄的行为变更

以下变更比过去**拒绝得更多**，因此记录在此（对调用方可见，且不属于纯新增）。

| 接口 | 变更 | 原因 |
|---|---|---|
| 除凭据豁免路径外的所有 `/api` 路径 | **未出示任何凭据的调用方被拒绝。** 在 D1 之前，`development` 与 `internal` 剖面根本不安装认证，会把该调用方当作兼容主体（数据范围 `("*",)`、角色 `OPERATOR`）提供服务。现在：已配置部署令牌时返回 401 `public_api_token_missing`；未配置任何令牌时 fail-closed 返回 503 `public_api_token_not_configured`；身份依赖另外保留 401 `authentication_required` 作为兜底。豁免路径为 `/api/auth/*`、`/api/dev/auth/*`、`/api/health`（含 `live`/`ready`）、`/api/dev/health` 与 `/api/internal/health` | 业主决定 D1：默认标识调用方，而"信任网络"是部署自己声明并会被上报的选择。SDK、CLI、MCP 与 Web 客户端不受影响——它们本就出示部署令牌或会话 |
| `/api/internal/*`（12 条路径） | **补上此前不存在的权限声明。** `internal` 剖面未安装路由权限闸门，因此这些路径从未解析过权限；安装闸门后暴露出：已挂载却未登记的路径会返回 500 `permission_not_declared` | 登记表是执行依据而非文档。每条登记都与该路由自身在处理器中已执行的底线一致（`validate_internal_operator_headers`），因此此前能访问者不会被新增拒绝 |
| `POST /api/route-cost/resource-pool/optimize` | **请求必须携带显式且有限的 `annual_financing_rate_pct`。** 该字段不再有服务端默认值：省略该字段，或发送 `null`、布尔值、字符串（含空串）、`NaN` 或 ±无穷大，都会被请求校验以 `422` 拒绝，而不再被填入此前隐含的 `6.0`。显式提供的 `0` 会被接受，并被视为已记录的零（早收现金项为零）。其余字段、符号约定与算术规则均未改变 | 优化器把 `base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365` 计入单位边际，因此服务端填入的费率会用调用方从未声明的假设计算边际。Web 客户端本已拒绝未知费率并发送已解析的值，因此不受影响；直接 API/SDK 调用方现在必须声明其想要的费率。该边界变更记录于 2026-10-06 的业务验收对账说明；它不建立任何有日期的现金需求曲线、日算惯例、贴现因子或 NPV |
| `POST /api/route-cost/resource-pool/optimize` | **付款/销售滞后天数必须显式声明。** `PortfolioResource.upstream_payment_lag_days` 变为必填（移除此前的服务端默认 `20`）；`PortfolioSaleOption.screen_sale_cash_lag_days` 必须声明为非负整数天，或显式的 `null`（移除此前的默认 `1`）。提供的值必须是严格整数：布尔（Python 中按整数对待）、浮点、字符串与负数一律以 `422` 拒绝；显式的 `0` 是已记录的零。资源级可选的 `screen_sale_cash_lag_days` 覆盖字段适用同一规则。当某配对的生效滞后仍未知（既无资源覆盖，销售选项又显式声明 `null`）时，该配对会被拒绝并上报（`SALE_CASH_LAG_MISSING` / `SALE_CASH_LAG_UNKNOWN`），而不是按"交付日即回款"计入早收现金抵减。组合读取 `GET /api/route-cost/resource-pool/options` 不再回填被移除的一天默认值：合格合约未声明可用滞后时组合为 `null`。其余字段与算术规则均未改变 | 这些滞后天数与费率共同进入同一个早收现金项（`base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365`）；服务端填入的值会用调用方从未声明的滞后计算边际，而把销售滞后假设为 0 天会产生最大可能的抵减。该边界变更记录于 2026-10-06 的业务验收对账说明；它不引入有日期的现金计划、日算惯例、贴现因子或 NPV |
| 信用额度、交易员授权、套保批准、机会阈值的 PUT，及假设集批准 | **职责分离（2026-11-24，商业智能 V3 F1）**：仍需 REVIEWER；同时持有前台角色（ANALYST）的身份现以 `403 segregation_of_duties` 拒绝。授权对象为调用者任一名称（主体 id、名称或显示名，不区分大小写）时以 `403 own_mandate` 拒绝 | 人物审查 P-01/P-02：既是交易员又是审核人者可设定衡量自己交易的限额 |
| `PUT /api/portfolio/credit-lines/{id}` | **未提交的字段保留原值（F1）**：此前不带 `contract_ids` 会清空关联及其超限；解除关联须显式传 `[]`。每次参考数据写入的审计事件逐字段记录变更前后值（并填写 `before_summary`/`after_summary`），响应新增 `changed` | 人物审查 P-01 |
| `PUT /api/portfolio/credit-lines/{id}`，同路径新增 `GET` | **解除全部合约关联需确认（F1）**：授信已有关联合约时，空的 `contract_ids` 返回 `409 unlink_not_confirmed`，除非同时发送 `unlink_contracts: true`。新增的 `GET` 返回全部已存字段（REVIEW，仅限风控职能），表单按所读内容提交。未经确认的严重限额告警在条件消失后不再自动关闭：保持打开并附 `Condition cleared at …` 提示，确认后的下一次扫描才关闭 | 实操审查 QA-R-01 |
| `POST /api/market/ticks` | **许可标签须单独授权，不合理报价被拒绝（F1）**：`EEX`、`ICE_OCM`、`Trayport` 仅接受有效数据范围明确包含该源的密钥（`*` 密钥返回 `403 source_not_granted`）。价格超出该枢纽报价单位与产品的合理区间、远期产品为负、交易所时间晚于接收超过 120 秒、或中间价为同一合约上一报价的 3 倍以上（或三分之一以下）时，整批以 `422 ticks_invalid` 拒绝并说明原因，不存储任何内容 | 人物审查 P-03 |
| `POST /api/desk/gas-day/status` | **不再返回 500（F1）**：写权限类别此前没有最低角色；现需 `gas_day.record` 权限（新增的 SCHEDULER 调度员角色与 ANALYST 持有），返回 403、404、422 或 200 | 人物审查 P-04 |
| `POST /api/access/api-keys` | **收窄（F1）**：管理员只能为 SERVICE 服务主体或自己签发密钥；为其他 USER 签发返回 403 `personal_key_self_service` 并记为拒绝审计，因为密钥以其所属者身份行事。已有密钥不受影响。新增 `GET`/`POST /api/me/api-keys` 与 `POST /api/me/api-keys/{key_id}/revoke`，供本人在交互式登录下管理自己的密钥（默认 90 天到期，最长 365 天，范围不超过本人所持） | 实操审查 QA-R-02 |
| `GET /api/portfolio/daily-balance` | **与今日“我的燃气日”同一口径（2026-11-24，QA-T-07）**：各行由 `application/gas_day` 生成（调用者授权范围、同一组明细）。`supply` 改为实物明细净额（合同取已提名量，否则合同量，并按气源停运封顶；LNG 外输；储气与进口减去用户提气、注气与出口），不再是合同量乘以实测交付率；`delivery_ratio` 仍为实测比率但不再应用（`delivery_ratio_applied: false`）。`state` 使用燃气日容差带（已批准的 `balancing.flat_band_pct`，否则 2%），除非传入 `flat_band_mwh`。未传 `short_premium_per_mwh`/`long_discount_per_mwh` 时，成本取该枢纽账簿已批准的不平衡结算假设，而非返回 null；传入时标注为 `entered`（手工录入）。每日新增 `physical_in_mwh`、`physical_out_mwh`、`net`、`band`、`cash_out`（费率、假设集、版本、依据）、`lines`、`simulated`；顶层新增 `delivery_ratio_applied`、`definition`、`scope`、`as_of_utc` | 同一枢纽同一天有两个平衡数（今日 +20,153 MWh，交付页 +27,438 MWh；成本 1.20 对客户端默认 0.30 GBP/MWh） |
| `GET /api/desk/today`（`gas_day`、`checklist` 行） | **停运与船货计划改变燃气日明细（2026-11-24，QA-T-09、QA-L-01）**：气源当日有 REMIT 停运的供应明细，按合同日量减去停运比例乘以覆盖当日比例封顶，`adjustments` 列出该消息（`source`、`id`、`version`）；清单提名行新增 `outages`。持有确定船货的再气化时段改用船货计划的逐燃气日外输量（`basis` 为 `cargo_plan`，`source_ref` 为 `cargo:<id>`），错过时段的日子为 0；无船货的时段保留 `basis` `slot`，并明确为假设。当日成交的双边（ETRM）交易单列为一行，`ref` 以 `:bilateral` 结尾。待发送的 LNG 外输提名截止时间为提名截止点（无论是否已过），此前为下一个未过的截止点 | 平衡忽略了已登记的停运，并把外输摊到船货已错过的时段窗口 |
| `GET /api/portfolio/position-ladder` 及基于其头寸腿的所有读取（Today 的 `book` 与 `key_figures` 行、交易台简报、交易员授权使用、估值快照的头寸、账簿报告） | **公司船货计入头寸阶梯（2026-11-24，QA-L-03、QA-R-26）**：公司船货（已设账簿、非压载航次）以其计划在接收站枢纽的逐燃气日外输量计为实物腿，交易台记录在该船货上的对冲（`PUT /api/lng/cargoes/{id}/hedges`，未退役）按交割月计为金融腿；二者仅计量不估值（计入 `unpriced_rows`），并在警告中说明。不重复计算：已在阶梯上的 DES 船货合同所指向的船货不再加计外输；`reference` 为阶梯上已有交易的对冲不再加计。计划已在阶梯上的船货不再给出 FOB 警告（“不在欧洲枢纽”）。`legs.physical`/`legs.financial` 计入船货腿（每燃气日一条、每笔对冲一条）。燃气日（“我的燃气日”、`GET /api/portfolio/daily-balance`）、机会残差、信用敞口与对冲审批合同列表不变：燃气日已从时段明细取外输，记录的对冲既非已订交易也非合同 | 交易台主管的损益与对冲比例漏计超过 4 TWh 的船货敞口与对冲 |
| `GET /api/lng/cargoes/{id}/plan`、`POST .../plan/what-if`、看板 `next` | **展期须在两个月份中较早停止交易者收盘前完成（2026-11-24，QA-L-02）**：`roll` 建议的 `due_utc` 取 `from_month` 与 `to_month` 中先停止交易者的收盘时间；此前恒为 `from_month` 的收盘，导致反向展期（船货提前一个月到达）在目标月已停止交易后才到期。目标月已停止交易时仍不建议展期（改为 `short_notice`） | 从 Jan-27 展期到 Dec-26 的到期日为 12 月 31 日，而 Dec-26 于 11 月 27 日停止交易 |
| `GET /api/lng/cargoes/{id}/plan` 及船货看板 | **无泊位时无实物扣气、无交付（2026-11-24，QA-L-06）**：无泊位（`missed`、`no_slot`）时 `gas_in_kind_mwh` 与 `delivered_mwh` 为 0；此前仍扣除实物气，`delivered_mwh` 实为到港时能量。所有计划新增 `energy_at_eta_mwh`（装载量减去至 ETA 的蒸发）。错过时段的 `last_change` 显示交付减少，而非增加 | 能量不平（1,000,000 对 1,009,840 MWh） |
| `PUT /api/market/firm-marks` | **按行情点的合理区间拒绝（2026-11-24，QA-R-05）**：估值价按 `POST /api/market/ticks` 所用的按单位合理区间检查（`domain/market/feed.py`）：EUR/MWh 上限 500，月度及更长期间不低于 0（单日期间可至 -50）；GBp/th 上限 1,500（单日 -150）。其他 EUR 或 GBP 单位先换算；USD、CAD 单位沿用原 -500..5,000 边界。超出时返回 `422 value_implausible`，附该单元格 `index`，`message` 写明区间，整张表不存储。此前远期月份的 4,200 与 -50 EUR/MWh 均被存储 | 实测审查 QA-R-05：不合理的公司估值价以公司自有数字进入估值 |
| `GET /api/projections/market-context`（切片 `freshness.state`、`data_sources` 行），`GET /api/projections/portfolio-snapshot`（`data_sources` 行） | **统一新鲜度规则（2026-11-24，QA-R-07）**：行所属来源在连接器清单中有声明时，状态取新鲜度契约的判定（来源的 `FreshnessPolicy` 与日历，即 `GET /api/desk/today` `stale_figures` 所用规则）：正常时限内 `FRESH`，至过期阈值前 `LATE`，之后 `STALE`，无数据 `MISSING`。此前凡超过声明期望即为 `STALE`（10 分钟前的 EEX 行情点；现为 `LATE`，3 天后过期）。`SOURCE_STALE` 警告仅随 `STALE`。行中无已声明来源的切片沿用仅按期望的判定。`expected_within_minutes` 与块的键不变 | “数据源”弹窗对每个数据源都显示“过期”，而今日页显示所有数字均为最新 |
| `GET /api/desk/today`（信用额度的 `rows[0].tightest_limit`） | **使用该额度自身的估值日期（2026-11-24，QA-R-07）**：`as_of` 与 `state` 取该行的 `marks_as_of` 与 `state`（其枢纽中最旧的收盘价）；此前取任一枢纽的最新收盘价，以旧枢纽估值的额度可能显示为最新 | 限额页、今日页与 `marks_stale` 告警使用同一判定 |
| `GET /api/stream/opportunities` | **改为推送机会引擎，而非旧的日内扫描（2026-11-24，M7）**：此前推送带数值的 `IntradayOpportunityRecord` 行；现推送 `opportunity` 事件，`status` 为 `open` 或 `withdrawn`（机会离开列出状态或有效期结束时推送撤回），以及评估完成时的 `evaluated` 事件；事件不含数值。每个事件按机会自身的读取规则过滤（所有来源族均已授权；非 `market` 通道时所有账簿可见）。燃气日截止通知的类别由 `alert` 改为 `nomination`，数据源告警由 `alert` 改为 `source`；通知正文末尾注明负责人与升级对象 | 各界面统一为一个机会模型：页面、告警与推送一致，旧扫描的重复告警消失（07 R11）。旧行仍可经 `GET /api/market/opportunities` 读取 |
| `GET /api/desk/today`（`price.<hub>`、`market.hubs[].front_month`、`book` 的 `mark`）、`POST /api/analysis/brief`（价格段） | **每个枢纽与月份只有一个价格（2026-11-24，P-08、QA-T-02、QA-L-22）**：月前数值取解析器的价格：按数据源新鲜度策略仍在期的实时行情点优先于昨日收盘价；`as_of`、`state`、`simulated` 与 `source` 均取该价格。日变动按同一交割月的前一收盘价计算（跨月滚动时无），Today 账簿日损益随所示变动计算。简报行日期为该价格的观测日。日前数值不变 | 同一时刻同一月份最多出现三个价格 |
| `GET /api/portfolio/position-ladder` 及所有基于 `ladder_inputs` 的读取 | **估值价取自解析器（2026-11-24，P-08）**：月份估值价为最新的在期行情点或结算价，否则公司当前估值价（`mark_method` 新值 `firm_mark`），否则如前按曲线或收盘价补齐；之后重新计算 `flat_months` | 看板显示更新的报价时，阶梯仍按演示曲线估值 |
| 估值快照价格（机会扫描、LNG 船货经济性） | **过期报价不再优先于在期结算价（2026-11-24，P-08）**：价格输入取解析器的结果；报价仅在在期时优先。价格读取快照时刻前 400 天内的数据 | 此前任意时长的报价都先于结算价被采用 |
| `GET /api/lng/cargoes/{cargo_id}/plan`（`inputs[]` 中的 `ETA` 行） | **ETA 来源说明其依据（2026-11-24，LNG-2）**：`source` 原为固定文本 “cargo record eta_utc”，现为 “ETA from <源系统> (<依据>, <置信度>)”，导入未说明时为 “basis not stated” 与 “confidence not stated”。曾匹配旧文本的客户端应改读 `cargo.eta` | 经验 P3：估计值要说明自己是估计；交易员按报告来源衡量延误 |
| `GET /api/opportunities`、`GET /api/opportunities/{opportunity_id}`（`sell_down` 类型；`locational` 日前候选） | **按账簿自有假设集与燃气日余量评估（2026-11-24，P-11）**：全公司评估先读账簿自有的已批准假设集，再回退到全公司假设集（卖出余量的不平衡折价与溢价；区位机会的负荷率、燃料与损耗、短期乘数）；币种与枢纽不同的账簿不平衡费率不予使用。余量为该账簿明日燃气日自身明细的日平衡（与 `GET /api/portfolio/daily-balance`、“我的燃气日”同一口径），在账簿平衡带内视为平衡，不再按实测交付比例缩放（快照中的余量输入注明 `definition: gas_day`、`delivery_ratio_applied: false`）。此前显示“无法评估”的卖出余量记录，在账簿持有费率时现可估值，数值随之变化，数量腿与首条证伪条件改写（评估器版本 2）。仅供决策参考 | 人物审查 P-11；与 QA-T-07 同一平衡口径 |
| 受治理的写入：`PUT /api/portfolio/credit-lines/{counterparty_id}`、`PUT /api/portfolio/trader-mandates/{mandate_id}`、`PUT /api/portfolio/hedge-approvals/{contract_id}`、`PUT /api/portfolio/lng-terminal-terms/{terminal_id}`、`PUT /api/opportunities/settings`、`POST /api/assumption-sets`、`POST /api/assumption-sets/{set_id}/versions`、`POST /api/assumption-sets/{set_id}/versions/{version}/approve`、`PUT /api/market/firm-marks`、`/api/access/*` 与 `/api/me/api-keys` 下的用户、组、许可与密钥写入、`PUT /api/credentials/{provider_id}`、`DELETE /api/credentials/{provider_id}`、`PUT /api/lng/cargoes/{cargo_id}/hedges` 以及内部身份写入 | **审计是写入的一部分（2026-11-24，GOV-1，P5）。** 变更的审计行无法写入时，写入返回 `503`，`detail.code` 与 `error` 为 `audit_unavailable`（DEPENDENCY 类，可重试），`detail.action` 为审计动作，变更不保存任何部分。此前变更可能在没有审计行的情况下成功。读取不受影响。用户与许可更新的审计行现在也记录 `before_summary` 与 `after_summary` | 受治理的变更必须可追溯（竞品研究第 5 条） |
| `PUT /api/settings/organisation` | **受治理的写入，并校验 `ai_features`（2026-11-24，GOV-1）**：审计行与变更在同一事务中写入；审计行无法写入时变更不保存，返回 503 `audit_unavailable`（此前审计失败被吞掉）；审计行现带 `before_summary` 与 `after_summary`。`ai_features` 中非已登记 AI 用途的键或非布尔值返回 422 `setting_invalid` | AI 开关属于管控，变更不得缺少审计行（P5） |
| 所有 AI 接口（`POST /api/analysis/explain`、`/brief`、`/ask`、`/query`，`POST /api/reports/market`、`/plan`、`/portfolio`，`POST /api/research/spreads/interpret`，`POST /api/monitoring/alerts/{alert_id}/analysis`，告警增强） | **组织关闭的用途不调用模型（2026-11-24，GOV-1）**：读者得到依据为 `rule` 的规则文本，与未配置模型时相同；设置库已配置但无法读取时，AI 视为关闭 | 按用途的停用开关（NIST AI RMF Manage 2.4） |
| 代表模型发起的能力调用：`POST /api/agent/research` 运行与 MCP 能力工具 | **超出模型工具白名单即拒绝（2026-11-24，GOV-1）**：AI 用途未列出、调用者任一角色均不允许模型调用、或从不由模型调用（`dataset.export`、`review.record_analytical_decision`、`shadow.start`、`shadow.pause`、`shadow.resume`、`strategy.freeze_version`）的能力，以 `PERMISSION_DENIED` 拦截，详情 `ai_tool_not_allowed: ...`，并记审计（`ai.tool.refused`）；人员直接调用同一能力不受影响 | 有界的代理权限（OWASP LLM Top 10，过度代理） |
| `POST /api/capabilities/{capability_id}/invoke` 与 MCP 能力工具（`CapabilityResult`） | **拒绝可追溯、结果经校验、仅由本人确认（2026-11-25，CODEX-1）**：`BLOCKED` 结果的 `execution_metadata` 现在同样写明能力、版本、主体、代理运行与参数哈希，成功结果另带 `output_hash`。成功结果的数据不符合能力声明的 `output_schema` 时，以 `BLOCKED` `INTERNAL_ERROR` 返回。超过声明 `timeout_policy` 的调用带 `TIMEOUT_OVERRUN` 警告。除非处理器核验过证据，`quality_state` 为 `NOT_ASSESSED`（此前默认 `VERIFIED`）。`human_confirmation` 仅在已登录本人发出时有效：部署令牌、服务账户或代表 AI 用途的模型发出时，以 `HUMAN_CONFIRMATION_REQUIRED` 返回并说明原因；确认与写入类调用均记审计（`governance.agent_capability`）。无身份的请求返回 401（与全局依赖一致），路由不再回退为拥有全部数据范围的分析员。未删除或重命名任何字段 | 人工监督须来自人；如实记录来源（NIST AI 600-1）；失败即关闭 |
| 所有报告文件（`format=csv`、`xlsx`、`pdf`） | **无已登记导出条款的许可数据文件被拒绝（2026-11-24，GOV-1，P6）**：若各行读取自既不在治理登记表中、也无许可登记表中当前许可覆盖的供应商许可数据源族，文件返回 403 `export_denied` 并附 `licensed_families`；同一数据的 JSON 读取不变 | 失败即关闭的导出策略（`ExportDecision`）：文件会离开平台 |

## 被拒绝的请求字段

已声明但管道从不读取的字段，是平台无法兑现的声明：填入它的调用方会收到未加修改的结果，却以为自己的选择已被应用。此类字段**以稳定错误码拒绝，而不是被忽略**，登记于此，并保持声明状态（删除它会把显式拒绝变成对仍在发送该字段的调用方的静默丢弃）。拒绝发生在运行被加载、被跟踪或被计费之前，且空值绝不构成违规。下表中每个拒绝码都已登记进产品错误分类法，因此客户端可直接分类（族、严重度、可恢复性），而不必解读原始状态码。

| 路径 | 字段 | 契约 |
|---|---|---|
| `POST /api/analysis/query` | `selected_terms`、`selected_assets`、`selected_contracts`、`include_sections` | `422 analysis_selection_not_supported`，并在 `detail.fields` 中列出每一个非空字段。确定性构建器只读取快照、任务与问题，因此术语、资产、合约或章节选择描述的是不会发生的工作。证据引用应放在 `question` 中——那正是平台记录的提示词、也是 provider 收到的文本 |
| `POST /api/reports/portfolio` | `portfolio_id`、`selected_resources`、`selected_contracts`、`selected_strategies` | 同一错误码与同一 `detail.fields` 契约：报告基于具权限的整份快照计算，因此组合/资源/合约/策略选择会成为调用方误以为已生效的范围 |
| `POST /api/agent/research` | `strategy_ir` | `422 strategy_ir_not_accepted`：编排器从不读取它，调用方可能以为自己提供的规格已被运行，而管道实际校验的是自己生成的候选。策略注册表才是拥有规格的路径 |
| `POST /api/agent/research` | `profile`（校验，非拒绝） | 不是平台已声明的 profile 时返回 `422 agent_profile_unknown`；已声明但未走完其全部阶段的 profile 以 `PROFILE_STAGES_NOT_REACHED:<stage,…>` 报告而不拒绝，因为提前停止往往是诚实的结果 |

## 弃用表

| 表面 | 弃用起始 | 计划移除 | 状态 |
|---|---|---|---|
| `/api/workflows/*`（10 个遗留壳） | 0.5.x（S4.3） | Web/SDK/CLI 全部迁移到领域化 `/api` 端点后 | 0.5.x 在 Web/SDK/CLI 迁移完成后已移除；旧路径现在返回 404 |
| `POST /api/review/decisions` 的 `actor`（请求字段） | 0.5.x（W0-03 C13） | 待无调用方再发送该字段 | 仍可接受但绝不使用：平台将已认证身份记录为决策及其审计事件的操作者。若该值与身份不一致，会以 `ACTOR_CLAIM_IGNORED:<claim>` 信封告警返回，让调用方得知其声明未被记录。同一次变更中该字段已改为可选，因此不发送才是受支持的形式 |

## 非目标

- URL 版本化（`/v1`、`/v2`）：已否决；无版本契约以只增方式演化。
- 生成式客户端桩代码：SDK DTO 保持手写，由 parity 测试守护。


## Strategy ownership and sharing — 2026-10-22

The public path registry now contains 187 paths (previously 182). Added:

- `/api/me/groups` (GET): the authenticated user's active sharing groups.
- `/api/access/groups` (GET/POST): ADMIN group catalogue and creation.
- `/api/access/groups/{group_id}` (PATCH): ADMIN group status/name changes.
- `/api/access/groups/{group_id}/members/{principal_id}` (PUT/DELETE): ADMIN membership changes.
- `/api/strategies/{strategy_id}/sharing` (PATCH): owner-selected PRIVATE, PUBLIC or GROUPS audience.

Strategy responses add `owner_principal_id`, `visibility`, `shared_group_ids` and
`can_manage`. New strategies are PRIVATE and bind ownership to the authenticated
active directory principal, never a request's attribution text. PUBLIC grants
read access within this deployment, still subject to roles and source licences;
it grants no edit or cross-region transfer permission. GROUPS requires explicit
active groups the owner belongs to. Shared readers cannot mutate strategy state.

This deliberately narrows existing access: hidden strategies and their child
resources return 404; lists filter before limiting. Jobs are restricted to their
server-recorded owner; a foreign `principal` query returns an empty list. Review
and portfolio projections withhold inaccessible strategy-linked records. Existing
ownerless strategies remain PRIVATE and quarantined pending verified ownership
assignment; migration 0040 does not infer owners from free-text attribution and
refuses downgrade to code that would expose these records.

Empty identity-key scopes now mean public-baseline access, not inheritance of
commercial grants. Explicit key scopes are intersected with current principal
grants. Operators must replace old implicit-scope keys with approved explicit
scopes; see [API keys](../operations/API_KEYS.md).

任务所有权补充：迁移 0041 增加独立的 `owner_principal_id` 外键，由服务端具名身份绑定。
`principal` 仅保留为归属展示和进一步过滤条件；旧的仅含名称的任务暂不授权读取或取消。
名称与身份 ID 相同也不构成访问授权，不自动推断或回填所有者。


功能改进分支新增持久化任务、版本对账、模型冻结与影子评价接口。当前分支共 240 条路径、260 项操作。见[功能引擎改进](../engineering/FUNCTIONAL_ENGINE_IMPROVEMENTS-CN.md)。
