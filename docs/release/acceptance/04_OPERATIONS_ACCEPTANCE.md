# 04 — 运维团队验收意见：可运维性实测

> **English abstract (added 2026-10-30; the record below is unchanged and in its original
> language).** Operations team's hand-over acceptance on 2026-10-07, every item reproduced by
> command. **Verdict: CONDITIONAL hand-over.** The two P0 findings (OPS-01, OPS-02) were
> fixed and independently re-checked (§2.10, §4.5); the conclusion rests on the five P1
> items in §11.

| 项目 | 内容 |
| --- | --- |
| 文档性质 | 接手方（运维团队）对 Eurogas Nexus 交付软件的可运维性验收与接手意见 |
| 审计日期 | 2026-10-07（Asia/Shanghai） |
| 被审对象 | 工作副本 `HEAD = b9977bc35cad2f89f9a9363fd001a6cc825f533d` + 29 个已修改文件 + 28 个未跟踪文件 |
| 审计方法 | **不采信仓库文档结论**；每一项都由本机实际执行的命令产生输出，命令与输出一并记录 |
| 实测环境 | Windows + 内嵌 PostgreSQL 16.2（`127.0.0.1:51356`）+ Docker Desktop 29.8.1（无 Docker Hub 出口） |
| 证据落盘 | `<repo>/.dnx-out/ops-review/`（被 `.gitignore` 的 `/.dnx-*` 覆盖，不进入交付物） |
| **接手结论** | **有条件接手（CONDITIONAL）** — 原 2 项 P0（OPS-01、OPS-02）已修复并经 §2.10 / §4.5 独立复核通过；结论改由 §11 的 5 项 P1 决定 |
| 复核轮次 | 第 2 轮（2026-10-07）。供应商修复 OPS-01 / OPS-02 后，复核方**独立重跑**全部相关命令；原 OPS-02B 的分歧已定位到确切触发条件（§4.4.2），并新发现 OPS-12（§2.11） |

> **运维立场声明。** 本文判断的是"运维团队拿到这份交付物后，能不能不依赖供应商现场支持地安装、配置、迁移、备份、恢复、升级、回滚和排障"。
> 组件质量高不等于可运维：本次结论由 §11 的硬缺口决定。
>
> **复核声明。** 第 2 轮没有采信"已修复"这一结论本身：§2.10 与 §4.5 中的通过证据全部由复核方在本机重新执行产生
> （依赖版本：SQLAlchemy 2.0.52 / pg8000 1.31.5 / PostgreSQL 16.2 / Docker 29.8.1）。

---

## 0. 计数总览

| 分类 | 数量 | 说明 |
| --- | --- | --- |
| **实测项** | **第 1 轮 29 组 + 第 2 轮 8 组 = 37 组** | 逐条命令执行并记录退出码与输出，见 §2–§9；第 2 轮为针对修复项的独立复核 |
| **无法实测项** | **8 项** | 均为环境或客户方前置条件缺失，见 §10；每项写明"为何无法实测 + 需要什么条件" |
| ~~P0（阻断接手）~~ | **0（已清零）** | ~~OPS-01、OPS-02~~ → 均已修复并经 §2.10 / §4.5 独立复核通过 |
| P1（接手前必须补齐） | 5 | OPS-03、OPS-04、OPS-05、OPS-06、OPS-12 |
| P2（可带缺陷接手，记入待办） | 5 | OPS-07 … OPS-11 |

**第 2 轮复核结论**：

| 编号 | 第 1 轮判定 | 复核结果 |
| --- | --- | --- |
| OPS-01 | P0，安装器 `.env` 缺 `EUROGAS_NEXUS_PUBLIC_API_TOKEN` | **已修复，复核通过**（§2.10）。阻断解除；残留 1 条 `--strict` 告警（§2.10.3） |
| OPS-02A | P0，`env=` 整体替换子进程环境 | **已修复，复核通过**（§4.5） |
| OPS-02B | P0，`CREATE DATABASE` 触发 25001 | **已修复，复核通过**；**原观察确认成立**，触发条件已定位（§4.4.2），双方分歧已解释 |
| OPS-12 | — | **第 2 轮新发现**（§2.11）：`.env` 带 UTF-8 BOM 时预检 fail-open、compose 直接判项目无效 |

**通过实测确认可用的能力（正面结论）**：配置预检、迁移预检、0039 downgrade 保护、空库全链迁移、备份文件生成与真实恢复、安装器发布身份校验与密钥 ACL、运维脚本（巡检/清理/恢复）的 dry-run 语义、日志不泄漏任何敏感值。

---

## 1. 结论摘要

| 维度 | 结论 |
| --- | --- |
| 配置运维 | **通过**。7 类行为全部实测命中，错误码与退出码语义正确（0/1/2）。⚠️ 但 `.env` 带 UTF-8 BOM 时预检会 fail-open（OPS-12，§2.11）。 |
| 迁移运维 | **通过**。预检在无库时 fail-closed；0039 的 downgrade 在存在超长值时**真的拒绝**，且不破坏版本与列宽。 |
| 备份/恢复 | **通过**（第 2 轮修正）。备份恢复数据路径真实可用（319,490 B 转储 → 新库行数完全一致）；自动化演练脚本原样跑不通的缺陷（OPS-02）**已修复并复核通过**，现可无人干预跑完 `ok=true / database_created=true / api_smoke 200`（§4.5）。 |
| 部署栈 | **无法实测**。镜像拉不到，栈起不来；`docker compose config` 静态渲染通过。 |
| 可观测性与敏感值 | **部分通过**。日志不泄漏 header 中的令牌/密钥/行情值；但**查询串令牌会被明文写进 access log**（OPS-05），且 metrics 有一处非法样本值（OPS-06）。 |
| 升级/回滚 | **部分通过**。回滚路径文档化完整且引用的脚本全部存在；安装器对 digest 校验严格；但 **compose 自身不固定 digest**（OPS-03）。 |
| 密钥管理 | **通过（有缺口）**。密钥集中在 ACL 受限的 `.env`；有凭据/身份密钥轮换 API；但**部署级令牌无轮换流程**（OPS-11）。 |

---

## 2. 配置运维实测（`scripts/ops/check_config.py`）

预检逻辑位于 `src/eurogas_nexus/core/preflight.py`（647 行，11 个检查项）。以下 8 个场景的环境文件由
`.dnx-out/ops-review/make_envs.py` 生成，原始输出存于 `.dnx-out/ops-review/config-matrix.txt`。

统一命令形式：

```powershell
$env:PYTHONPATH="$r\.dnx-deps;$r\src;$r\packages\python-sdk\src"
& $py "$r\scripts\ops\check_config.py" --env-file <scenario>.env
```

### 2.1 完整环境 → **0 findings，EXIT 0** ✅

```
##### SCENARIO: 01_full_release.env #####
Eurogas Nexus configuration preflight
  environment : release
  api profile : release

No findings.

No errors, 0 warning(s).
EXIT=0
```

> 注：仅当 release 档位下 `FORWARDED_ALLOW_IPS`、OIDC 三元组、全部生产开关、`RUNTIME_STORE_DATABASE_URL`、
> `EUROGAS_NEXUS_PUBLIC_API_TOKEN`、合法 Fernet 密钥**同时**正确时才可能 0 findings。上例已做到。

### 2.2 缺必填 → **2 error，EXIT 1** ✅

```
ERROR [missing_required] EUROGAS_NEXUS_PUBLIC_API_TOKEN: not set: every route profile identifies its callers; without it the API refuses protected routes with 503
        fix: set the deployment token, or enable EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS if this deployment really does trust its network
ERROR [missing_required] EUROGAS_NEXUS_SECRET_KEY: not set: provider credentials are encrypted with it and identity digests are keyed by it
        fix: generate one with: python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

2 error(s), 0 warning(s). This deployment must not start until the errors are resolved.
EXIT=1
```

### 2.3 变量名拼错（`..._SECRET_KEYS`）→ **unknown_variable + 建议正确名，EXIT 1** ✅

```
ERROR [unknown_variable] EUROGAS_NEXUS_SECRET_KEYS: set but not part of the configuration contract, so it has no effect
        fix: did you mean EUROGAS_NEXUS_SECRET_KEY? Nothing reads the name as written
ERROR [missing_required] EUROGAS_NEXUS_SECRET_KEY: not set: provider credentials are encrypted with it and identity digests are keyed by it
EXIT=1
```

拼错的名字**同时**被报为"无效果"，这正是运维最需要的诊断（否则只会看到"密钥未设置"而不知为何）。

### 2.4 占位密钥 → **3 placeholder_secret，EXIT 1** ✅

`EUROGAS_NEXUS_SECRET_KEY=changeme`、`EUROGAS_NEXUS_PUBLIC_API_TOKEN=your-token-here`、`GIE_API_KEY=example`：

```
ERROR [placeholder_secret] EUROGAS_NEXUS_SECRET_KEY: the value is a placeholder, not a key
ERROR [placeholder_secret] EUROGAS_NEXUS_PUBLIC_API_TOKEN: the value is a placeholder, not a credential
ERROR [placeholder_secret] GIE_API_KEY: the value is a placeholder, not a credential
3 error(s), 0 warning(s). This deployment must not start until the errors are resolved.
EXIT=1
```

### 2.5 开发开关留在生产 → **4 dev_setting_in_production，EXIT 1** ✅

`ALLOW_ANONYMOUS_CALLERS=1`、`DB_ECHO=true`、`DEV_LOGIN_USERNAME=ops-review`、`OIDC_ALLOW_HTTP=1`：

