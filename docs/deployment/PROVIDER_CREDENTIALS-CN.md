# 配置供应商凭据

[English](PROVIDER_CREDENTIALS.md) · [管理与数据运营](../guides/ADMIN_AND_OPERATIONS-CN.md)

需要 Key 的供应商采用统一凭据规则，采集、模型调用和凭据 API 使用同一解析逻辑。

## 查看当前生效的凭据来源

解析顺序如下：

1. 如果管理员在凭据管理中停用该供应商，供应商保持停用。
2. 使用非空环境变量。下表首先列出的名称是标准名称，随后列出兼容别名。
3. 支持密钥文件的供应商读取对应 `*_FILE`。已配置文件无法读取或为空时会报错。
4. 使用加密凭据库中的记录。

`GET /api/credentials/providers` 返回各供应商的 `effective_source`、可用变量和连接器实现状态。来源值包括 `env`、`file`、`credential_store`、`disabled` 和 `missing`，响应不含密钥。

修改环境变量中的 Key 后，重启或重新部署服务，使新配置生效。

## 选择正确的配置方式

| 供应商 | 配置项 | 凭据型连接器状态 |
| --- | --- | --- |
| GIE AGSI+/ALSI | `GIE_API_KEY`、`GIE_API_KEY_FILE` | 已实现；还需来源认证 |
| 美国 EIA | `EIA_API_KEY` | 已实现，支持 Henry Hub |
| ENTSO-E | `ENTSOE_SECURITY_TOKEN` | 已实现，支持电力数据 |
| DeepSeek | `EUROGAS_NEXUS_LLM_API_KEY`，兼容 `DEEPSEEK_API_KEY` | 已实现 |
| 其他模型端点 | `EUROGAS_NEXUS_LLM_API_KEY` | 支持 OpenAI 兼容接口 |
| EEX、ICE OCM、ICIS、Argus、Trayport、Kpler、Platts、Weather | 凭据库 | 连接器尚未实现，可保存配置供后续接入使用 |

ECB、ENTSOG、英国央行、ECB €STR 和纽约联储的上述公开接口无需 Key。

## 准备可复用的测试文件

1. 将 `.env.testing.example` 复制为 `.env.testing`。
2. 填写你实际使用的供应商凭据。该私有文件已由 Git 忽略。
3. 启动本地测试服务前显式加载文件。使用兼容的 shell 时可执行：

```bash
set -a; . ./.env.testing; set +a
```

该文件只保存供应商凭据。数据库地址、会话和加密密钥及登录密码保留在对应部署环境中。

## 完成来源激活

配置凭据后，继续核对来源启用状态、采集计划、所需认证和数据许可。外部模型调用还受 `EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED` 控制。

EEX 公开 TTF NGP 参考观测采用单独的有界下载流程，上表连接器状态指通过供应商凭据接入授权行情的方式。

最后检查首次运行结果和数据时间，并在业务页面核对一条记录。
