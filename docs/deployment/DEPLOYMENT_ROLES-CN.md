# 部署角色

## 明确决策

Eurogas Nexus 按设备角色交付，且只有以下两种模式：

| 角色 | 部署设备 | 安装内容 | API 地址 | 数据库访问 |
| --- | --- | --- | --- | --- |
| `Server` | 专用服务器或虚拟机 | PostgreSQL、迁移、API、HTTPS 网关、采集任务、可选模拟价格任务 | 客户自有域名的 HTTPS 地址 | 仅后端服务 |
| `Client` | 交易员工作站 | 仅 Windows 或 Linux 客户端 | 现有服务器的 `/api` HTTPS 地址 | 永不访问 |

不存在隐含的第四种模式。客户端永远不会得到 PostgreSQL 地址、数据库
密码、供应商密钥或数据库迁移权限。

## 显式部署姿态开关

后端读取 `EUROGAS_NEXUS_DEPLOYMENT_POSTURE`：

- `private_network_preview`（默认）：当前姿态；Server 仍必须位于
  客户防火墙或 VPN 白名单之后。
- `security_accepted`：仅当
  `EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` 指向存在的、经运营方评审的
  验收证据文件时才有效。

`public_network_deployment_allowed()` 在两项条件同时成立前始终返回 false。
在真实部署完成外部安全验收前，本仓库的 Windows 部署预检保持不变。

## 部署环境配置档

本包随附的运行时定义将所有服务的 `EUROGAS_NEXUS_ENV` 设为 `release`、
`EUROGAS_NEXUS_API_PROFILE` 设为 `release`。这两个值是面向客户姿态的一部分，
不是装饰：

- 它们把仅限开发环境的表面挡在客户部署之外。尤其是模型上下文协议（MCP）工具
  表面：在 `trial`/`release` 配置档下，只要持久化服务身份尚未建成，MCP 工具的
  发现与调用就会被后端与 MCP 适配器拒绝，而不是仅靠文档声明；
- 未设置配置档时默认是 `development`（开发者默认值），它并不说明该部署是否
  可以安全地面向客户。

在客户部署中不得删除或覆盖这两个变量。如果某个部署确实只是开发或测试工作区，
应当显式说明，而不是用"未设置"来表达。

## Release 产物选择

独立的 Windows NSIS 安装包**仅包含 Client**。安装后只会以整机模式创建桌面
程序和卸载程序，不会安装 PostgreSQL、FastAPI 后端、Alembic 迁移、
HTTPS 网关或数据采集任务。

应按部署角色选择 Release 产物：

- `Client`：下载 `Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe`，并连接到一个已经存在、可访问且以 `/api`
  结尾的 HTTPS 后端地址；
- `Server`：下载 `Eurogas-Nexus-Server.zip` 并运行
  `Deploy-EurogasNexus.ps1 -Role Server`，不需要桌面安装包；
因此，安装后目录里只有桌面程序和卸载程序，属于正常的 Client 安装结果，
不表示数据库和后端已经安装。Release 说明和产物命名必须明确标注这一边界；
相关生产化工作记录在
`docs/release/RELEASE_READINESS.md` 的 `DEP-001`。

## Windows 部署入口

Windows 部署包包括：

- `Deploy-EurogasNexus.ps1`：面向实施人员的统一角色部署工具；
- `Install-EurogasNexusServerRuntime.ps1`：部署工具内部调用的服务器运行时脚本；
- `compose.yaml`、`Caddyfile` 和 API 镜像引用；
- `release-identity.json`：Release 身份记录（schema 版本、应用与 Release
  版本、渠道、完整提交 SHA，以及按 `sha256` 摘要固定的 API 镜像仓库）；
- 中英文运维说明。

Client-only NSIS 客户端安装包作为独立的 GitHub Release 产物发布，
不包含在 Server 运维 ZIP 包中。

两个 Windows 入口脚本都从 `release-identity.json` 解析版本、渠道和镜像引用：
无需源码检出，也无需手工设置 `EUROGAS_NEXUS_VERSION`；若该变量或
`EUROGAS_NEXUS_RELEASE_CHANNEL` 与包内身份冲突，脚本会直接拒绝。身份文件
缺失、格式错误或内部不一致时，脚本会失败关闭，不会猜测版本。API 镜像按该
记录中的摘要固定，安装器不会静默回退到浮动 tag；显式传入但与固定引用冲突的
镜像会被拒绝，而不是覆盖固定值。仓库字段的最后一段路径若携带 tag 会按格式
错误被拒绝（引用前部的镜像仓库端口仍然允许）。ZIP 自身的 SHA-256 **不会**
写入压缩包内部（压缩包无法自我哈希），请使用 Release 的 `SHA256SUMS` 与
`release-manifest.json` 校验。