```
ERROR [dev_setting_in_production] EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS: enabled in a production deployment: anonymous callers would be accepted in a production deployment
ERROR [dev_setting_in_production] EUROGAS_NEXUS_OIDC_ALLOW_HTTP: enabled in a production deployment: OIDC discovery and token exchange would cross cleartext
ERROR [dev_setting_in_production] EUROGAS_NEXUS_DEV_LOGIN_USERNAME: enabled in a production deployment: the development credential login is not mounted in production profiles, so this only leaks a credential into the environment
ERROR [dev_setting_in_production] EUROGAS_NEXUS_DB_ECHO: enabled in a production deployment: echoed SQL can carry business values into the log
4 error(s), 0 warning(s). This deployment must not start until the errors are resolved.
EXIT=1
```

### 2.6 OIDC 半配置（issuer 有、client_id/redirect_uri 空）→ **EXIT 1** ✅

```
ERROR [oidc_partially_configured] EUROGAS_NEXUS_OIDC_CLIENT_ID, EUROGAS_NEXUS_OIDC_REDIRECT_URI: interactive SSO is partially configured, so sign-in fails with oidc_not_configured at the moment a user tries it
        fix: set the missing value(s): EUROGAS_NEXUS_OIDC_CLIENT_ID, EUROGAS_NEXUS_OIDC_REDIRECT_URI
1 error(s), 0 warning(s). This deployment must not start until the errors are resolved.
EXIT=1
```

### 2.7 代理跳数未声明 → **warning，EXIT 0；`--strict` 时 EXIT 1** ⚠️（有意设计，见 OPS-08）

```
WARN  [proxy_hop_not_trusted] FORWARDED_ALLOW_IPS: a production deployment is served but no trusted proxy hop is declared; the API will observe every request as plain http, which suppresses the Secure cookie attribute
        fix: set FORWARDED_ALLOW_IPS to the proxy network (for example 172.16.0.0/12) when TLS is terminated in front of the API

No errors, 1 warning(s).
EXIT=0

--- 同一环境加 --strict ---
1 warning(s); --strict treats them as errors.
EXIT=1
```

### 2.8 附带验证：开发档位未声明浏览器来源 → **warning，EXIT 0** ✅

```
WARN  [dev_origin_not_declared] EUROGAS_NEXUS_CORS_ORIGINS: a development profile is served and no browser origin is declared; ... every cookie-authenticated mutation will be refused with origin_not_allowed.
EXIT=0
```

### 2.9 退出码语义与 `--json` ✅

```powershell
& $py scripts/ops/check_config.py --env-file <完整环境> --json
```
```json
{ "api_profile": "release", "environment": "release", "errors": 0, "findings": [], "ok": true, "warnings": 0 }
EXIT=0

& $py scripts/ops/check_config.py --env-file .dnx-out/ops-review/env/nope.env
cannot check: no environment file at ...\nope.env
EXIT=2
```

三种退出码（0 通过 / 1 有问题 / 2 检查无法执行）语义清晰，适合直接接入 CI 与安装器门禁。

### 2.10 ~~**P0 发现 OPS-01：安装器写出的 `.env` 缺 `EUROGAS_NEXUS_PUBLIC_API_TOKEN`，栈必然起不来**~~ → **已修复，复核通过** ✅

> **第 2 轮状态：已修复并独立复核通过。** §2.10.1 为第 1 轮原始观察（保留作为缺陷记录与回归基线），
> §2.10.2 为复核方在修复后重新执行得到的证据，§2.10.3 为残留项。

#### 2.10.1 第 1 轮原始观察（缺陷记录）

`scripts/install/windows/Install-EurogasNexusServerRuntime.ps1`（`Initialize-RuntimeFiles`，第 323–337 行）
写出的 `.env` 只包含以下 13 个键，其中**没有** `EUROGAS_NEXUS_PUBLIC_API_TOKEN`：

```
EUROGAS_NEXUS_API_IMAGE / EUROGAS_NEXUS_VERSION / EUROGAS_NEXUS_RELEASE_CHANNEL
POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_PORT / API_PORT
HTTPS_PORT / HTTPS_BIND_ADDRESS / SERVER_NAME
EUROGAS_NEXUS_SECRET_KEY / EUROGAS_NEXUS_INTERNAL_API_TOKEN
```

全仓库检索确认：`scripts/install/` 下关于 token 只有 2 处命中，均为 **internal** token：

```
命令: rg "Token|token" scripts/install
scripts\install\windows\Install-EurogasNexusServerRuntime.ps1:322:  $internalToken = ...
scripts\install\windows\Install-EurogasNexusServerRuntime.ps1:336:  "EUROGAS_NEXUS_INTERNAL_API_TOKEN=$internalToken"
```

**实测 1（compose 渲染）**——把安装器会写出的键值原样交给 compose：

```powershell
docker compose --env-file .dnx-out/ops-review/env/10_installer_written_setup.env -f deploy/runtime/compose.yaml config
```
```
time="..." level=warning msg="The \"EUROGAS_NEXUS_PUBLIC_API_TOKEN\" variable is not set. Defaulting to a blank string."   (×10)
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: ""            ← config-check 容器
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: ""            ← migrate 容器
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: ""            ← api 容器
```

**实测 2（把该容器环境喂给预检）**：

```powershell
& $py scripts/ops/check_config.py --env-file .dnx-out/ops-review/env/11_installer_container_env.env
```
```
ERROR [missing_required] EUROGAS_NEXUS_PUBLIC_API_TOKEN: not set: every route profile identifies its callers; without it the API refuses protected routes with 503
WARN  [secret_key_not_fernet] EUROGAS_NEXUS_SECRET_KEY: not a 32-byte urlsafe-base64 Fernet key; the product falls back to hashing the raw string, which cannot be rotated deliberately

1 error(s), 1 warning(s). This deployment must not start until the errors are resolved.
EXIT=1
```

**后果链条（compose.yaml 第 37–74 行）**：`config-check` 退出 1 → `migrate` 的
`depends_on: config-check: condition: service_completed_successfully` 永不满足 → `api` 永不启动。
**按仓库文档给出的 Windows 安装路径，栈一次也起不来**，且失败信息只出现在 `config-check` 的日志里。

同一份渲染还暴露第二个问题：安装器用 `New-HexSecret 32` 产生的 `EUROGAS_NEXUS_SECRET_KEY` 是 64 位十六进制串，
不是 32 字节 urlsafe-base64 Fernet 密钥，预检给出 `secret_key_not_fernet`（"cannot be rotated deliberately"）。
在 `--strict` 发布门禁下这同样会拒绝。

#### 2.10.2 修复内容与复核证据（第 2 轮）

供应商修复：`Initialize-RuntimeFiles` 现在生成并写入第 14 个键，重装时从既有 `.env` 保留原值
（与 internal token 同一模式）。复核方核对源码：

```
line 328:  $publicApiToken = if ($existing.EUROGAS_NEXUS_PUBLIC_API_TOKEN) { $existing.EUROGAS_NEXUS_PUBLIC_API_TOKEN } else { New-HexSecret 32 }
line 343:  "EUROGAS_NEXUS_PUBLIC_API_TOKEN=$publicApiToken"
```

**复核命令 1（compose 渲染，14 键变量集）**：

```powershell
docker compose --env-file .dnx-out/ops-review/env/10_installer_written_setup.env -f deploy/runtime/compose.yaml config
```
```
compose warnings about unset variables: 0               （修复前为 10）
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: 9d3f7c1a5e8b204f6a1c3e5d7b9f0a2c4e6d8b0f2a4c6e8d0b2f4a6c8e0d2b4f   ← config-check
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: 9d3f7c1a5e8b204f6a1c3e5d7b9f0a2c4e6d8b0f2a4c6e8d0b2f4a6c8e0d2b4f   ← migrate
      EUROGAS_NEXUS_PUBLIC_API_TOKEN: 9d3f7c1a5e8b204f6a1c3e5d7b9f0a2c4e6d8b0f2a4c6e8d0b2f4a6c8e0d2b4f   ← api
```
渲染出的健康检查同样取到非空令牌，不再会因空令牌而失败：
`req.add_header('X-Eurogas-Api-Key', os.environ['EUROGAS_NEXUS_PUBLIC_API_TOKEN']);`

**复核命令 2（把渲染后的容器环境喂给预检）**：

```powershell
& $py scripts/ops/check_config.py --env-file .dnx-out/ops-review/env/12_installer_container_env_fixed.env
```
```
Eurogas Nexus configuration preflight
  environment : release
  api profile : release

WARN  [secret_key_not_fernet] EUROGAS_NEXUS_SECRET_KEY: not a 32-byte urlsafe-base64 Fernet key; ...

No errors, 1 warning(s).
EXIT=0
```

**复核判定：OPS-01 阻断解除。** `missing_required` 消失，`config-check` 退出 0，
`migrate` / `api` 的依赖链可以满足。

#### 2.10.3 残留项（不阻断启动，但阻断 `--strict` 发布门禁）

安装器的 `EUROGAS_NEXUS_SECRET_KEY` 仍由 `New-HexSecret 32` 产生（64 位十六进制串），
因此预检仍给出 `secret_key_not_fernet`（"cannot be rotated deliberately"）。复核实测：

```powershell
& $py scripts/ops/check_config.py --env-file .dnx-out/ops-review/env/12_installer_container_env_fixed.env --strict
```
```
WARN  [secret_key_not_fernet] EUROGAS_NEXUS_SECRET_KEY: not a 32-byte urlsafe-base64 Fernet key; ...
1 warning(s); --strict treats them as errors.
EXIT=1
```

