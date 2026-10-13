# 服务器运行时部署包

本目录是 `Server` 和 `Server` 使用的服务器运行时定义。正常实施应运行
`Deploy-EurogasNexus.ps1`，不应手工修改或逐个启动 Compose 服务。

服务包括 PostgreSQL 16、一次性配置预检、一次性 Alembic 迁移、FastAPI、
Caddy HTTPS 网关和可选公开数据采集。客户交付不包含模拟价格或预览种子服务。
PostgreSQL 与 API 仅
绑定回环地址，客户通过 HTTPS 网关访问。目录中不包含任何密钥。

`env.server.example` 是本技术栈的环境变量模板，由
`src/eurogas_nexus/core/config_contract.py` 经
`python scripts/ci/generate_env_template.py` 生成，覆盖产品实际读取的全部变量；
请勿手工编辑。

**环境配置错误时技术栈拒绝启动。** `config-check` 服务在迁移与 API 之前运行
`scripts/ops/check_config.py`：缺少凭据加密密钥、OIDC 配置不完整、变量名拼写
错误、或 release 部署中残留开发专用开关，都会在启动阶段被拦下，而不是在用户
首次使用时表现为 503 或一个被静默忽略的设置。error 阻断启动，warning（密钥
无法刻意轮换、未声明受信代理跳数）仅报告并交由运维判断。部署前可单独运行：

```bash
python scripts/ops/check_config.py --env-file <你的环境文件> --strict
```

`--strict` 将 warning 也视为错误，发布门禁应使用该形式。

由 `Dockerfile.api` 构建的 API 镜像还包含 Python 运行时锁定依赖的许可证/
声明文本，位于 `/usr/share/licenses/eurogas-nexus/python-license-texts`
（`manifest.json` 与 `texts/`），在构建时从镜像自身的 site-packages 依据
`requirements-runtime.lock` 收集；收集缺失或不完整会导致镜像构建失败。
这些是技术性声明，不构成法律结论。可用
`docker run --rm --entrypoint cat <镜像>` 加上上述 `manifest.json` 路径查看。

可用
`docker run --rm --network none <镜像> python scripts/release/verify_python_license_texts.py`
校验镜像内交付的证据；该工具默认使用上述路径和镜像自身的
`requirements-runtime.lock`，发现篡改、不完整、多余或缺失证据时以非零状态退出，
属于技术性校验，不构成法律结论。发布 `container-acceptance` 作业在写入 G19
PASS 之前，会在 linux/amd64 镜像摘要内执行同一命令；arm64 条目仅核对清单是否
存在，不在其中执行。

完整流程见 `docs/deployment/DEPLOYMENT_ROLES-CN.md`。

API wheel 排除可执行市场模拟器；镜像只复制
`scripts/release/runtime_artifact_policy.json` 中列出的脚本，保留启动、公开数据
采集、灾难恢复及许可证校验工具。构建时校验实际 wheel 与已安装镜像内容；
容器验收在不可变 amd64 摘要中再次执行
`python scripts/release/verify_customer_artifact.py`。Docker 构建上下文排除本地
`.dnx*` 工作数据。这些内容检查不证明已有数据库没有模拟行；客户数据验收
仍需单独核查数据库来源信息。