以管理员身份运行 PowerShell，并先执行无副作用的预检：

```powershell
./Deploy-EurogasNexus.ps1 -Action Preflight -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe
```

预检不会安装 Docker、启动容器、修改防火墙或写入凭据。

## Server 角色

服务器设备必须预先具备：

- 与所选 Docker/Compose 运行时兼容的 Windows 10/11 或 Windows Server；
- PowerShell 5.1 或更高版本；
- 已安装且正在运行的 Docker Engine 与 Docker Compose v2；
- 至少 8 GB 内存和 10 GB 可用磁盘；
- 已解析到服务器的客户域名；
- 该域名对应的客户自有 PEM 证书和 PEM 私钥；
- 已由客户管理员批准的入站 HTTPS 端口。
- 服务器上明确的回环或私网 IP；拒绝绑定 `0.0.0.0`。

Eurogas Nexus **不会静默下载或安装** Docker Desktop、WSL、PostgreSQL、
证书或证书颁发机构。这些操作会影响授权、重启、企业策略和信任链，必须
由客户明确完成。

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Server `
  -ServerName nexus.example.com `
  -HttpsBindAddress 10.20.30.40 `
  -HttpsPort 8443 `
  -TlsCertificatePath C:/secure/nexus.example.com.crt `
  -TlsPrivateKeyPath C:/secure/nexus.example.com.key `
  -PrivateNetworkOnly
```

安装严格按以下顺序执行：

1. 检查依赖、端口、证书和 Compose；
2. 生成随机数据库密码和后端密钥；
3. 将受限配置写入 `%ProgramData%\Eurogas Nexus`；
4. 启动 PostgreSQL 并执行健康检查；
5. 在一次性容器中执行受控数据库升级（`upgrade_database.py upgrade`：新库无需备份，已安装的库需要最近 24 小时内登记的备份；见 `docs/operations/DATABASE_UPGRADE.md`）；
6. 启动 API 和 HTTPS 网关；
7. 除非指定 `-SkipPublicData`，否则采集 ECB 和 ENTSOG；
8. 验证 API、数据库连接和迁移版本。

首次采集后，`public-ingestion-worker` 运行产品的数据运维调度器（`scripts/ops/run_dataops_scheduler.py`，与参考库使用同一路径）。每个公共数据源按各自的计划与读取边界运行、单独失败、按调度器策略重试，并在“管理 → 数据源”中显示状态。供应商失败会保留在 `ingestion_runs` 和数据源中心，后台任务不会伪造替代数据。

| 数据源 | 计划 | 需要 |
|---|---|---|
| ECB 汇率 | 每日 | 无 |
| ENTSOG 流量、容量（滚动 7 个燃气日）、参考网络（至多每日） | 每小时 | 管理员批准（见“首次运行”） |
| GIE AGSI 储气、ALSI LNG | 每日 | 批准与本公司 GIE 密钥 |
| GIE IIP REMIT 储气与 LNG 停运 | 每 30 分钟 | GIE 密钥 |
| ENTSOG REMIT 输气停运 | 每小时 | 无 |
| EIA Henry Hub | 每日 | 本公司 EIA 密钥 |
| ENTSO-E 日前价格、负荷、发电（NL、DE-LU、BE、FR；7 天） | 每小时 | 本公司 ENTSO-E 令牌 |
| Elexon 英国发电、需求、市场指数 | 每 30 分钟 | 无 |
| National Gas 英国储气、LNG 与需求 | 每 3 / 6 小时 | 无 |
| SONIA、€STR、SOFR 定盘利率 | 每日 | 无 |

密钥保存在“管理 → 数据源”（凭据，使用 `EUROGAS_NEXUS_SECRET_KEY` 加密），或在运行环境中提供 `GIE_API_KEY`/`GIE_API_KEY_FILE`、`EIA_API_KEY`、`ENTSOE_SECURITY_TOKEN`。缺少密钥时，相应数据源的运行记录为 `credential_missing`，不进行任何请求；保存密钥后，默认关闭的需密钥数据源（GIE、GIE IIP、ENTSO-E）会在下一次调度扫描时自动开启，除非运维人员已将其关闭。授权价格供应商在客户配置相应凭据与数据范围之前保持禁用。

软件包版本 `1.0.0-beta`（`beta` 渠道）支持公司 SSO（OIDC）或本地账户登录，每个接口都会校验调用者
权限，但尚未经过独立渗透测试（关口 G15）。因此 Server 仍必须指定 `-PrivateNetworkOnly`，部署在客户
防火墙或 VPN 白名单之后，严禁直接暴露到公网。HTTPS 只保护传输，不能替代上述评审。G15 通过之前，
公网及多租户部署仍属阻塞项。

## Client 角色

客户端设备只需要 NSIS 安装包和现有服务器 HTTPS 地址：

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe
```