即：**按默认方式启动已经可以**，但 `deploy/runtime/README-EN.md:31` 自己规定的发布门禁形式
（`--strict`）对安装器生成的环境**仍然拒绝**。建议把密钥生成改为 Fernet 形式
（等价于 `base64.urlsafe_b64encode(os.urandom(32))`）一并收口，否则安装器产出的环境永远过不了自家门禁。


---

### 2.11 **P1 新发现 OPS-12（第 2 轮）：`.env` 带 UTF-8 BOM 时，预检 fail-open、compose 直接判项目无效**

该缺陷在第 2 轮复核时意外暴露：复核方用 PowerShell `Set-Content -Encoding utf8` 生成环境文件后，
预检报出 `environment : development`，而文件里明明写着 `EUROGAS_NEXUS_ENV=release`。定位结果：

```powershell
$bytes = [System.IO.File]::ReadAllBytes($f)
first 6 bytes: EF BB BF 45 55 52          ← UTF-8 BOM
BOM present: True
```

`check_config.py` 的 `load_env_file()` 用 `path.read_text(encoding="utf-8")` 读取，**不剥离 BOM**；
首行的键因此变成 `\ufeffEUROGAS_NEXUS_ENV`。而 `_check_unknown_variables()` 只报告以
`EUROGAS_NEXUS_` / `EUROGAS_` 开头的名字——带 BOM 的名字**两个前缀都不匹配**，于是既不被识别、
也不被报为未知变量，**被彻底静默丢弃**。

> 这正好违背该函数自己写明的设计目标（`check_config.py:36-38`）：
> "Anything else is refused, because silently ignoring a line would report a clean preflight
> for a deployment that never received the setting."——BOM 让这句话失效。

#### 影响 1：预检 fail-open（生产防护整体失效）

构造 BOM 文件，首行即 `EUROGAS_NEXUS_ENV=release`，同时故意带上 `ALLOW_ANONYMOUS_CALLERS=1`、
`DB_ECHO=true`、且**不给** `RUNTIME_STORE_DATABASE_URL`。同一份内容做有/无 BOM 对照：

| 版本 | 预检判定 | 退出码 |
| --- | --- | --- |
| **无 BOM（对照）** | environment=release；`missing_required` RUNTIME_STORE_DATABASE_URL + 2 条 `dev_setting_in_production` + `proxy_hop_not_trusted` | **EXIT=1**（3 error / 1 warning） |
| **有 BOM** | environment=**development**；只剩 1 条 `dev_origin_not_declared` 警告 | **EXIT=0**（"No errors, 1 warning"） |

```
--- WITH BOM (first line is the assignment) ---
Eurogas Nexus configuration preflight
  environment : development
  api profile : development

WARN  [dev_origin_not_declared] EUROGAS_NEXUS_CORS_ORIGINS: a development profile is served ...

No errors, 1 warning(s).
EXIT=0
```

`_is_production()` 依赖 environment 与 api_profile 两者；首行被吃掉后两者都退化为 `development`，
于是**生产开关检查、代理跳数检查、远程库必填检查全部跳过**。一个 release 形态、允许匿名调用、
开着 SQL 回显、且没有数据库的部署，拿到了干净的预检结论。

#### 影响 2：`docker compose --env-file` 同样失败，且是硬失败

同一份带 BOM 的 `.env` 交给 compose：

```powershell
docker compose --env-file .dnx-out/ops-review/env/12_installer_container_env_fixed.env -f deploy/runtime/compose.yaml config
```
```
level=warning msg="The \"EUROGAS_NEXUS_API_IMAGE\" variable is not set. Defaulting to a blank string."   (×9)
service "config-check" has neither an image nor a build context specified: invalid compose project
compose EXIT=1
```

而安装器写出的 `.env` **第一行正是** `EUROGAS_NEXUS_API_IMAGE=$ApiImage`：

```
line 345: [IO.File]::WriteAllLines($EnvironmentFile, $lines, [Text.UTF8Encoding]::new($false))   ← 无 BOM，安装器本身是干净的
$lines = @(
    "EUROGAS_NEXUS_API_IMAGE=$ApiImage"      ← 首行
    "EUROGAS_NEXUS_VERSION=$PackageVersion"
```

**责任界定（避免过度归因）**：安装器自身用 `UTF8Encoding($false)` 写入，**不带 BOM**，因此这不是安装器的缺陷。
风险来自"人工编辑后重新保存"这一常规运维动作：Windows 上若干编辑器（Notepad 的"UTF-8"、部分 Excel/记事本另存、
某些 CI 模板渲染）会写入 BOM。一旦发生，`docker compose up` 会以 `invalid compose project` 失败，
错误信息完全指不到真正原因（运维看到的是"没有指定镜像"，而 `.env` 里镜像明明写着）。

#### 修复建议

| 层面 | 建议 |
| --- | --- |
| `load_env_file()` | 读取时用 `encoding="utf-8-sig"`（或显式 `lstrip("\ufeff")`）；并把"键名以 `\ufeff` 开头"作为显式错误报出，而不是静默丢弃 |
| compose 路径 | 安装器/文档提示 `.env` 必须为无 BOM UTF-8；或在 `Deploy-EurogasNexus.ps1` 启动前做一次 BOM 探测并自动剥离 |
| 回归测试 | 增加"首行为赋值且文件带 BOM"的用例；现有用例全部使用无 BOM 文件，因此从未覆盖 |

---

## 3. 迁移运维实测

### 3.1 `migration_preflight.py` 无库 → **fail-closed，EXIT 1** ✅

```powershell
$env:RUNTIME_STORE_DATABASE_URL=""
& $py scripts/ops/migration_preflight.py
```
```
source migration head: 0039_identity_api_key_hash_width
database URL present: False
database URL: not configured
connectivity: failed
current revision: unavailable
missing tables: 0
recent backup: not checked
warning: RUNTIME_STORE_DATABASE_URL is not configured.
EXIT=1
```

### 3.2 `migration_preflight.py` 活库 → **EXIT 0，且 DSN 已脱敏** ✅

```powershell
$env:RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_verify"
& $py scripts/ops/migration_preflight.py
```
```
source migration head: 0039_identity_api_key_hash_width
database URL present: True
database URL: postgresql+pg8000://nexus:***@127.0.0.1:51356/nexus_verify     ← 口令已脱敏
connectivity: ok
current revision: 0039_identity_api_key_hash_width
missing tables: 0
EXIT=0
```

### 3.3 活库 `alembic current` / `heads` ✅

```powershell
$env:RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_verify"
& .dnx-deps\bin\alembic.exe current
& .dnx-deps\bin\alembic.exe heads
```
```
0039_identity_api_key_hash_width (head)
0039_identity_api_key_hash_width (head)
```

### 3.4 空库全链迁移（演练用库 `nexus_ops_migdrill`）✅

```powershell
createdb -h 127.0.0.1 -p 51356 -U nexus nexus_ops_migdrill
& .dnx-deps\bin\alembic.exe upgrade head
```
39 个 revision 全部 `Running upgrade ...` 成功，无 ERROR；末态：

```
0039_identity_api_key_hash_width (head)
key_hash | character varying | 80   ← 0039 已生效
```

### 3.5 **0039 downgrade 保护：存在超长值时真的拒绝** ✅（本次验收最重要的一条正面证据）

在 `nexus_ops_migdrill` 造一条 69 字符的 keyed digest（`hash_key_secret()` 在配置了
`EUROGAS_NEXUS_SECRET_KEY` 时的真实输出长度：`"hmac:" + sha256_hex`）：

```sql
INSERT INTO identity_api_keys (key_id, principal_id, key_hash, key_prefix, display_name, created_at_utc, is_bootstrap)
VALUES ('ops-review-key-0000000000000001','ops-review-principal','hmac:'||repeat('a',64),'ops-rv','ops acceptance long digest',now(),false);

SELECT key_id, char_length(key_hash) FROM identity_api_keys;
    ops-review-key-0000000000000001 | 69
```

```powershell
& .dnx-deps\bin\alembic.exe downgrade -1
```
```
INFO  [alembic.runtime.migration] Running downgrade 0039_identity_api_key_hash_width -> 0038_contract_payment_terms, ...
File "...\alembic\versions\0039_identity_api_key_hash_width.py", line 84, in downgrade
    raise RuntimeError(
RuntimeError: refusing to narrow identity_api_keys.key_hash: 1 row(s) hold a keyed digest longer than 64 characters and would be invalidated. Revoke and re-mint those API keys first, or keep this revision applied.
EXIT=1

--- 拒绝之后的状态 ---
SELECT version_num FROM alembic_version;                  → 0039_identity_api_key_hash_width
SELECT character_maximum_length ... key_hash;             → 80
```

**拒绝是干净的**：退出码 1、错误信息给出可执行补救（先吊销并重签 key）、事务回滚后版本与列宽都未被改动。

### 3.6 干净 downgrade → 成功并回到 64；再 upgrade → 80 ✅

```
DELETE FROM identity_api_keys WHERE key_id='ops-review-key-0000000000000001';   → DELETE 1
alembic downgrade -1   → Running downgrade 0039 -> 0038 ...   EXIT=0
    version_num = 0038_contract_payment_terms ; key_hash_width = 64
alembic upgrade head   → Running upgrade 0038 -> 0039 ...     EXIT=0
    version_num = 0039_identity_api_key_hash_width ; key_hash_width = 80
```

