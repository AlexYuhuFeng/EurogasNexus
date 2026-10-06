# 服务器运行时部署包

本目录是 `Server` 和 `Server` 使用的服务器运行时定义。正常实施应运行
`Deploy-EurogasNexus.ps1`，不应手工修改或逐个启动 Compose 服务。

服务包括 PostgreSQL 16、一次性 Alembic 迁移、FastAPI、Caddy HTTPS 网关、
可选公开数据采集和可选模拟价格采集。PostgreSQL 与 API 仅绑定回环地址，客户
通过 HTTPS 网关访问。目录中不包含任何密钥。

由 `Dockerfile.api` 构建的 API 镜像还包含 Python 运行时锁定依赖的许可证/
声明文本，位于 `/usr/share/licenses/eurogas-nexus/python-license-texts`
（`manifest.json` 与 `texts/`），在构建时从镜像自身的 site-packages 依据
`requirements-runtime.lock` 收集；收集缺失或不完整会导致镜像构建失败。
这些是技术性声明，不构成法律结论。可用
`docker run --rm --entrypoint cat <镜像>` 加上上述 `manifest.json` 路径查看。

完整流程见 `docs/deployment/DEPLOYMENT_ROLES-CN.md`。