部署工具先验证 `/api/health`，再静默运行 NSIS 安装包，并只写入如下客户端部署
记录：

```json
{
  "schema_version": 1,
  "role": "Client",
  "api_base_url": "https://nexus.example.com/api"
}
```

桌面程序首次启动时读取该记录。用户之后可在“设置”中测试和更换服务器。
Web 部署通过 `VITE_EUROGAS_API_BASE_URL` 指定相同的 HTTPS 地址策略。

部署工具默认拒绝签名无效或未签名的安装包。已发布的安装包（包括 1.0.0 beta）**未签名**：是否签名
由部署方公司决定（发布中的 `signing-state.json` 逐个文件记录）。可先用公司自己的代码签名证书签名，
部署工具即可接受；或仅在验收安装时，先按 `SHA256SUMS` 与 GitHub 证明核对文件，再使用
`-AllowUnsignedPreview`，工具输出结果中会显示 `unsigned_preview_allowed: true`。

## 网络要求

拉取容器镜像和采集最新公开数据需要互联网。客户端安装时必须能够连接其
配置的 API。完全离线部署需要预先制作镜像归档和离线安装包；部署脚本不会
进行未披露的互联网搜索或下载。

## 运维

- `Repair` 重新应用 Compose 和迁移，不删除数据；
- `Validate` 检查 API、PostgreSQL、必需表和 Alembic 版本；
- `Uninstall` 停止服务器运行时并保留 PostgreSQL 卷；
- 只有 `Uninstall -PurgeServerData` 会删除运行时数据库卷；
- 桌面客户端应从 Windows“应用”中卸载，部署工具只移除受管服务器地址。

升级或清除前必须备份 PostgreSQL。不得将 `.env`、私钥、供应商原始数据或
客户数据放入支持工单或公开仓库。

## 首次运行：批准公共数据源

ENTSOG 与 GIE 仅在管理员代表贵公司批准后才会读取（这是一道“默认拒绝”的闸门：其条款要求署名，产品会记录由谁接受了条款）。安装程序不会批准任何数据源：是否接受提供方条款由客户决定。批准之前，摄取运行会以稳定原因码 `source_not_approved` 被拒绝（在数据源中心、数据馈送与运行历史中可见），交易台页面显示“ENTSOG 流量：数据源尚未批准 — 管理 → 连接器”，`/api/health/ready` 在 `attention` 下列出这些数据源（就绪状态本身仍为 `ready`）。

使用浏览器：管理 → 数据源 →“需要您批准的公共数据源”，见 [ADMIN.md](../user/manual/ADMIN.md)。无界面安装（幂等；重复已生效的批准不会改变任何内容）：

```bash
docker compose run --rm public-ingestion python scripts/ops/approve_public_source.py --list
docker compose run --rm public-ingestion python scripts/ops/approve_public_source.py \
  --all-open --operator <您的标识> --reason "<工单或原因>" --accept-terms
```

`--revoke --source entsog --operator <标识> --reason "<原因>"` 撤销批准（下一次计划运行起停止读取，已存储数据保留）。`--list` 显示每个数据源的状态及其条款摘要；`--accept-terms` 表示您已阅读并代表公司接受（缺少该参数则不记录任何内容）。批准会写入审计（`source.approval`），并执行一次有界的实时检查。若 GIE 在存储密钥之前获批，其状态为“已批准，等待密钥”，并在密钥存储后的首次读取时进行检查。