> **未对 `nexus_browser` 执行任何 downgrade**（那是其他团队在用的活数据）。全部降级实验只在
> `.dnx-out` 下自建的 `nexus_ops_migdrill` 上进行。

---

## 4. 备份 / 恢复实测

### 4.1 `backup_runtime.py` 依赖外部 `pg_dump`（OPS-07）

```powershell
$env:RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_browser"
& $py scripts/ops/backup_runtime.py .dnx-out\ops-review\backups      # PATH 中无 pg_dump
```
```
Running: pg_dump --format=custom --no-owner --host=127.0.0.1 --port=51356 --username=nexus --file=... nexus_browser
FileNotFoundError: [WinError 2] 系统找不到指定的文件。
EXIT=1     ← 未捕获的 Python 栈回溯，而不是脚本自己设计的 "pg_dump failed with exit code N"
```

**静态核实**：`deploy/runtime/Dockerfile.api` 只做 `pip install`，没有 `apt-get install postgresql-client`；
`deploy/runtime/compose.yaml` 里没有任何 backup 服务（检索 `backup|pg_dump|cron` 命中 0 行）。
**即：交付的 API 镜像内没有 `pg_dump`/`pg_restore`，交付的栈也没有备份入口。**

### 4.2 真实备份（把内嵌 PostgreSQL 16.2 的 bin 加进 PATH）✅

```powershell
$env:PATH="<root>\.dnx-pg\pgserver\pginstall\bin;$env:PATH"     # pg_dump 16.2
& $py scripts/ops/backup_runtime.py .dnx-out\ops-review\backups
```
```
Running: pg_dump --format=custom --no-owner --host=127.0.0.1 --port=51356 --username=nexus --file=...\nexus-runtime-20261007T021944Z.dump nexus_browser
Backup written: ...\nexus-runtime-20261007T021944Z.dump
Restore (see docs/operations/BACKUP_RESTORE.md): pg_restore --clean --if-exists --dbname=<target> nexus-runtime-20261007T021944Z.dump
EXIT=0

dump 大小 = 319490 bytes ；pg_restore --list 条目 = 440 行（含 88 个 TABLE DATA）
```

附带发现（OPS-09）：`pg_dump_args()` **完全丢弃 DSN 中的口令**，仅透传 `--username`，靠环境里的
`PGPASSWORD`/`.pgpass` 或服务端 trust 认证。本次不带 `PGPASSWORD` 也成功（该内嵌实例对本地 TCP 为 trust），
换成 compose 里的 `postgres:16-alpine`（强制 scram-sha-256）时会失败。

### 4.3 真实恢复 + 数据一致性比对 ✅

```powershell
dropdb --if-exists nexus_ops_restore ; createdb nexus_ops_restore
pg_restore --no-owner -h 127.0.0.1 -p 51356 -U nexus --dbname=nexus_ops_restore <dump>
psql -d <db> -tAc "SELECT '<table>' , count(*) FROM <table> UNION ALL ..."
```
```
pg_restore EXIT=0

--- SOURCE (nexus_browser) ---      --- RESTORED (nexus_ops_restore) ---
alembic_version|1                   alembic_version|1
audit_events|202                    audit_events|202
identity_principals|1               identity_principals|1
ingestion_runs|4                    ingestion_runs|4
market_observations|2382            market_observations|2382
observation_temporal_metadata|0     observation_temporal_metadata|0
source_runtime_states|0             source_runtime_states|0

restored revision = 0039_identity_api_key_hash_width
```

**结论：备份文件真实可恢复，逐表行数完全一致，版本一致。** 转储文件保存在
`.dnx-out/ops-review/backups/`（319,490 B）。

### 4.4 ~~**P0 发现 OPS-02：`backup_restore_drill.py` 按原样跑不通（两个独立缺陷）**~~ → **已修复，复核通过** ✅

> **第 2 轮状态：两处缺陷均已修复，复核方在修复后重跑并取得 `ok=true`（见 §4.5）。**
> 下面 §4.4.1 / §4.4.2 保留第 1 轮的原始观察与归因过程：其中缺陷 A 双方一致；
> 缺陷 B 复核方观察到 25001、供应商无法复现，第 2 轮已把触发条件定位清楚，**双方结论并不矛盾**（§4.4.2）。

#### 4.4.1 缺陷 A：子进程环境被整体替换，丢掉 `PATH`（双方确认）

```python
# scripts/ops/backup_restore_drill.py（修复前）:164-169
dump = subprocess.run(dump_command, env=_pg_env(source_url), capture_output=True, text=True)
#                      ^^^^^^^^^^^^^^^^^^^^^^ _pg_env 只返回 {"PGPASSWORD": ...}
```

原样执行：

```powershell
$env:PATH="<pgbin>;$env:PATH"
& $py scripts/ops/backup_restore_drill.py --target-database-url postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_ops_drill_restore
```
```json
{ "detail": "could not find a \"pg_dump\" to execute\npg_dump: error: \n",
  "error": "pg_dump_failed", "ok": false }
EXIT=1
```

最小化复现（`.dnx-out/ops-review/diag_env.py`）：

```
--- A: env REPLACED with {'PGPASSWORD': ...} (what the drill does) ---
returncode: 0
stdout: 'pg_dump (PostgreSQL) 16.2\n'
stderr: 'could not find a "pg_dump" to execute\n'      ← 子进程环境里没有 PATH

--- B: env MERGED with os.environ (the correct form) ---
returncode: 0
stderr: ''                                             ← 干净

--- C: env REPLACED, absolute path to pg_dump ---
raised: FileNotFoundError [WinError 2]                 ← 连进程都创建不了（SystemRoot 等被剥离）
```

**同一缺陷的两种表现（双方观察合并）**：复核方在子进程能被创建的情形下看到 stderr
`could not find a "pg_dump" to execute`；供应商在另一路径下直接得到 `FileNotFoundError [WinError 2]`。
两者同源——替换环境同时剥掉了 `PATH` 与 `SystemRoot`，具体报哪种取决于可执行文件能否被定位到。
另据供应商说明，该文件修复前**没有 `import os`**，因此修复 `_pg_env` 必须同时补上该 import（已补）。

#### 4.4.2 缺陷 B：`CREATE DATABASE` 触发 25001 —— 触发条件已定位

```python
# scripts/ops/backup_restore_drill.py（修复前）:101-104
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
    connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
```

复核方第 1 轮观察到 SQLSTATE `25001 CREATE DATABASE cannot run inside a transaction block`；
供应商在同一环境（SQLAlchemy 2.0.52 / pg8000 1.31.5）用**直接探针**无法复现，三种写法全部成功。
第 2 轮复核方做了变量隔离实验（`.dnx-out/ops-review/diag_25001.py`、`diag_25001_v6.py`），结论如下：

| 变体 | 写法 | 结果 |
| --- | --- | --- |
| **V1** | **旧代码原样**：同一 engine 先跑存在性 `SELECT`，再 `engine.connect().execution_options(AUTOCOMMIT)` 建库 | ❌ **25001 FAIL**（复核方观察复现） |
| **V2** | 同样的 per-connection 写法，但 engine **从未被使用过** | ✅ OK |
| **V3** | engine 级 `execution_options(isolation_level="AUTOCOMMIT")`（即采用的修复） | ✅ OK |
| V4 | 普通 `engine.connect()`，不设 isolation | ❌ 25001 FAIL |
| V5 | 探针与 CREATE 在同一连接上，isolation 事后施加 | ❌ `InvalidRequestError`（事务已初始化，不允许改 isolation） |
| **V6** | per-connection 写法不变，但存在性探针改到**另一个 engine** 上执行 | ✅ OK |

```
V1 old code: probe, pool reuse, per-connection AUTOCOMMIT        FAIL ProgrammingError ... 'C': '25001'
V2 per-connection AUTOCOMMIT, engine never used before           OK
V3 engine-level AUTOCOMMIT (the fix)                             OK
V4 plain connect(), no isolation                                 FAIL ProgrammingError ... 'C': '25001'
V5 probe + CREATE on same connection, AUTOCOMMIT applied late    FAIL InvalidRequestError ...
V6 probe on a SEPARATE engine, rest identical                    OK
```

**触发条件 = "该 Engine 已经被存在性探针用过"**，而不是 `execution_options` 这个写法本身。

- 供应商的直接探针是 **V2 形态**（一次性、engine 从未使用），所以通过；
- 复核方跑的是 **V1 形态**（`create_database_if_missing` 里先 `SELECT 1 FROM pg_database` 再用同一 engine 建库），所以失败。

**因此复核方第 1 轮的观察成立且可复现；双方的分歧来自探针构造不同，不涉及谁算错。**
采纳的修复（新建独立 `ddl_engine` 并把 isolation 声明在 engine 上）同时在 V1 与 V6 两种情形下正确，
因为它既换了 engine（消除"已被用过"这一前提），又把隔离级别声明在连接建立时——歧义被彻底消除：

```python
# 修复后（scripts/ops/backup_restore_drill.py:115-131）
ddl_engine = get_engine(maintenance_dsn).execution_options(isolation_level="AUTOCOMMIT")
try:
    with ddl_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
finally:
    ddl_engine.dispose()
```

#### 4.4.3 第 1 轮的失败样本（保留作为回归基线）

只修正缺陷 A（monkeypatch `_pg_env` 为合并环境，其余代码不动，见 `run_drill_patched.py`），目标库**不存在**时：

```json
{ "detail": "(pg8000.dbapi.ProgrammingError) {'S': 'ERROR', 'V': 'ERROR', 'C': '25001',
  'M': 'CREATE DATABASE cannot run inside a transaction block', ...}",
  "error": "ProgrammingError", "ok": false }
EXIT=1
```

