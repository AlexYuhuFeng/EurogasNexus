# 系统管理与数据运营指南

[English](ADMIN_AND_OPERATIONS.md) · [客户使用指南](README-CN.md)

完成本节的配置后，用户能够访问获分配的功能，所需来源能够更新，运营异常有明确的处理责任人。

## 准备安装环境

按照交付版本的[部署说明](../deployment/DEPLOYMENT_ROLES-CN.md)安装服务器和客户端。登记服务地址、版本与发布通道、数据库结构版本、登录方式、运营负责人及备份恢复流程。

向交易台交付前，完成[客户上线与交接](CLIENT_ONBOARDING-CN.md)。

## 配置用户与权限

1. 按[企业单点登录说明](../operations/ENTERPRISE_SSO.md)设置公司的登录方式。
2. 打开“管理”>“访问与身份”，分配已获批准的角色和数据范围。
3. 设置岗位资料和办公室，用于组织用户工作区。
4. 使用该账户完成一项具有代表性的获准任务。
5. 使用独立测试身份检查受限任务，并保存结果。

商业数据权限由业务负责人批准，管理员按批准结果落实。系统管理权限与商业数据访问权限分别配置。

## 接通一个数据源

1. 打开“管理”>“数据源中心”，检查连接器是否已实现。
2. 如需凭据，按该来源支持的方式配置。
3. 完成适用的访问或来源认证检查。
4. 启用来源，确认采集计划或导入流程。
5. 执行或观察首次采集，检查结果、记录数量和来源时间。
6. 打开对应的市场或实物数据视图，将一条记录与原始来源核对。

**完成检查：**凭据已配置、来源已启用、采集成功及记录符合时效要求，是四项不同的检查。

| 数据 | 所需配置 | 详细资料 |
| --- | --- | --- |
| ECB 参考汇率 | 公开接口，无需 API Key | [公开数据采集](../../scripts/ops/ingest_public_sources.py) |
| ENTSOG 网络、流量及容量 | 无需 API Key；需指定查询范围并完成来源认证 | [数据调度程序](../../scripts/ops/run_dataops_scheduler.py) |
| GIE 储气及 LNG | GIE Key 及来源认证 | [供应商凭据](../deployment/PROVIDER_CREDENTIALS-CN.md) |
| 英国央行、ECB €STR、纽约联储利率 | 公开接口 | [利率来源](../operations/INTEREST_RATES.md) |
| ENTSO-E 电力、EIA Henry Hub | 对应供应商的令牌或 Key | [电力数据](../operations/POWER_DATA.md)、[市场数据来源](../operations/MARKET_DATA_SOURCING.md) |
| 授权报价、结算价及汇率定盘价 | 获授权的数据连接或导入文件 | [行情接入](../operations/LIVE_PRICE_SOURCES.md)、[汇率定盘价](../operations/FX_FIXINGS.md) |
| ECMWF 预测、National Gas 需求 | 对应数据集的采集配置 | [ECMWF](../data/ECMWF_FORECAST_OPERATIONS.md)、[National Gas](../data/NATIONAL_GAS_REST_OPERATIONS.md) |

凭据目录标明连接器的实现状态。为未来连接器保存 Key，不等于数据连接已可用。模拟来源通过数据源中心的测试来源开关显示。

## 复用测试凭据

将仓库中的 `.env.testing.example` 复制为私有的 `.env.testing`，填写实际使用的服务。启动测试环境时显式加载该文件；在 Render 中，可将条目导入服务的 Environment 页面。数据库地址、会话密钥及登录密码保留在各环境自己的部署配置中。

当前统一凭据规则覆盖 GIE、EIA、ENTSO-E 和已配置的 LLM 服务。管理员停用的供应商保持停用。其余情况下，按支持的环境变量、密钥文件、加密凭据库顺序解析。

`GET /api/credentials/providers` 的 `effective_source` 表明当前使用哪种来源。变量名及别名见[凭据配置说明](../deployment/PROVIDER_CREDENTIALS-CN.md)。

## 监控与恢复

在数据源中心检查来源故障与数据时效，在“管理”>“运行状态”查看运行准备情况及问题报告。服务连通性与实际数据覆盖分别检查。参考汇率可能每日发布，报价连接则有自己的更新频率。

来源失败时，先查看最近运行、查询范围、供应商响应和下次重试，再决定是否手动重跑。平台故障按[事件响应](../operations/INCIDENT_RESPONSE.md)、[备份恢复](../operations/BACKUP_RESTORE.md)和[版本回退](../operations/RELEASE_ROLLBACK.md)处理。报障资料见[技术支持](SUPPORT_AND_UPDATES-CN.md)。

## Render 测试环境

[Render 测试部署](../deployment/RENDER_MOBILE_PREVIEW.md)在启动时运行调度器并安排首次公开数据采集；来源认证和凭据要求仍按各来源执行。调度器随服务运行，空闲休眠后应重新检查来源时间。

公司的正式运行和恢复要求，通过受管服务器部署及客户交接记录落实。
