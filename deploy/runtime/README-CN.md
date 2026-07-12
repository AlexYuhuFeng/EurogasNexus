# 服务器运行时部署包

本目录是 `Server` 和 `AllInOne` 使用的服务器运行时定义。正常实施应运行
`Deploy-EurogasNexus.ps1`，不应手工修改或逐个启动 Compose 服务。

服务包括 PostgreSQL 16、一次性 Alembic 迁移、FastAPI、Caddy HTTPS 网关、
可选公开数据采集和可选模拟价格采集。PostgreSQL 与 API 仅绑定回环地址，客户
通过 HTTPS 网关访问。目录中不包含任何密钥。

完整流程见 `docs/deployment/DEPLOYMENT_ROLES-CN.md`。