> 文档示例给出的目标库名正是"尚不存在"的库（`nexus_restore_drill`），也就是**文档示例的调用方式在第 1 轮必然失败**。

**修正两处后（第 1 轮的手工验证）**，演练核心链路确实能跑通 —— 这当时就说明缺陷是局部的、机制本身没问题：

```powershell
createdb nexus_ops_drill_restore
& $py run_drill_patched.py postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_ops_drill_restore
```
```json
{ "api_smoke_status": 200, "audit_events_rows": 202, "database_created": false,
  "dump_bytes": 319490, "elapsed_seconds": 8.405, "identity_principals_rows": 1,
  "ingestion_runs_rows": 4, "missing_tables": [], "ok": true,
  "revision": "0039_identity_api_key_hash_width", "source_runtime_states_rows": 0 }
EXIT=0
```

即：**转储 → 建库 → 恢复 → 版本/必需表/业务行校验 → API 冒烟**这一整条链路是好的，
坏的只是"建库那一行"和"子进程环境那一行"。

#### 环境附加限制（OPS-10，非产品缺陷但影响运维）

`backup_restore_drill.py` 用 `tempfile.TemporaryDirectory()` 且**没有 `--work-dir` 选项**。本机上
`pg_dump.exe` 无法写入 `C:\Users\qqshu\AppData\Local\Temp`：

```
PS 写入 system Temp: OK
pg_dump --file into system Temp → pg_dump: error: could not open output file
   "C:\Users\qqshu\AppData\Local\Temp\nexus-probe3.dump": Permission denied     EXIT=1
pg_dump --file into <repo>\.dnx-out\... → EXIT=0
```

在受限主机上，运维只能靠改 `TEMP`/`TMP` 环境变量绕开，而脚本给出的错误信息
（`pg_dump_failed` + 被截断的 400 字节 stderr）不足以定位。

> **第 2 轮补充（供应商复核意见一致）**：该现象是**本机沙箱对临时目录的限制，不是产品缺陷**。
> 供应商在修复后跑通演练时也遇到同一现象——本机 `%TEMP%` 下 `pg_dump` 报 `Permission denied`，
> 把 `TEMP`/`TMP` 指到工作区即可。**结论不变**：值得写进交付文档，因为运维在受限环境下会遇到同样的现象，
> 而脚本没有 `--work-dir` 选项、错误信息也不指向临时目录权限。

---

### 4.5 OPS-02 修复后的端到端复核（第 2 轮）✅

复核方**不采信"已修复"结论**，直接把交付的 `backup_restore_drill.py`（未做任何 monkeypatch）
在目标库**不存在**的条件下重跑，以真实走到 `CREATE DATABASE` 分支：

```powershell
dropdb --if-exists nexus_ops_drill_fixed          # 确保 database_created 必须为 true
$env:TEMP = "<repo>\.dnx-out\ops-review\tmp"; $env:TMP = $env:TEMP
& $py scripts/ops/backup_restore_drill.py --target-database-url postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_ops_drill_fixed
```
```json
{
  "api_smoke_status": 200,
  "audit_events_rows": 240,
  "database_created": true,
  "dump_bytes": 328675,
  "elapsed_seconds": 3.004,
  "identity_principals_rows": 1,
  "ingestion_runs_rows": 4,
  "missing_tables": [],
  "ok": true,
  "revision": "0039_identity_api_key_hash_width",
  "source": "postgresql+pg8000://nexus:***@127.0.0.1:51356/nexus_browser",
  "source_runtime_states_rows": 0,
  "target": "postgresql+pg8000://nexus:***@127.0.0.1:51356/nexus_ops_drill_fixed"
}
EXIT=0
```

**复核判定：OPS-02 阻断解除。** 关键判据是 `database_created: true` —— 建库分支被真实执行并通过，
说明缺陷 B 的修复有效（若仅有缺陷 A 被修，此处必然仍是 25001）。

> **遗留说明**：`--keep-dump` 会把转储写到仓库根的 `backups/` 目录（脚本内写死为 `ROOT / "backups"`），
> 与 `backup_runtime.py` 的"输出目录由参数决定"不一致；本次复核因此未加该参数，避免在仓库内留下产物。
> 属于 OPS-10 同一类的可用性小缺口。

---

## 5. 部署栈实测（含阻塞点）

### 5.1 静态渲染通过 ✅

```powershell
docker compose --env-file .dnx-out/ops-review/compose.env -f deploy/runtime/compose.yaml config
→ EXIT=0
```

核对结论（`deploy/runtime/compose.yaml`）：

| 检查点 | 实测 |
| --- | --- |
| 服务顺序 | `postgres(healthy)` → `config-check(completed)` → `migrate(completed)` → `api` ✅ |
| postgres 健康检查 | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`，5s/20 次/10s 起窗 ✅ |
| api 健康检查 | Python 内联脚本请求 `/api/health/ready`，令牌从容器自身环境读取（不进 `docker inspect`）✅ |
| gateway 健康检查 | `wget --no-check-certificate --spider https://127.0.0.1/api/health`，`profiles: ["server"]` ✅ |
| 卷 | `runtime-postgres` 具名卷 → `/var/lib/postgresql/data` ✅ |
| 网络 | 单一 `default` 网络；postgres/api 端口都绑 `127.0.0.1` ✅ |
| 可选组件 | `public-ingestion` / `preview-seed` / `simulated-prices` / `monitoring` 均为 profile 隔离 ✅ |

### 5.2 **阻塞点：镜像拉不到，栈无法端到端启动** ❌（无法实测，见 §10）

```powershell
curl.exe -sS -o NUL -w "http_code=%{http_code} time=%{time_total}" --max-time 25 https://registry-1.docker.io/v2/
→ curl: (28) Failed to connect to registry-1.docker.io:443 after 21270 ms
   http_code=000 time=21.270720        EXIT=28

curl.exe ... https://auth.docker.io/token
→ curl: (28) Failed to connect to auth.docker.io:443 after 21275 ms     EXIT=28

docker version --format '{{.Server.Version}}'   → 29.8.1        （Docker Desktop 正常）
docker images                                    → 本地无任何镜像缓存
```

```powershell
docker compose --env-file .dnx-out/ops-review/compose.env -f deploy/runtime/compose.yaml pull
```
```
 Image postgres:16-alpine Error failed to resolve reference "docker.io/library/postgres:16-alpine":
   Head "https://registry-1.docker.io/v2/library/postgres/manifests/16-alpine":
   dialing registry-1.docker.io:443 container via direct connection because Docker Desktop has no HTTPS proxy:
   dial tcp [2a03:2880:f130:83:face:b00c:0:25de]:443: connectex: A connection attempt failed ...
 Image registry.example.com/eurogas-nexus-api@sha256:0000... Interrupted
Error response from daemon: failed to resolve reference "docker.io/library/postgres:16-alpine": ...
compose pull EXIT=1
```

**需要什么条件才能实测**：① 到 `registry-1.docker.io` 与目标私有仓库的网络出口（或 Docker Desktop 的 HTTPS 代理）；
或 ② 供应商提供 `docker save` 出的离线镜像 tar（`postgres:16-alpine`、`caddy:2-alpine`、
`python:3.11-slim` 构建基础镜像、API 镜像）以及可用的 digest 清单。

---

## 6. 升级 / 回滚

### 6.1 镜像是否固定 digest → **compose 自身不固定**（OPS-03）

| 镜像 | compose 中的写法 | 是否不可变 |
| --- | --- | --- |
| API | `image: ${EUROGAS_NEXUS_API_IMAGE}` | 取决于运维填什么，**compose 不校验** |
| PostgreSQL | `postgres:16-alpine` | ❌ 可变 tag |
| Caddy | `caddy:2-alpine` | ❌ 可变 tag |

而"填什么"没有任何门禁兜底：

```powershell
# 把 API 镜像改成 :latest
& $py scripts/ops/check_config.py --env-file .dnx-out/ops-review/env/09_image_latest_tag.env
```
```
Eurogas Nexus configuration preflight
  environment : release
  api profile : release

No findings.

No errors, 0 warning(s).
EXIT=0          ← :latest 完全放行
```

原因：`preflight.py:584` 明确把 `EUROGAS_NEXUS_API_IMAGE` 排除在 `external_variable_unset` 检查之外，
且**没有任何检查校验镜像引用形态**。

#### 判断：这是**缺口**，不是有意设计；但修复应当是"警告"而非"错误"

供应商问：`check_config.py` 对 `:latest` 放行是有意设计还是缺口？复核方判断为**缺口**，依据四点：

1. **契约本身已声明意图，只是没人执行**。`env.server.example:254-259`（由 `config_contract.py` 生成）
   对 `EUROGAS_NEXUS_API_IMAGE` 写着 "Required when: deploying with deploy/runtime/compose.yaml"
   与 "Pin by digest rather than tag so a rollback names an immutable image"。要求写在模板注释里，
   compose 路径上却没有任何一处校验它。
2. **`preflight.py:576-582` 的排除理由不覆盖"形态"**。原注释只论证了"未设置 ≠ 未配置，
   因为 compose 会在运行时替换"，这是**不报告缺失**的理由，而不是**跳过形态校验**的理由。
   两者被同一行 `reported_elsewhere` 一起排除了，属于顺手扩大范围。
