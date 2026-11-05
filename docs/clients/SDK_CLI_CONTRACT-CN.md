# SDK 与命令行集成约定

[English](SDK_CLI_CONTRACT.md)

## 使用配套接口

Python SDK 随仓库发行包提供，源码位于 `packages/python-sdk/src/eurogas_nexus_sdk`。它提供健康检查、市场与实物观测、组合、研究、策略、复核及运行管理等类型化 API 客户端。

命令行入口为 `eurogas-nexus`，实现位于 `src/eurogas_nexus/cli/main.py`。使用与安装环境配套的 SDK 和命令帮助。

[SDK 说明](../../packages/python-sdk/README.md)提供原始流量数据示例，[函数目录](../api/DATA_SCIENCE_FUNCTIONS.md)介绍分析接口。

## 配置地址和身份

SDK 方法接收服务根地址，例如 `https://nexus.example.com`，健康检查方法会追加 `/api/health`。桌面部署设置则使用以 `/api` 结尾的地址，两者按各自接口要求填写。

配置该环境发放的凭据。共享 HTTP 模块读取：

- `EUROGAS_NEXUS_PUBLIC_API_TOKEN`，兼容旧名 `EUROGAS_NEXUS_API_TOKEN`；
- `EUROGAS_NEXUS_IDENTITY_BEARER`；
- 适用的操作员上下文使用 `EUROGAS_NEXUS_PRINCIPAL`。

身份、操作权限和来源访问由后端校验。

首次读取可使用：

```python
from eurogas_nexus_sdk import fetch_health

health = fetch_health("https://nexus.example.com")
print(health.status, health.version, health.profile)
```

安装命令行工具后，可执行：

```bash
eurogas-nexus --base-url https://nexus.example.com health
eurogas-nexus --help
```

示例地址应替换为 IT 提供的服务根地址。健康检查反映服务状态，数据采集及商业数据覆盖另行检查。

## 保留可复现的集成记录

- 运行数据通过后端 API 读取，不直接访问数据库或导入内部领域模块。
- 使用已记录的方法及明确参数，保留返回的元数据、编号、来源、警告和缺失输入。
- 凭据保存在获批运行配置中，与研究笔记、共享示例和日志分开。
- 自动化前，区分会保存状态的操作与读取或计算请求，确认所需权限。
- 记录服务版本、SDK 版本、请求及返回依据。
- SDK 和命令行测试分别位于 `tests/sdk`、`tests/cli`；边界测试检查 API 调用关系。

[SDK](SDK_CLIENT_DESIGN_SPEC.md)和[命令行](CLI_CLIENT_DESIGN_SPEC.md)设计文档用于专项参考。早期启动阶段记录说明当时范围，当前方法以配套发行版本为准。
