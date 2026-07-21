# 部署角色

## 明确决策

Eurogas Nexus 按设备角色交付，且只有以下三种模式：

| 角色 | 部署设备 | 安装内容 | API 地址 | 数据库访问 |
| --- | --- | --- | --- | --- |
| `Server` | 专用服务器或虚拟机 | PostgreSQL、迁移、API、HTTPS 网关、采集任务、可选模拟价格任务 | 客户自有域名的 HTTPS 地址 | 仅后端服务 |
| `Client` | 交易员工作站 | 仅 Windows 或 Linux 客户端 | 现有服务器的 `/api` HTTPS 地址 | 永不访问 |
| `AllInOne` | 演示、试用或单用户工作站 | 本地 PostgreSQL、迁移、API、采集任务和桌面 Client | 仅回环地址 `http://127.0.0.1:8765/api` | 仅后端服务 |

不存在隐含的第四种模式。客户端永远不会得到 PostgreSQL 地址、数据库
密码、供应商密钥或数据库迁移权限。

## Release 产物选择

独立的 Windows NSIS 安装包**仅包含 Client**。安装后只会以整机模式创建桌面
程序和卸载程序，不会安装 PostgreSQL、FastAPI 后端、Alembic 迁移、
HTTPS 网关或数据采集任务。

应按部署角色选择 Release 产物：

- `Client`：下载 `Eurogas-Nexus-Client-0.5.0-x64-setup.exe`，并连接到一个已经存在、可访问且以 `/api`
  结尾的 HTTPS 后端地址；
- `Server`：下载 `Eurogas-Nexus-Server-Windows.zip` 并运行
  `Deploy-EurogasNexus.ps1 -Role Server`，不需要桌面安装包；
- `AllInOne`：只下载
  `Eurogas-Nexus-AllInOne-<版本>-<提交>-x64-setup.exe`。该安装包已包含桌面
  Client 和本地 API 镜像，会自动完成 Docker 与 PostgreSQL 配置。

因此，安装后目录里只有桌面程序和卸载程序，属于正常的 Client 安装结果，
不表示数据库和后端已经安装。Release 说明和产物命名必须明确标注这一边界；
相关生产化工作记录在
`docs/release/PRODUCTION_READINESS_BACKLOG.md` 的 `DEP-001`。

## Windows 部署入口

Windows 部署包包括：

- `Deploy-EurogasNexus.ps1`：面向实施人员的统一角色部署工具；
- `Install-EurogasNexusServerRuntime.ps1`：部署工具内部调用的服务器运行时脚本；
- `compose.yaml`、`Caddyfile` 和 API 镜像引用；
- 中英文运维说明；
- 作为独立 Release 产物提供的 Client-only NSIS 客户端安装包。

以管理员身份运行 PowerShell，并先执行无副作用的预检：

```powershell
./Deploy-EurogasNexus.ps1 -Action Preflight -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus_0.5.0_x64-setup.exe
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
5. 在一次性容器中显式执行 `alembic upgrade head`；
6. 启动 API 和 HTTPS 网关；
7. 除非指定 `-SkipPublicData`，否则采集 ECB 和 ENTSOG；
8. 验证 API、数据库连接和迁移版本。

首次采集后，运行时每 30 分钟更新 ECB、ENTSOG 运行/容量和已授权的 GIE 数据，
每 24 小时更新 ENTSOG 参考拓扑。供应商失败会保留在 `ingestion_runs` 和“数据源”
页面中，后台任务不会伪造替代的设施数据。

GIE 采集在客户通过“数据源”工作流保存自己的 GIE 密钥后才启用。授权价格
供应商在客户配置相应凭据之前保持禁用。

`v0.5-preview` 尚未实现多用户登录或 SSO，因此 Server 和 AllInOne 必须指定
`-PrivateNetworkOnly`，部署在客户防火墙或 VPN 白名单之后，严禁直接暴露到公网。
HTTPS 只保护传输，不能替代用户授权。后端认证和权限控制完成前，公网及多租户
部署均属于阻塞项。

## Client 角色

客户端设备只需要签名 NSIS 安装包和现有服务器 HTTPS 地址：

```powershell
./Deploy-EurogasNexus.ps1 -Action Install -Role Client `
  -ServerApiUrl https://nexus.example.com/api `
  -ClientInstallerPath ./Eurogas-Nexus_0.5.0_x64-setup.exe
```

部署工具先验证 `/api/health`，再静默运行签名 NSIS，并只写入如下客户端部署
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

部署工具默认拒绝签名无效或未签名的安装包。内部预览测试可使用
`-AllowUnsignedPreview`，客户交付不得使用该参数。

## AllInOne 角色

AllInOne 是 Windows 一键试用安装包。测试电脑需要 64 位 Windows 10/11、
管理员权限、8 GB 内存、10 GB 可用磁盘，以及已经安装的 Docker Desktop 和
Docker Compose v2。首次安装需要联网。电脑不需要预装 Python、Node.js、Rust、
Git、PostgreSQL，也不需要源代码、域名或 TLS 证书。

直接运行 `Eurogas-Nexus-AllInOne-...-x64-setup.exe`。安装器会按顺序：

1. 检查 Docker Compose；如果 Docker Desktop 已安装但未启动，则自动启动并等待；
2. 加载安装包内与当前 Release 提交绑定的 API 镜像；
3. 拉取官方 `postgres:16-alpine` 镜像；
4. 用密码学安全随机数生成数据库和后端密钥，并限制配置文件权限；
5. 启动 PostgreSQL，并显式执行 `alembic upgrade head`；
6. 将预览输入和带 `_Sim` 标记的模拟行情写入 PostgreSQL；
7. 启动 API、模拟行情循环任务和公开数据源采集任务；
8. 以整机模式安装桌面 Client，并写入受管本机 API 地址；
9. 通过 `/api/health` 验证成功后才结束安装。

API 和 PostgreSQL 的宿主机端口只绑定 `127.0.0.1`，不会向局域网暴露。模拟源
与正式授权源走相同的采集、标准化、PostgreSQL、API、SDK 和客户端链路，并
保留 `_Sim` 来源标记。高级实施人员仍可检查仓库中相同的 PowerShell 与 Compose
源文件，但 Release 不再提供第二个含义不清的 AllInOne ZIP 包。

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