3. **与产品其余部分的姿态不一致**。发布链路处处强制 digest：`promote_image.py:460` 显式
   `refusing to promote the mutable 'latest' tag`；`package_deployment_bundle.py:336` 要求
   `sha256:<64 hex>`；`Deploy-EurogasNexus.ps1` 用正则校验 `repository@sha256:<64hex>`（§6.2 五例全过）。
   唯独运维手写 `.env` 这条路完全裸奔，而 README-EN.md 又把这条路描述为等价用法。
4. **但不能设成 error**。`check_config.py` 同时在 development 档位使用，可变 tag 在 dev/test 是合理的；
   而且交付的 `compose.yaml` 自己就把 `postgres:16-alpine`、`caddy:2-alpine` 写成可变 tag，
   对 API 镜像设 error 会与交付文件自相矛盾，也会让本地开发无法通过预检。

**建议实现（与供应商倾向一致）**：

- 新增一条 **warning** 级检查：在生产档位（复用 `_is_production()`）下，若 `EUROGAS_NEXUS_API_IMAGE`
  非空且**不匹配 `@sha256:[0-9a-f]{64}$`**，报 `api_image_not_pinned_by_digest`（warning）。
  这样 `--strict` 自然把它提升为发布门禁的 error，与既有严重度语义完全吻合，无需新机制。
- 是否单独把 `:latest` 提为 error，复核方**不建议**：理由见上，且 `--strict` 已经足够。
- **注意这条警告覆盖不到 OPS-03 的另一半**：`postgres:16-alpine` / `caddy:2-alpine` 写死在 `compose.yaml` 里，
  `check_config.py` 是环境变量检查器、读不到它们。这半边必须在 **compose 文件本身**改为 `@sha256:`
  形式（或由一个 compose 静态检查承担），否则 OPS-03 只解决了一半。
- 顺带建议在文档里点明"安装器路径（release-identity 强校验）"与"裸 compose 路径（无校验）"的差异——
  两条路并存且无人说明，是本缺口真正的运维风险来源。

### 6.2 发布/安装侧对 digest 的校验是严格的 ✅（正面对冲）

从 `Deploy-EurogasNexus.ps1` 中**只抽取**三个纯校验函数（AST 取函数体，不 dot-source 整个安装器，
避免执行安装动作），逐个喂入构造的 `release-identity.json`
（脚本 `.dnx-out/ops-review/test_release_identity.ps1`）：

```
extracted functions: Assert-IdentityText, Assert-IdentityImageRepository, Read-BundleReleaseIdentity
A_pinned_digest_good         expected=ACCEPT [AS EXPECTED]  ACCEPT -> api_image=registry.example.com/eurogas-nexus-api@sha256:aaaa...
B_mutable_latest_tag         expected=REFUSE [AS EXPECTED]  REFUSE -> api_image_reference does not match ^[^@\s]+@sha256:[0-9a-f]{64}$
C_reference_digest_mismatch  expected=REFUSE [AS EXPECTED]  REFUSE -> api_image_reference does not match repository and digest.
D_short_digest               expected=REFUSE [AS EXPECTED]  REFUSE -> api_image_digest does not match ^sha256:[0-9a-f]{64}$
E_repository_carries_tag     expected=REFUSE [AS EXPECTED]  REFUSE -> api_image_repository must end with a repository name and must not carry a tag on its final path component.
```

**结论**：走"发布身份文件 → 安装器"这条路时 digest 强制；走"手写 .env → docker compose up"这条路时**没有任何强制**。
两条路并存且没有文档说明差异，是 OPS-03 的实质。

### 6.3 回滚路径是否文档化 → **是，且引用物全部存在** ✅

`docs/operations/RELEASE_ROLLBACK.md`（55 行）给出：回滚前 `compatibility_check.py` +
`migration_preflight.py --json` + 对只读副本跑 `smoke_release.py`；回滚步骤 6 步；破坏性迁移的回滚改为
"恢复备份 → 隔离库验证 → 切换"；并明确列出不安全动作（禁止无验证的 `alembic downgrade`）。

逐项核实引用物是否真实存在：

```
docs\operations\RELEASE_ROLLBACK.md          PRESENT
docs\operations\BACKUP_RESTORE.md            PRESENT
docs\operations\DISASTER_RECOVERY.md         PRESENT
docs\operations\INCIDENT_RESPONSE.md         PRESENT
scripts\release\compatibility_check.py       PRESENT
scripts\release\smoke_release.py             PRESENT
scripts\ops\migration_preflight.py           PRESENT
```

⚠️ 第 1 轮曾发现：回滚文档第 47 行推荐的恢复手段正是 `backup_restore_drill.py`，而该脚本当时按原样跑不通（OPS-02），
**回滚剧本的最后一环不可执行**。第 2 轮复核后**该缺口已闭合**：脚本可无人干预跑完
`database_created: true / ok: true / api_smoke 200`（§4.5），回滚剧本引用的三个脚本
（`compatibility_check.py`、`migration_preflight.py`、`backup_restore_drill.py`）现在都经实测可用。

> 仍需注意运行前置条件：目标机上 `pg_dump`/`pg_restore` 必须在 `PATH` 上（交付镜像内没有，OPS-04），
> 且进程的 `TEMP`/`TMP` 必须指向可写目录（OPS-10）。这两条建议写进回滚剧本的执行前提。

---

## 7. 可观测性与敏感值

### 7.1 起一次真实 API 并用 canary 值扫描日志 ✅

```powershell
$env:EUROGAS_NEXUS_ENV="release" ; $env:EUROGAS_NEXUS_API_PROFILE="release"
$env:EUROGAS_NEXUS_PUBLIC_API_TOKEN="leakcanary-token-8f2c41ab9e5d"
$env:EUROGAS_NEXUS_INTERNAL_API_TOKEN="leakcanary-internal-4a7b2c9d1e6f"
$env:EUROGAS_NEXUS_SECRET_KEY=<$py -c "base64.urlsafe_b64encode(...)">     # canary 前缀 LEAKCANARY-KEY-
$env:RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_ops_restore"
& $py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 58123 --log-level info *> .dnx-out\ops-review\api-canary.log
```

请求覆盖 8 类：`/api/health/live`(200)、`/api/health/ready`(200)、`/api/runtime/metrics`(200)、
`/api/market/observations`(200)、`/api/market/quotes`(200)、无令牌(401)、错误令牌(403)、未知路径(404)。

日志扫描（`.dnx-out/ops-review/api-canary.log`，19 行）：

```
canary 'leakcanary-token-8f2c41ab9e5d'    -> 1 hit(s)     ← 见 7.2
canary 'leakcanary-internal-4a7b2c9d1e6f' -> 0 hit(s)     ✅
canary 'LEAKCANARY-KEY-'                  -> 0 hit(s)     ✅
canary 'wrong-token-canary-0001'          -> 0 hit(s)     ✅
canary '33.6823'  (行情价)                 -> 0 hit(s)     ✅
canary '33.682'   (行情价)                 -> 0 hit(s)     ✅
canary 'api_key='                         -> 1 hit(s)     ← 见 7.2
```

**结论**：走 header 的令牌、错误令牌、加密主密钥、以及响应体中返回的行情价，**都没有进入日志**。
错误响应也是结构化信封（含 `correlation_id`），无堆栈、无凭据：

```json
{"detail":{"error":"public_api_token_missing","message":"Public API token is required."},
 "error":"UNCLASSIFIED_ERROR","family":"SYSTEM","severity":"error","correlation_id":"54201287af7a4d40"}   → 401
{"detail":{"error":"public_api_token_invalid",...},"error":"public_api_token_invalid",
 "family":"VALIDATION","correlation_id":"78679f912c1c431f"}                                              → 403
```

健康就绪对象语义清晰：

```json
{"status":"ready","scope":"readiness","checks":{"runtime_db":"ok","required_tables":"ok"}}
```

### 7.2 **P1 发现 OPS-05：令牌可经查询串传入，并被 access log 明文记录**

```
--- token in QUERY STRING : http://127.0.0.1:58123/api/runtime/metrics?api_key=leakcanary-token-8f2c41ab9e5d
{"data":"# HELP eurogas_http_requests_total ..."}    http_code=200      ← 查询串令牌被接受
```

uvicorn access log 原样记录请求行：

```
INFO:     127.0.0.1:62491 - "GET /api/runtime/metrics?api_key=leakcanary-token-8f2c41ab9e5d HTTP/1.1" 200 OK
```

**风险**：任何一次"图省事把令牌放 URL"的调用（curl 调试、SDK 误配、外部脚本）都会把可长期使用的部署令牌
写进应用日志、网关日志、以及任何经过的反向代理日志。仓库自己的 `docs/operations/API_KEYS.md:17` 也提醒
"use headers for ordinary requests to avoid putting secrets in URLs"——但服务端并未拒绝这种用法。
建议：查询串令牌要么直接拒绝，要么在 access log 层做 query 脱敏。

### 7.3 **P1 发现 OPS-06：metrics 存在非法样本值，Prometheus 抓取会失败**

```
# HELP eurogas_db_pool_checked_out Checked-out connections.
# TYPE eurogas_db_pool_checked_out gauge
eurogas_db_pool_checked_out <bound method QueuePool.checkedout of <sqlalchemy.pool.impl.QueuePool object at 0x00000240BD200C50>>
```

样本值不是数字，而是 Python 绑定方法的 `repr`（还带内存地址，每次进程重启都变）。
Prometheus 文本格式要求样本值为数值，该指标族会导致抓取器解析失败。同族的
`eurogas_db_pool_size 10`、`eurogas_db_pool_overflow 20` 正常，说明是单点疏漏（漏调用 `.checkedout()`）。

