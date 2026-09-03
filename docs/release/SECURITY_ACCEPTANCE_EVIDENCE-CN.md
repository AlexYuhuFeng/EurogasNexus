# 安全验收证据

英文版：[SECURITY_ACCEPTANCE_EVIDENCE.md](SECURITY_ACCEPTANCE_EVIDENCE.md)

由 `scripts/security/run_security_acceptance.py` 生成。

## 自动化状态

当前工作树为 `PASS`（运行日期由脚本记录）。

检查项：

- API 导入不加载数据库/网络。
- 公开 API 表面受控（86 条路径），`/api/workflows/*` 已移除。
- 每条公开路径都有权限声明。
- 公共令牌与 internal 令牌在未配置时 fail-closed。
- 身份 API key 仅存哈希，角色优先级正确。
- 旧公共令牌兼容主体仍为 OPERATOR。
- OIDC access-token 校验在未配置时 fail-closed。
- 保留私网/VPN-only 姿态。

## 外部验收状态

`BLOCKED`

代码工作树无法完成外部验收。移除私网/VPN-only 姿态前必须完成：

1. 真实部署渗透测试与依赖 CVE 复跑。
2. 客户身份团队评审 OIDC issuer/JWKS TLS 配置。
3. 目标部署的备份恢复与事故响应演练。
4. 部署负责人安全签批。

四项全部完成前，Server 角色仍为私网/VPN-only。

## 姿态开关

`EUROGAS_NEXUS_DEPLOYMENT_POSTURE=security_accepted` 是前置条件，不是签批。
只有 posture 为 `security_accepted` 且
`EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` 指向存在的文件时，
`public_network_deployment_allowed()` 才返回 true。
