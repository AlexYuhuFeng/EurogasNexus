# 本地 Docker 运行时（中文摘要）

英文原文：[LOCAL_DOCKER_RUNTIME.md](LOCAL_DOCKER_RUNTIME.md)，二者不一致时以英文为准。

`.local-runtime` Docker 栈默认使用 development profile：打开
`http://127.0.0.1:3000` 不需要 API token，且 `/docs` 与 `/openapi.json` 可用；
本地 public-ingestion worker 只运行 ECB，配置 provider certification/凭据前
不运行 ENTSOG/GIE 实时 worker。切换回 release profile 后，需在 Settings 配置
以 `/api` 结尾的后端地址、`.local-runtime/.env` 中的
`EUROGAS_NEXUS_PUBLIC_API_TOKEN` 以及合法的 operator principal。
release profile 下 `/docs` 与 `/openapi.json` 按设计返回 404。