其余指标（HTTP 计数/错误/延迟、ingestion runs/failures、source 新鲜度等）形态正确。

### 7.4 进程级可观测性边界（需运维知悉）

`src/eurogas_nexus/api/middleware/observability.py` 是**进程内**计数（注释自述），
`http_metric_lines()` 只反映单个 worker；多副本部署时指标不能直接相加，也没有 `/metrics` 之外的聚合层。
此外 `/api/runtime/metrics` 需要部署令牌，抓取器要单独配置凭据。

---

## 8. 密钥管理

### 8.1 Secrets 落在哪里（静态核实 + 实证）

| 秘密 | 存放位置 | 保护 |
| --- | --- | --- |
| `POSTGRES_PASSWORD`、`EUROGAS_NEXUS_SECRET_KEY`、`EUROGAS_NEXUS_INTERNAL_API_TOKEN` | `<InstallRoot>\.env`（`Install-EurogasNexusServerRuntime.ps1:161, 323-339`） | `icacls /inheritance:r /grant:r "<user>:(R,W)" "SYSTEM:(F)" "Administrators:(F)"`（第 291-296 行），失败即 `throw` |
| TLS 私钥 | `<InstallRoot>\tls\server.key` | 目录级 `icacls /inheritance:r`，仅 SYSTEM/Administrators（第 309-310 行） |
| 供应商凭据（GIE 等） | 数据库 `provider_credentials`，用 `EUROGAS_NEXUS_SECRET_KEY` 加密，仅存 `redacted_preview` | `src/eurogas_nexus/security/credentials.py` |
| 身份 API key | 数据库 `identity_api_keys`，存 keyed digest（`hmac:`+sha256 = 69 字符，故 0039 把列宽加到 80） | 明文仅在创建/轮换时返回一次 |
| 运行期环境变量 | compose `x-runtime-environment` 注入容器 | api 健康检查刻意从容器自身环境读令牌，避免出现在 `docker inspect` |

生成方式：`New-HexSecret 32` 使用 `[Security.Cryptography.RandomNumberGenerator]`（CSPRNG，第 190-200 行），
**重装时若 `.env` 已存在则复用原值**（第 320-322 行），不会静默轮换——这一点对运维是好事。

### 8.2 轮换流程

| 对象 | 是否有轮换手段 | 证据 |
| --- | --- | --- |
| 身份 API key | ✅ `POST /api/internal/identities/{principal_id}/keys/{key_id}/rotate`（先吊销旧 key 再签发） | `api/routes/internal/identity_admin.py:176-227`；`POST .../keys/{key_id}/revoke`:228 |
| 供应商凭据 | ✅ `POST /api/credentials/{provider_id}/rotate` | `api/routes/public/credentials.py:115` |
| 会话 | ✅ 吊销会话 / 按主体吊销 | `api/routes/public/access.py:160,286` |
| **`EUROGAS_NEXUS_SECRET_KEY`** | ❌ 无流程。轮换会使已存凭据不可解密，必须"轮换后重新录入全部供应商凭据" | `deploy/runtime/env.server.example:103`；`docs/operations/LLM_MONITORING-EN.md:51` |
| **`EUROGAS_NEXUS_PUBLIC_API_TOKEN` / `..._INTERNAL_API_TOKEN`** | ❌ 无流程。只能手工改 `.env` 并重启；且脚本**不生成** public token（OPS-01） | 全仓库 `scripts/install/` 无 public token 引用 |

### 8.3 附带发现（OPS-11）

- 部署级令牌没有轮换剧本，也没有"轮换会影响哪些调用方"的清单。
- `EUROGAS_NEXUS_INTERNAL_API_TOKEN` 由安装器生成并写入 `.env`，但在 dev 之外的档位是否会随
  API 启动而重新加载、轮换后 worker 容器是否同步，均无文档。

---

## 9. 运维脚本可用性（`scripts/ops/`）

在自建副本库 `nexus_ops_restore` 上执行（**不触碰 `nexus_browser`**），原始输出见
`.dnx-out/ops-review/ops-scripts.txt`。

| 脚本 | 命令 | 结果 |
| --- | --- | --- |
| `validate_runtime_db.py` | 无参数 | ✅ EXIT 0；列出 92 张必需表、`Missing tables: none`、`Alembic revision: 0039_...`；DSN 已脱敏 |
| `prune_job_records.py` | `--retention-days 30` | ✅ EXIT 0；默认 dry-run：`Job prune dry-run: 0 rows deleted of 0 eligible`，并输出 `Oldest job still represented:` 与"被保留的活跃行"提示 |
| `prune_job_records.py` | `--retention-days 0` | ✅ EXIT 2；`Invalid retention policy: retention_days must be between 1 and 3650` |
| `prune_job_records.py` | 缺参数 | ✅ EXIT 2；argparse 明确报 `--retention-days` 必填 |
| `prune_audit_events.py` | 默认 | ✅ EXIT 0；dry-run：`Audit prune dry-run: 0 rows eligible (retention_days=365 ...)` |
| `prune_runtime_data.py` | `--dry-run` | ✅ EXIT 0；输出 JSON 计数 |
| `recover_stale_jobs.py` | 无参数 | ✅ EXIT 0；dry-run JSON：`{"status":"ok","committed":false,...}` |
| `prune_job_records.py` | 无 `RUNTIME_STORE_DATABASE_URL` | ✅ EXIT 2；`Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.` |
| `recover_stale_jobs.py` | 无 `RUNTIME_STORE_DATABASE_URL` | ✅ EXIT 2；`{"status":"blocked","reason":"database_url_missing"}` |

**评价**：破坏性脚本默认 dry-run、要求显式 `--commit`、保留期必须由运维给出且带上下界校验、
无库时全部 fail-closed 且退出码为 2。这一组是本次验收里质量最好的部分之一。

---

## 10. 无法实测项与所需条件（8 项）

| # | 项目 | 为何无法实测 | 需要什么条件 |
| --- | --- | --- | --- |
| N1 | `docker compose up` 端到端（config-check → migrate → api 真实过门、健康检查转 healthy） | 镜像拉不到：`curl registry-1.docker.io` 超时 `EXIT=28`；`docker compose pull` 报 `failed to resolve reference "docker.io/library/postgres:16-alpine"`；本地无镜像缓存 | 到 `registry-1.docker.io` 与私有仓库的网络出口/HTTPS 代理，**或**供应商提供离线镜像 tar（含 `postgres:16-alpine`、`caddy:2-alpine`、`python:3.11-slim`、API 镜像）与 digest 清单 |
| N2 | Caddy 网关 HTTPS 入口、TLS 证书装载、`profiles: ["server"]` 下的健康检查 | 依赖 N1 的 `caddy:2-alpine` | 同 N1；另需客户方的服务器证书与私钥（`server.crt`/`server.key`） |
| N3 | Windows 安装器全流程（`Deploy-EurogasNexus.ps1` → `Install-EurogasNexusServerRuntime.ps1`） | 需要管理员权限、Docker Hub 出口，且会真实改动主机（`.env`、ACL、TLS 目录、`ProgramData`），不适合在验收机上执行 | 一台可丢弃的 Windows 主机 + 管理员 + N1 的镜像条件；本次仅以 AST 抽取方式验证了其中的发布身份校验函数（§6.2） |
| N4 | 异地/外部备份介质与保留策略 | 仓库未提供任何对象存储/带库集成，compose 里也无 backup 服务 | 客户方指定备份目标（S3/文件服务器）与保留期；需供应商补 `pg_dump` 定时任务或 sidecar |
| N5 | Prometheus/Grafana 实际抓取与告警联通 | 本机无监控栈 | 客户方提供的 Prometheus/Grafana 实例；另需先修 OPS-06，否则该指标族会抓取失败 |
| N6 | 真实供应商凭据下的加密凭据读写（GIE 等） | 无可用的真实 `GIE_API_KEY`，且不应在验收机上使用真实凭据 | 客户方提供的测试用凭据 |
| N7 | 多副本/多节点下的指标聚合与负载均衡 | 单机单进程环境 | 目标生产拓扑或等价的本地编排 |
| N8 | 代码签名证书 / GPG 签名与校验流程 | 证书与私钥属于客户方资产，不在交付物内 | 客户方提供 Authenticode 证书与 GPG 私钥（`EUROGAS_NEXUS_SIGNTOOL_PATH`、`WINDOWS_SIGNING_CERT_PATH`、`EUROGAS_NEXUS_GPG_SIGNING_KEY_ID` 均为空占位） |

---

## 11. 运维接手结论

### 结论：**有条件接手（CONDITIONAL）** —— P0 已清零，条件全部收敛为 P1

第 2 轮复核后，**原 2 项 P0 已修复并验证通过**（OPS-01 → §2.10.2；OPS-02 → §4.5），
安装与灾备演练这两个最基本动作**已不再被阻断**。当前遗留的条件项全部是 P1：

