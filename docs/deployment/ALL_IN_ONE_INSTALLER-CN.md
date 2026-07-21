# Windows AllInOne 一键安装包

## 应下载哪个文件

对于已经安装 Docker Desktop 的 Windows 测试电脑，请从 GitHub Release 下载
`Eurogas-Nexus-AllInOne-<版本>-<提交>-x64-setup.exe`。不要再自行组合 Client-only
安装包与部署 ZIP。

## 前置条件

- 64 位 Windows 10 或 Windows 11；
- 管理员权限；
- 已安装 Docker Desktop 和 Docker Compose v2；
- 8 GB 内存和 10 GB 可用磁盘；
- 首次安装可联网，用于拉取官方 PostgreSQL 镜像并按需采集最新公开数据。

Windows 11 通常已经包含 Evergreen WebView2 Runtime；只有检测到运行时缺失时，
Client 安装程序才会调用微软 WebView2 引导安装程序。

预览部署不需要 Python、Node.js、Rust、Git、本机 PostgreSQL、源代码、域名、
TLS 证书或付费行情密钥。

## 安装结果

安装器会部署桌面前端、仅绑定回环地址的 FastAPI 容器、PostgreSQL 16、显式
Alembic 迁移、数据库内预览输入、数据库内 `_Sim` 模拟行情及公开数据采集任务。
Client 只通过 `http://127.0.0.1:8765/api` 读取运行数据，绝不直连 PostgreSQL。

安装日志位于
`%ProgramData%\Eurogas Nexus\Logs\all-in-one-install.log`，其中不会记录自动生成的
数据库密码或后端密钥。

## 日常操作

开始菜单提供“打开、启动服务、停止服务、运行状态、运行日志、卸载”等入口。
普通卸载会移除应用并停止容器，但保留 PostgreSQL Docker 数据卷。永久删除数据
只能通过明确的 `PurgeData` 管理动作完成，并要求手工输入 `PURGE` 确认。
卸载程序也会询问是否永久删除数据，并始终把“否”设为安全默认值。

付费价格源、GIE、天气和 LLM 服务在客户通过后端数据源设置保存自有凭据前保持
禁用。

在发布流水线接入获批的 Authenticode 代码签名证书前，预览安装包可能触发
Windows SmartScreen。正式客户交付必须完成签名，不能把预览状态描述成已完成
生产签名。
