# Actor 身份模型

英文版：[ACTOR_IDENTITY_MODEL.md](ACTOR_IDENTITY_MODEL.md)

## 范围

Eurogas Nexus 目前是单信任域的决策支持预览产品。本文档定义信任链（复核决策、
审计事件、internal operator 写入）使用的最小 actor 身份模型，并明确声明
未实现的部分。

## Actor Principal

actor 由 **principal 字符串**标识：一个稳定的 operator 标识符，记录在每条
复核决策、审计事件、凭据变更、摄入运行和认证写入上，使信任链能逐行回答
「谁做的」。

规则（唯一校验器：`src/eurogas_nexus/domain/identity/principal.py`）：

- 必填并去除首尾空白，1–64 字符；
- 以字母或数字开头；
- 只含字母、数字和 `. _ @ -`；
- 拒绝空值、控制字符和内嵌空白。

示例：`trader-a`、`ops-user`、`analyst.alice`、`ops@nexus`。

执行点：

| 表面 | 执行方式 |
|---|---|
| `POST /api/review/decisions` | 持久化前用 `normalize_principal` 校验 actor |
| Internal operator 写入（`/api/internal/*`） | `X-Eurogas-Principal` 头以同一规则校验 |
| 审计事件 | principal 原样记录；由上述入口点先行校验 |
| 公共摄入脚本 | 在具备运行身份前固定为 `operator` |

## 明确不在范围内（R32）

- 用户账户、密码、会话、多用户授权。
- 公司 SSO / OIDC / SAML。
- 超出「internal token + principal 头」的按用户数据隔离或 RBAC。
- 取消私网/VPN-only 的服务器部署姿态。

这些都取决于 R32 认证增量（`NEXT_DEVELOPMENT_QUEUE.md`）。在此之前身份模型
保持最小，但每条敏感行都已带校验过的 actor，将来接入真实认证无需重写信任链。

## 演进

R32 落地后，principal 字符串变为对已认证身份的引用（如 `user:<id>` 或
`service:<id>`），审计/复核 schema 增加 `actor_kind` 判别字段。既有行保留
字符串 principal；两者通过同一 `actor` 列契约可读。