| 编号 | 级别 | 缺陷 | 影响 | 状态 |
| --- | --- | --- | --- | --- |
| ~~OPS-01~~ | ~~P0~~ | 安装器 `.env` 缺 `EUROGAS_NEXUS_PUBLIC_API_TOKEN` | 栈起不来 | ✅ **已修复，复核通过**（§2.10.2）。残留：`--strict` 门禁仍因 `secret_key_not_fernet` 拒绝（§2.10.3） |
| ~~OPS-02~~ | ~~P0~~ | 演练脚本 `env=` 替换环境 + 建库 25001 | 灾备演练跑不通 | ✅ **已修复，复核通过**（§4.5，`database_created: true` / `ok: true`） |
| **OPS-12** | **P1** | `.env` 带 UTF-8 BOM 时预检 **fail-open**（生产防护整体跳过），且 compose 判 `invalid compose project` | 一个 release 形态、允许匿名调用、开着 SQL 回显且无数据库的部署可以拿到"干净"预检；BOM 若进入 compose 路径则**直接起不来** | 🔴 **新增，未修**（§2.11） |
| OPS-03 | P1 | compose 不固定 digest；预检对 `:latest` 零告警（**判定为缺口**，见 §6.1） | 无法保证两次部署是同一份制品；与发布链路的强 digest 姿态不一致 | 🟡 未修（另有 `postgres`/`caddy` 两行在 compose 文件内，预检覆盖不到） |
| OPS-04 | P1 | 交付镜像内无 `pg_dump`/`pg_restore`，栈内无备份服务 | 客户环境里做备份需运维自行准备客户端与外部调度 | 🟡 未修 |
| OPS-05 | P1 | 部署令牌可经 `?api_key=` 传入并被 access log 明文记录（§7.2） | 凭据进入应用/网关/代理日志 | 🟡 未修 |
| OPS-06 | P1 | `eurogas_db_pool_checked_out` 输出绑定方法 `repr`（§7.3） | Prometheus 抓取该指标族失败 | 🟡 未修 |

**接手前必须补齐（按建议顺序）**：OPS-12 → OPS-05 → OPS-06 → OPS-03 → OPS-04。
其中 **OPS-12 建议优先**：它是唯一一条既能让预检 fail-open、又能让栈硬起不来的缺陷，
且触发动作（在 Windows 上编辑并另存 `.env`）是运维日常动作。

其余可带缺陷接手、记入待办的项：

| 编号 | 级别 | 项 |
| --- | --- | --- |
| OPS-07 | P2 | `backup_runtime.py` 在缺 `pg_dump` 时抛未捕获栈回溯，而非设计好的退出码 1 |
| OPS-08 | P2 | warning 级问题（代理跳数未声明、开发档位未声明来源）不阻断栈启动，而 compose 的 `config-check` 未加 `--strict` → 线上可能带着"Cookie 不发 Secure"的风险跑起来。这是文档化的有意设计，但运维需明确知晓并写进发布检查表 |
| OPS-09 | P2 | `pg_dump_args()` 丢弃 DSN 口令，依赖环境 `PGPASSWORD`/`.pgpass` 或服务端 trust；在 compose 的 scram 认证下会失败 |
| OPS-10 | P2 | `backup_restore_drill.py` 无 `--work-dir`，且 `--keep-dump` 把产物写死在仓库根 `backups/`；受限主机上 Temp 不可写时报错不足以定位 |
| OPS-11 | P2 | 部署级令牌（public/internal）与 `EUROGAS_NEXUS_SECRET_KEY` 无轮换流程与影响清单 |

### 只能由供应商或客户方提供的项

| 项 | 责任方 | 说明 |
| --- | --- | --- |
| 真实镜像仓库访问权 / 离线镜像 tar + digest 清单 | **供应商** | 没有它，N1/N2/N3 三项端到端实测永远做不了（§5.2、§10） |
| OPS-12 / OPS-03 / OPS-04 / OPS-05 / OPS-06 的代码修复与复验证据 | **供应商** | 均是交付物内部缺陷，运维无法在不改代码的前提下绕过 |
| Windows Authenticode 证书与 GPG 私钥 | **客户方** | `EUROGAS_NEXUS_SIGNTOOL_PATH`、`WINDOWS_SIGNING_CERT_PATH`、`EUROGAS_NEXUS_GPG_SIGNING_KEY_ID` 在交付模板中均为空占位（§10 N8） |
| 服务器 TLS 证书/私钥 | **客户方** | Caddy 需要 `deploy/runtime/tls/server.{crt,key}`（§10 N2） |
| 备份目标介质（对象存储/文件服务器）与保留期策略 | **客户方** | 仓库未提供任何外部备份集成（§10 N4） |
| 生产监控平台（Prometheus/Grafana）与告警接收渠道 | **客户方** | 产品只暴露进程内指标端点（§7.4、§10 N5） |
| 真实数据源凭据（GIE 等） | **客户方** | 用于验证加密凭据读写（§10 N6） |
| 生产拓扑（多副本/负载均衡） | **客户方** | 用于验证指标聚合（§10 N7） |

### 接手后的第一批动作建议（按优先级）

1. **立即可做**：`backup_restore_drill.py` 已可无人干预跑通（§4.5），把它接进例行调度，
   作为"每日备份 + 每周恢复比对"的固定手段；只需保证进程的 `TEMP`/`TMP` 指向可写目录、且
   PostgreSQL 客户端工具在 `PATH` 上（镜像内没有，见 OPS-04）。
2. 在测试环境跑通一次完整 `docker compose up`（拿到镜像后），确认 §5.1 的依赖链在真实运行时成立；
   注意 `.env` 必须保存为**无 BOM** UTF-8，否则会撞上 OPS-12 的 `invalid compose project`。
3. 每次迁移前固定执行 `migration_preflight.py --json` 与 `alembic current`，把 §3.5 的 0039 拒绝行为
   写入变更评审清单（存在 `hmac:` 前缀 digest 时禁止降级）。
4. 把 §2 的 8 个配置场景整理成上线前的固定检查表；发布门禁一律使用 `--strict`。
   注意安装器当前产出的环境**过不了 `--strict`**（§2.10.3），需供应商先收口密钥生成。
5. 在监控接入前先记录 OPS-06，避免抓取器因非法样本值整族丢弃。
6. 把 OPS-12 的 BOM 探测加入自己的部署前脚本（一条 `Get-Content -Raw` 检查首字符即可），
   在供应商修复前作为运维侧兜底。

---

## 12. 证据清单

| 文件 | 内容 |
| --- | --- |
| `.dnx-out/ops-review/config-matrix.txt` | 8 个配置场景的完整命令与输出（§2） |
| `.dnx-out/ops-review/env/01..11_*.env` | 11 个场景环境文件，含安装器实测用的 `10_/11_` |
| `.dnx-out/ops-review/make_envs.py` | 场景环境文件的生成脚本 |
| `.dnx-out/ops-review/ops-scripts.txt` | 9 条运维脚本命令与输出（§9） |
| `.dnx-out/ops-review/backups/nexus-runtime-20261007T021944Z.dump` | 活库 `nexus_browser` 的真实备份，319,490 B（§4.2） |
| `.dnx-out/ops-review/manual-drill/runtime.dump` | 独立复现的转储，用于隔离 pg_dump 的 Temp 写入限制 |
| `.dnx-out/ops-review/diag_env.py` | 子进程环境替换缺陷的最小化复现（§4.4-A） |
| `.dnx-out/ops-review/run_drill_patched.py` | 仅修正 `_pg_env` 后的演练运行器（§4.4-B 归因） |
| `.dnx-out/ops-review/seed_long_key.sql` | 0039 downgrade 保护场景的数据构造（§3.5） |
| `.dnx-out/ops-review/test_release_identity.ps1` + `identity/A..E.json` | 发布身份 digest 校验的 5 个用例（§6.2） |
| `.dnx-out/ops-review/api-canary.log` | 带 canary 值的真实 API 日志（§7.1、§7.2） |
| `.dnx-out/ops-review/compose.env` | compose 静态渲染所用的运维环境 |

**第 2 轮（复核）新增证据**：

| 文件 | 内容 |
| --- | --- |
| `.dnx-out/ops-review/env/12_installer_container_env_fixed.env` | 修复后安装器环境 → 预检 `EXIT=0` 的复核输入（§2.10.2） |
| `.dnx-out/ops-review/env/13_bom_first_line_failopen.env` | 带 BOM、首行为赋值 → 预检 fail-open 的复现输入（§2.11） |
| `.dnx-out/ops-review/env/14_nobom_control.env` | 同上内容的无 BOM 对照组（§2.11） |
| `.dnx-out/ops-review/diag_25001.py` | 25001 触发条件的 6 变体隔离实验（§4.4.2） |
| `.dnx-out/ops-review/diag_25001_v6.py` | V1 / V6 对照，证明触发条件是"同一 engine 已被用过"（§4.4.2） |

**本次实测新增的数据库（均在本地内嵌实例内，未触碰 `nexus_browser` 之外任何既有库）**：

| 库 | 用途 | 处置 |
| --- | --- | --- |
| `nexus_ops_migdrill` | 空库全链迁移 + 0039 downgrade 保护实验 | 保留（末态 = head） |
| `nexus_ops_restore` | 备份恢复一致性比对的恢复目标 | 保留（`nexus_browser` 的完整副本） |
| `nexus_ops_drill_restore` | 第 1 轮演练的目标库（预建） | 保留（演练末态） |
| `nexus_ops_drill_fixed` | 第 2 轮复核：目标库**先删除**，验证 `database_created=true` | 保留（演练末态，证明建库分支通过） |

> 上述四库与全部证据目录都在 `.gitignore` 覆盖范围内（实证：`git check-ignore -v .dnx-out/ops-review/api-canary.log`
> → `.gitignore:83:/.dnx-*`），不会进入交付物。若验收结束后需要清理，
> 直接 `dropdb` 这四个库并删除 `.dnx-out/ops-review/` 即可，不影响任何既有数据。
> 第 2 轮为隔离 25001 触发条件而建的 `nexus_probe_*` 临时库已在实验结束时全部删除（实测剩余 0 个）。
