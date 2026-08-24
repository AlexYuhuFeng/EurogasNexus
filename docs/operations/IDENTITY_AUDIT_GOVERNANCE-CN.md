# 身份、授权与审计治理运营手册

英文版：[IDENTITY_AUDIT_GOVERNANCE.md](IDENTITY_AUDIT_GOVERNANCE.md)

## 支持的身份模型

R32 支持本地 PostgreSQL 身份；本增量不包含公司 SSO/OIDC，也未引入 OIDC
依赖。

| 项目 | 行为 |
|---|---|
| 主体 | `identity_principals` 中的 USER 或 SERVICE 行 |
| 角色 | VIEWER、ANALYST、OPERATOR、ADMIN |
| 凭据 | `identity_api_keys` 中的哈希 bearer API key |
| 客户端头 | `X-Eurogas-Identity: nexus_<key_id>_<secret>` |
| 旧部署兼容 | 只发送 `X-Eurogas-Api-Key` 时仍映射为 OPERATOR service principal |
| 私网部署姿态 | 安全验收前保持不变 |

## Internal 管理

以下端点都要求 `X-Eurogas-Internal-Token` 和合法的
`X-Eurogas-Principal` 头。

```text
GET    /api/internal/identities
POST   /api/internal/identities
POST   /api/internal/identities/{principal_id}/keys
POST   /api/internal/identities/{principal_id}/keys/{key_id}/rotate
POST   /api/internal/identities/{principal_id}/keys/{key_id}/revoke
POST   /api/internal/identities/{principal_id}/disable
GET    /api/internal/audit/events
POST   /api/internal/audit/prune
```

- `POST .../keys` 只返回一次明文 bearer，离开前请保存。
- `GET /api/internal/identities` 永不返回哈希或明文 key。
- rotate 会先吊销旧 key，再签发新 key。
- disable 后该主体的所有 key 立即失效。

## 角色授权

| 权限类别 | 最低角色 |
|---|---|
| PUBLIC / READ | VIEWER |
| GOVERNED | ANALYST |
| OPERATOR | OPERATOR |

ADMIN 满足所有角色。旧部署令牌调用方保持 OPERATOR 兼容。注册表由
`tests/security/test_permissions_registry.py` 测试，release 配置下由
`route_permission.py` 强制执行。

## 商业数据 scope

`identity_principals.data_scopes` 保存来源 family 授权。公共基线来源
（`operator-input`、`ENTSOG`、`GIE`、`ECB`、`Weather`）对所有 active 身份
可见；商业 family 需要显式授权：

```json
["EEX", "ICE_OCM", "Trayport"]
```

`*` 授予全部 family，适合 operator/admin 服务身份。未知商业来源一律
fail-closed。市场观测与报价响应会按已认证身份的授权 family 做行级过滤。

## 审计保留与导出

- 默认保留 365 天；允许范围 30–3650 天。
- 清理默认 dry-run：

```bash
python scripts/ops/prune_audit_events.py --retention-days 365
python scripts/ops/prune_audit_events.py --retention-days 365 --commit
```

- `POST /api/internal/audit/prune` 接受 `retention_days` 和 `dry_run`。
- `GET /api/internal/audit/events` 仅导出受限范围、不含秘密的审计行，并记录
  `audit.export` 事件。
- 身份生命周期操作始终追加审计事件。

## R32A 剩余范围

- 公司 SSO/OIDC/SAML、浏览器会话和密码生命周期。
- 安全验收及取消私网/VPN-only 部署姿态。
