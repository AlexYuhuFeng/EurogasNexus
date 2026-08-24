# OIDC Access Token 运营手册

英文版：[OIDC_ACCESS_TOKEN.md](OIDC_ACCESS_TOKEN.md)

## 目的

R32A 增加经评审的 OIDC **access-token 校验**路径，未引入 JWT/OIDC SDK 依赖。
它是机器到机器的 bearer 校验流程，不是浏览器登录流程；没有 redirect、PKCE、
refresh token 或 session cookie。

## 配置

```text
EUROGAS_NEXUS_OIDC_ISSUER=https://idp.example.com/realms/nexus
EUROGAS_NEXUS_OIDC_CLIENT_ID=eurogas-nexus
EUROGAS_NEXUS_OIDC_AUDIENCE=eurogas-api
EUROGAS_NEXUS_OIDC_ROLE_CLAIM=roles
EUROGAS_NEXUS_OIDC_SCOPE_CLAIM=entitlements
EUROGAS_NEXUS_OIDC_ALLOW_HTTP=false
```

- `ISSUER` 必须是 HTTPS；`ALLOW_HTTP=true` 仅用于经评审的开发/测试 issuer。
- `CLIENT_ID` 必填；`AUDIENCE` 缺省等于 client id。
- discovery（`/.well-known/openid-configuration`）与 JWKS 在首次请求时惰性
  获取并缓存 300 秒；导入 API 不发起任何网络调用。

## 客户端请求

release 客户端仍需发送部署令牌：

```http
X-Eurogas-Api-Key: <public-api-token>
X-Eurogas-Oidc-Access-Token: <RS256 access token>
```

当同时发送 `X-Eurogas-Identity`（本地 DB key）时，本地 key 优先。

## 校验规则

- 仅接受 RS256，且必须带 `kid`。
- 按 `kid` 匹配 JWKS key，并使用 SHA-256/PKCS#1 v1.5 验签。
- 强制校验 `iss`、`aud`、`exp`、`nbf` 和非空 `sub`，容忍 60 秒时钟偏差。
- 未识别角色声明映射为 VIEWER（最小权限）。识别别名：
  admin/administrator → ADMIN；operator/ops/operations → OPERATOR；
  analyst/trader/research → ANALYST；viewer/read → VIEWER。
- `entitlements`/`data_scopes` 声明值成为商业数据 scope；未知 family 仍在
  entitlement 层 fail-closed。

## 运营

- 无效 token 以 best-effort 写入 `identity.authentication.denied` 审计，不保存
  token 本身。
- 安全验收通过前，私网/VPN-only 服务器部署姿态保持不变。

## 非目标

- 无 login redirect、PKCE、refresh token、session 或 SAML。
- 导入期代码与自动化测试不调用任何身份提供商。
