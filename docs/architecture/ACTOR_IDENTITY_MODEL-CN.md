# Actor 身份模型

英文版：[ACTOR_IDENTITY_MODEL.md](ACTOR_IDENTITY_MODEL.md)

## 范围

R32 已增加本地 PostgreSQL 身份（`identity_principals` /
`identity_api_keys`），包含 USER/SERVICE 主体、哈希 bearer key 和
VIEWER/ANALYST/OPERATOR/ADMIN 角色。本文档定义信任链（复核决策、审计事件、
internal operator 写入）使用的 actor 身份模型，并明确说明仍推迟的部分。

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
| R32 identity-key 客户端 | `X-Eurogas-Identity` bearer 解析为 PostgreSQL 主体；其角色/名称为已认证 actor |
| 审计事件 | principal 原样记录；由上述入口点先行校验 |
| 公共摄入脚本 | 在具备运行身份前固定为 `operator` |

## R32 已交付范围

- PostgreSQL 本地 USER/SERVICE 账户。
- 哈希 bearer API key（`X-Eurogas-Identity`），明文仅返回一次。
- OIDC access-token 校验（`X-Eurogas-Oidc-Access-Token`，R32A）：
  RS256/JWKS/issuer/audience/expiry 校验与声明到角色的映射。
- 角色授权：PUBLIC/READ VIEWER+，GOVERNED ANALYST+，OPERATOR OPERATOR+。
- 按身份执行商业数据 scope，未知来源 fail-closed。

## 仍推迟

- OIDC 交互式登录（redirect/PKCE/refresh/session）与 SAML。
- 浏览器/密码会话。
- 取消私网/VPN-only 服务器部署姿态；须等待安全验收。

## 演进

identity-key 调用方已由持久化的 `principal_id`/`name` 表示；仅使用旧头部的
调用方继续保留 legacy principal 字符串。审计/复核行通过同一 `actor` 列契约可读。
未来的 `actor_kind` 判别字段与 SSO 映射属于 R32A 范围。
