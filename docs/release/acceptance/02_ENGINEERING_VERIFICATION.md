# 02 工程团队验收核验：CA-01..CA-10 整改状态 + 覆盖率 / 静态检查 / 安装构建

| 项目 | 内容 |
| --- | --- |
| 文档性质 | 工程（供应方）团队对 `19_COMMERCIAL_ACCEPTANCE_AUDIT.md` 中 CA-01..CA-10 发现项的**整改核验报告** |
| 核验日期 | 2026-10-07（Asia/Shanghai） |
| 被核验对象 | 工作副本 `HEAD = b9977bc35cad2f89f9a9363fd001a6cc825f533d` **加上未提交的工作树改动**（10:45 实测 `git status --porcelain`：32 个已修改文件 + 28 个未跟踪条目；该计数在核验窗口内仍在变动）。本报告核验的是"工作树内容"，不是某个已提交的 SHA |
| 核验方法 | 不采信仓库文档结论；CA-01..CA-10 每一条都由本机实际执行的命令确认；命令与输出一并记录 |
| 实测环境 | Windows + 内嵌 PostgreSQL 16.2（`127.0.0.1:51356`）+ bundled Python 3.12（`C:\Users\qqshu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`）+ bundled Node v24.21.0 |
| 证据落盘 | `<repo>/.dnx-out/`（已被 `.gitignore` 的 `/.dnx-*` 覆盖，不进入交付物） |
| 核验结论 | **CA-01/CA-04/CA-07/CA-10 已闭环（4 项）；CA-02/CA-03/CA-05/CA-06/CA-08 部分闭环（5 项）；CA-09 仍开放（1 项）**。另有 3 项工程侧新发现，见 §6 |
| 覆盖率实测口径 | **75%（27943 statements / 6926 missed）**，本机独立复现，与上一轮 `coverage.json` 完全一致 |

> **工程立场声明。** 本报告只回答"代码/配置/文档层面的整改是否成立、当前测试与构建的真实状态是什么"，
> 不回答"这份软件能否作为商业交付物被接收"。CA-09 是验收阻塞项，且**工程证据无法代替人工 UAT**：
> 即使全部自动化门禁为绿，商用处置仍由甲方/放行门禁决定。

---

## 0. 方法、基线与工具版本

### 0.1 被核验对象是脏工作树

```
命令: git rev-parse HEAD
输出: b9977bc35cad2f89f9a9363fd001a6cc825f533d

命令: git log --oneline -1
输出: b9977bc fix: refuse undeclared optimiser payment timing

命令: git status --porcelain   （节选；完整未跟踪清单可在仓库根用 git status --porcelain --untracked-files=all 复现）
 M .github/workflows/ci.yml
 M .gitignore
 M pyproject.toml
 M scripts/install/windows/Install-EurogasNexusServerRuntime.ps1
 M src/eurogas_nexus/api/routes/public/auth.py
 ...
 M tests/unit/test_migration_preflight.py
```

因此：**本报告的每一个数字都绑定到"2026-10-07 10:17–10:45 期间的工作树内容"**。
工作树与 HEAD 的差异（核验时 32 改 + 28 新增，计数随时间变动）是本轮整改本身。核验窗口内 `src/`、`packages/python-sdk/src/`
**没有任何文件被改动**（`Get-ChildItem src,packages\python-sdk\src -Recurse -Filter *.py | Where LastWriteTime -gt (now-50min)`
返回空），所以覆盖率与测试数字对应同一份源码内容。

### 0.2 工具与依赖来源

| 用途 | 路径 / 版本 |
| --- | --- |
| Python | bundled `python.exe`（3.12）；系统无 `python` |
| 测试与运行依赖 | `<repo>/.dnx-deps`（hash lock 安装） |
| 覆盖率工具 | `<repo>/.dnx-cov`（`coverage 7.16.2` + `pytest-cov`，来自本轮新增 `requirements-coverage.lock`） |
| 静态检查 | `<repo>/.dnx-deps/bin/ruff.exe`（`ruff 0.16.7`） |
| 前端 | bundled `node.exe` v24.21.0、`clients/web/node_modules`（含 `typescript 5.9.3`） |
| 数据库 | 内嵌 PostgreSQL 16.2，`127.0.0.1:51356`，库 `nexus_verify` / `nexus_browser` |

统一 `PYTHONPATH`（后文所有 pytest 命令）：

```
C:\Users\qqshu\Desktop\Dev Work\EurogasNexus\.dnx-cov;
C:\Users\qqshu\Desktop\Dev Work\EurogasNexus\.dnx-deps;
C:\Users\qqshu\Desktop\Dev Work\EurogasNexus\src;
C:\Users\qqshu\Desktop\Dev Work\EurogasNexus\packages\python-sdk\src
```

---

## 1. CA-01..CA-10 逐条核验

### 1.0 判定汇总

| CA | 优先级 | 判定 | 一句话理由 |
| --- | --- | --- | --- |
| CA-01 | P1 | **已闭环** | `evaluate_gates` 实现 channel rank 继承；实测 stable 下 G11/G19 的 `required=True`，empty evidence → 整体 FAIL |
| CA-02 | P1 | **部分闭环** | schema v2 信封 + SHA/digest/producer/时效/外部审批全部实装且实测拒绝 status-only / 错 SHA / 无 digest 的 PASS；剩余缺口是**非密码学 provenance**（信封字段自述）与外部审批身份尚未配置 |
| CA-03 | P1 | **部分闭环** | `release.yml` web 作业在打包前跑 `npm test` + i18n 门禁，G1 以同 SHA CI run（含 browser acceptance job）为必查项；但**前端套件当前实测红**（2 失败），且无已发布 SHA 的端到端同 SHA 证据 |
| CA-04 | P1 | **已闭环** | 实测打包出 ZIP：11 个成员 = 10 个白名单 payload + 1 个 `release-identity.json`，无递归目录 payload；fail-closed 策略测试通过 |
| CA-05 | P1 | **部分闭环** | 采取"在客户档位禁用受影响能力"分支：trial/release 档位拒绝 MCP 工具发现与调用（实测 37 项相关测试全过）；但**持久化服务身份、elevation 双人控制、org/desk 隔离仍未构建** |
| CA-06 | P1 | **部分闭环** | 显式下载 `image-metadata` + 强制 digest 校验已实装，并在不可变 amd64 镜像内执行了 notice 校验器；但**镜像启动 + PostgreSQL 迁移 + 认证 smoke 仍未做**（arm64 仅查 manifest 未执行） |
| CA-07 | P1 | **已闭环** | `ARCHITECTURE_V2_EXECUTION_STATE.md` 已改写（2026-10-06），全文不再出现"Nothing else is outstanding"；`RELEASE_READINESS.md` 顶部标注 2026-09-22 审计覆盖为 NOT APPROVED |
| CA-08 | P1 | **部分闭环** | `.automation/` 已 0 跟踪、0 落盘，`.dockerignore` 排除，`git archive HEAD` 无 automation 路径；但**公开 HEAD 仍跟踪一个乱码名残留文件**，内含整棵 `.automation` 树 38 个路径名（见 §6.3） |
| CA-09 | 验收阻塞 | **仍开放** | 自动化整套（Playwright + axe，3 视口 × EN/ZH）存在且被 G1 绑定为同 SHA 必查 job；但**全流程人工/业务验收矩阵未完成**，`20_AUTHENTICATED_HMI_AUDIT.md` 自述"仅 `/api/me` + 两次认证 GET …Disposition remains NOT APPROVED" |
| CA-10 | P1 | **已闭环** | 两个安装脚本 **0 个制表符**；`release-identity.json` 实测随运营 ZIP 交付并含不可变镜像 digest；"无源码 checkout 的解压包 preflight"测试在本机 Windows 上实跑通过 |

**计数：已闭环 4（CA-01/04/07/10）；部分闭环 5（CA-02/03/05/06/08）；仍开放 1（CA-09）。**

---

### CA-01 — 稳定通道跳过 RC 门禁

**审计原文要求**：`evaluate_gates` 只匹配请求通道或 `all`，stable 跳过标记为 `rc` 的 G1/G11。

**实现位置**：`scripts/release/validate_stable_release.py:473-480`

```python
# Promotion inherits earlier-channel controls; stable must not skip RC gates.
channel_rank = {"preview": 0, "rc": 1, "stable": 2}
required_for = gate["required_for"]
required = required_for == "all" or (
    required_for in channel_rank
    and channel_rank[channel] >= channel_rank[required_for]
)
```

**独立证明**（自写证据脚本，非仓库文档）：

```
命令: python .dnx-out/proof_ca01_ca02.py
输出（节选）:
git HEAD = b9977bc35cad2f89f9a9363fd001a6cc825f533d
  G1 required_for=all    preview=True  rc=True  stable=True
 G11 required_for=rc     preview=False rc=True  stable=True
 G19 required_for=rc     preview=False rc=True  stable=True
  G6 required_for=stable preview=False rc=False stable=True
 G15 required_for=stable preview=False rc=False stable=True
gates newly mandatory when moving preview -> rc: ['G11', 'G19']
RC-rank gates still mandatory at stable: ['G1','G10','G11','G12','G14','G19','G2','G3','G4','G5','G8','G9']
stable failed with empty evidence dir: True
```

```
命令: pytest -v tests/release/test_customer_release_boundary.py::test_stable_inherits_rc_evidence_requirements \
             tests/release/test_evidence_envelope.py::test_missing_evidence_stays_pending_and_channel_inheritance_holds
输出: 2 passed
```

**判定：已闭环。** G11（Provenance）与 G19（Container acceptance by digest）在 stable 下强制必需，
且缺证据时整体 `failed=True`（fail-closed），而非仅记录状态。

**剩余缺口**：无（工程范围内）。

---

### CA-02 — 证据文件只被当作"状态声明"

**审计原文要求**：`load_evidence` 不检查被测 SHA、制品 digest、签发者、时效与环境；要求版本化证据信封、
SHA/digest 绑定、provenance 与显式授权的外部审批；**任何情况下不得伪造 PASS 记录**。

**实现事实**（`scripts/release/evidence_envelope.py` + `validate_stable_release.py`）：

- `EVIDENCE_SCHEMA_VERSION = 2`：旧格式 / status-only 一律 FAIL，文件缺失才是 PENDING_EXTERNAL；
- `commit_sha` 必须是 40 位小写 SHA，且与 release context 的 `git_sha` 逐字比对（`validate_stable_release.py:366-378`）；
- `subject.kind ∈ {source, artifact, image}`，artifact 绑定的 PASS 必须给出 digest，且 digest 与实际
  bundle 文件重算的 sha256 比对；image 绑定必须等于 `api_image_digest`，并与 `image-metadata.json` /
  `release-manifest.json` 里 release run 自己产出的 digest 比对（`_trusted_image_digests`）；
- `producer.{workflow,job,environment,run_id}` 必须命中 policy 的 `producers` 白名单，`local_only` profile
  仅在本机 dry-run flag 下接受；
- `evidence_policy.max_age_days=30` / `future_skew_minutes=15` 时效与未来时间拒绝；
- G1 额外要求 PASS 证据声明 `report.ci_run`，并由校验器**重新向只读 GitHub API 反查**该 run
  （仓库/工作流/提交固定，必需 job 全部成功）。

**独立证明**（自写证据脚本）：

```
命令: python .dnx-out/proof_ca01_ca02.py
输出（节选）:
== CA-02: status-only / wrong-SHA evidence can never read as PASS ==
legacy status-only G2 -> FAIL | unsupported evidence schema_version None; evidence must be a schema_version 2 envelope; evidence commit_sha mu
legacy status-only overall failed: True
wrong tested SHA -> FAIL | evidence commit 0000000000000000000000000000000000000000 is not the release commit b9977bc35cad2f89f9a9363fd00
artifact PASS without digest -> FAIL | artifact-bound gate PASS must bind the tested digest(s); a status-only claim cannot authorise release
== CA-02 residual: external gates cannot self-approve ==
authorized_external_approvals = []
```

```
命令: pytest -q tests/release/test_customer_release_boundary.py tests/release/test_evidence_envelope.py \
             tests/release/test_publication_gate_enforcement.py tests/release/test_ci_run_verification.py \
             tests/release/test_deployment_bundle_policy.py tests/release/test_deployment_roles.py \
             tests/release/test_container_promotion.py tests/release/test_release_engineering.py
输出: 285 passed, 3 skipped, 2 warnings in 73.66s
```

**判定：部分闭环。**

- 审计列出的四项要求（版本化信封、SHA/digest 绑定、provenance 校验、显式授权外部审批）**均已实装并被负例证明**；
- 外部门禁 G15–G18 在无 `authorized_external_approvals` 身份时永远是 FAIL/PENDING，**不能自证通过**（符合"不得伪造 PASS"）。

**剩余缺口（明确写出）**：

1. **provenance 不是密码学 provenance。** `evidence_envelope.py` 模块 docstring 与 policy 均自述：
   "Every field is self-declared JSON text… a hostile actor who can write into the evidence directory can still
   claim an authorised producer identity. Signed attestation and GitHub-run metadata verification remain
   documented residual work." 即 G2/G3/G4/G12/G19 的 producer run identity 仍为自述，**签名 attestation 未实现**；
2. `authorized_external_approvals = []`：外部审批路径（G15 外部安全验收、G16 供应商认证、G17 代码签名、
   G18 用户验收）当前**没有任何已配置的授权身份**，因此这 4 个门禁在机制上无法 PASS（fail-closed 正确，
   但也意味着"外部审批端到端跑通"这件事没有证据）；
3. 没有对真实发布执行过完整门禁集（本机仅做单元/契约级负例，见 §8）。

---

### CA-03 — release 发布不绑定前端与前端的同 SHA 证据

**审计原文要求**：`release.yml` web 作业只构建、不跑前端套件；发布与同 SHA 的 browser/critical workflow 证据不绑定。

**实现事实**（`.github/workflows/release.yml` web 作业）：

```yaml
      - name: Test Web client before packaging
        working-directory: clients/web
        run: npm test

      - name: Check bilingual UI key coverage
        run: python scripts/uat/check_i18n_parity.py

      - name: Build Web client with release identity
        ...
      - name: Package Web client
```

即"前端测试 + 双语 key 门禁"都排在 `npm run build` 与打包**之前**（有对应回归：
`tests/release/test_customer_release_boundary.py::test_release_web_tests_precede_build_and_packaging`）。

同 SHA 绑定由 G1 承担：`scripts/release/policy/stable_gate_policy.json` 的 `ci_acceptance.required_jobs` 为

```
命令: python -c "import json;p=json.load(open('scripts/release/policy/stable_gate_policy.json'));print('\n'.join(p['ci_acceptance']['required_jobs']))"
输出:
validate
Dependency license & CVE audit
PostgreSQL integration
web-client-build
Browser acceptance (EN/ZH, 3 viewports)
```

且 `ci.yml` 中 `browser-acceptance` job 的 `name` 正是 `Browser acceptance (EN/ZH, 3 viewports)`，
入口脚本 `scripts/uat/browser_workflow_smoke.mjs` 存在。

**独立证明**：

```
命令: python scripts/uat/check_i18n_parity.py
输出: {"missing": [], "ok": true, "only_en": [], "only_zh": [], "referenced_keys": 1770, "zh_keys": 2922}
EXIT=0
```

**判定：部分闭环。** 门禁接线已闭环（打包前测试 + 同 SHA CI 反查），但**该门禁本机实测为红**：

```
命令: cd clients/web; node --test "tests/*.test.ts"
输出: exit 1；2 个测试失败（详见 §6.1）
      ✖ one resolution feeds both the layout class and the rendered task
      ✖ the identity gate returns before the hooks, and the component it mounts owns them
```

**剩余缺口**：

1. `npm test` 在当前环境（bundled Node v24.21.0）**失败**，会阻塞 release web 作业 → G4 证据无法产出（详见 §6.1 的根因）；
2. 没有任何已发布 SHA 的"同 SHA browser acceptance + 关键工作流证据"端到端记录（本轮未执行 release workflow），
   因此 G1 的同 SHA 反查只在单元层被证明，未在真实发布上被证明。

---

### CA-04 — 部署打包器递归复制本地目录

**审计原文要求**：Python/Bash/PowerShell 打包器递归复制本地 runtime/doc 树，可能把密钥或私有文件带进客户 ZIP。

**实现事实**：`scripts/release/package_deployment_bundle.policy.json`（schema 2）采用**显式白名单**：
`entries` 10 条 + 一个生成的 `release-identity.json`；`forbidden_member_globs` 明确禁止
`.automation/`、`docs/engineering/`、`tests/`、`.env*`、`*.pem/*.key/*.crt/*.pfx`、`*.sqlite/*.db/*.zip/*.tar.gz` 等；
policy 首段写明 "Recursive directory copies are not permitted, and the packager fails closed on missing
required files, unsafe paths, symlinks and duplicates."

**独立证明（真实构建，不是读文档）**：

```
命令: python scripts/release/package_deployment_bundle.py .dnx-out/bundle-ca04 \
        --release-context .dnx-out/bundle-context.json --image-digest sha256:aaaa…(64)
输出: .dnx-out\bundle-ca04\Eurogas-Nexus-Server-Windows.zip     （30804 bytes，EXIT=0）

命令: python -c "import zipfile;z=zipfile.ZipFile(...);…"
输出:
members: 11
  Eurogas-Nexus-Server-Windows/START-HERE.txt
  Eurogas-Nexus-Server-Windows/deploy/runtime/Caddyfile
  Eurogas-Nexus-Server-Windows/deploy/runtime/README-CN.md
  Eurogas-Nexus-Server-Windows/deploy/runtime/README-EN.md
  Eurogas-Nexus-Server-Windows/deploy/runtime/compose.yaml
  Eurogas-Nexus-Server-Windows/docs/deployment/DEPLOYMENT_ROLES-CN.md
  Eurogas-Nexus-Server-Windows/docs/deployment/DEPLOYMENT_ROLES-EN.md
  Eurogas-Nexus-Server-Windows/docs/deployment/HANDOVER_INDEX.md
  Eurogas-Nexus-Server-Windows/release-identity.json
  Eurogas-Nexus-Server-Windows/scripts/install/windows/Deploy-EurogasNexus.ps1
  Eurogas-Nexus-Server-Windows/scripts/install/windows/Install-EurogasNexusServerRuntime.ps1
```

**判定：已闭环。** 11 = 10 个白名单 payload + 1 个身份文件；无递归目录 payload、无测试/工程文档/密钥/环境文件。
fail-closed 行为由 `tests/release/test_deployment_bundle_policy.py` 的 26 个用例覆盖
（`test_missing_required_file_fails_closed`、`test_unapproved_and_secret_files_never_enter_the_archive`、
`test_windows_junction_escaping_the_repository_is_refused` 等），已在本机随 285-passed 批次实跑。

**剩余缺口**：无（工程范围内）。注意口径：审计原文"Ten payload files verified"指
**10 个 payload + 1 个生成的身份文件 = 11 个成员**，两者不矛盾。

---

### CA-05 — 多组织/桌面隔离与服务身份未构建

**审计原文要求**：不要做共享多组织/桌面隔离声明；要么构建并测试持久化服务身份、elevation 双人控制与
scope 隔离，要么在客户档位禁用受影响能力。

**实现事实（选择"禁用"分支）**：

1. `src/eurogas_nexus/mcp/server.py:13-17,44-80`：客户档位（`trial`/`release` 环境，或 `release` API profile）
   **拒绝工具发现与调用**，包括导出的 handler（`MCPToolAccessDisabled`），理由写明是"在 D6 持久化服务身份建成之前，
   环境授予的身份是无主权限"；允许清单 fail-closed（`_MCP_TOOL_ENVIRONMENTS={development,test}`、
   `_MCP_TOOL_API_PROFILES={development,internal}`）。
2. `src/eurogas_nexus/security/capabilities.py:279,333-346`：`UNSUPPORTED_SCOPE_KINDS = ("ORGANIZATION",
   "PORTFOLIO", "MARKET", "REGION")`，backend 无法表达的 scope 种类**如实上报**而不是编造
   （`ExperienceProfile.unsupported_scope_kinds`）。

**独立证明**：

```
命令: pytest -q tests/unit/test_mcp_deployment_gate.py tests/security/test_experience_profile.py
输出（-v 摘录）: 37 passed
  tests/unit/test_mcp_deployment_gate.py::test_customer_facing_profiles_refuse_discovery_and_invocation[trial] PASSED
  tests/unit/test_mcp_deployment_gate.py::test_customer_facing_profiles_refuse_discovery_and_invocation[release] PASSED
  tests/unit/test_mcp_deployment_gate.py::test_exported_handlers_refuse_direct_invocation PASSED
  tests/unit/test_mcp_deployment_gate.py::test_stdio_subprocess_refuses_in_a_customer_facing_deployment PASSED
  tests/unit/test_mcp_deployment_gate.py::test_unknown_environment_fails_closed[prod|Trial|RELEASE|production] PASSED
  tests/security/test_experience_profile.py::test_scope_kinds_report_what_the_backend_cannot_express PASSED
```

**判定：部分闭环。** "禁用受影响能力"这一可选分支已实装并有负例证明；**但底层能力仍未构建**，
因此不得出现任何共享多组织/桌面隔离的能力声明。

**剩余缺口**：

1. **持久化服务身份（D6）** 未构建 —— 客户档位目前是"整体不提供 MCP"，而不是"以持久化身份提供"；
2. **elevation 双人控制** 未构建、未测试；
3. **组织/桌面（desk）隔离** 未构建：`ORGANIZATION/PORTFOLIO/MARKET/REGION` scope 仍被列为 backend 无法表达的
   种类，`portfolio.*` 等能力只在角色权限范围内成立，没有组织维度的强制边界。

---

### CA-06 — 容器验收只查 manifest，不查运行态

**审计原文要求**：容器验收只检查 manifest 平台，不检查运行中服务健康与安装/升级/回滚；assembly 下载 `release-*`
而镜像元数据名为 `image-metadata`；证据路径组装也需要端到端证明。

**实现事实**：

- `release.yml` 的 `container-acceptance` 作业：`Download image metadata` → `name: image-metadata`，
  然后 `docker buildx imagetools inspect "$IMAGE@$DIGEST"` 校验 digest 与 `linux/amd64`、`linux/arm64`；
  再进行 "Execute notice verification in the immutable amd64 image"：
  `docker run --rm --network none --platform linux/amd64 "$IMAGE@$DIGEST" python scripts/release/verify_python_license_texts.py`
  —— 非零退出即失败，G19 的 PASS 只在该执行成功后才写出；
- `assemble` 作业：`Download all release artifacts`（`pattern: release-*`）+ **单独的**
  `Download immutable image identity`（`name: image-metadata` → `release-assets/image-metadata`），
  即修掉了 `release-*` 通配符与 `image-metadata` 命名不匹配的缺陷；
- 证据写入用 `--image-digest "$DIGEST"`，由 `_trusted_image_digests` 与 `image-metadata.json` 交叉校验。

**独立证明**（读实际 workflow 文本 + 策略反查）：

```
命令: Select-String -Path .github/workflows/release.yml -Pattern 'alembic|/healthz|healthcheck|rollback|docker run'
输出: L904: docker run --rm --network none --platform linux/amd64 \        ← 全文件唯一一次容器执行
```

```
命令: pytest -q tests/release/test_container_promotion.py     （随 §2 的 285-passed 批次）
输出: 通过（含 test_post_copy_digest_mismatch_fails_closed…、test_failure_other_than_manifest_not_found_never_writes 等 40 项）
```

**判定：部分闭环。** 元数据下载与 digest 校验已闭环，且在不可变镜像内**执行**了校验器（不只是 inspect）。

**剩余缺口**：

1. **不可变镜像启动 + 服务健康（healthcheck/HTTP 探活）未做**：唯一一次 `docker run` 是
   `--network none` 跑一次性校验器，不启动服务、不探活；
2. **镜像内 PostgreSQL 迁移未做**：迁移证据来自源码级 CI（`ci.yml` → `scripts/ci/run_postgres_ci.sh`，G3），
   不是"用交付镜像对自己该连的库执行 `alembic upgrade head`"；
3. **认证 smoke 未做**；arm64 仅确认 manifest 存在，**未执行**（工作流注释亦自述）；
4. **"最终证据组装"没有端到端证明**：没有对当前 SHA 执行过 release workflow，G19/G4 等证据的实际拼装未被验证。

---

### CA-07 — 检查点声称"没有其他遗留项"

**审计原文要求**：修正检查点；本次审计才是当前商用处置，不是历史测试总数。

**独立证明**：

```
命令: Select-String -Path docs\engineering\*.md,docs\engineering\Architecture-V2\*.md -Pattern 'Nothing else is outstanding'
输出: 仅 Architecture-V2\19_COMMERCIAL_ACCEPTANCE_AUDIT.md:35（审计原文引述）
      → 检查点正文已无该句

命令: Get-Content docs\engineering\ARCHITECTURE_V2_EXECUTION_STATE.md -TotalCount 45
输出:
# Architecture V2 Execution State
Last updated: 2026-10-06
Audit baseline: `e911fae`, equal to `origin/main` at audit start. Historical slice records below do not
constitute current production approval.
...
review; no commercial approval is claimed.
...

命令: Get-Content docs\release\RELEASE_READINESS.md -TotalCount 14
输出:
2026-09-22 commercial audit override: **NOT APPROVED FOR CUSTOMER PRODUCTION**.
The evidence below is historical, scoped to its dated ref, and does not certify Architecture V2.
...
Status: `RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`
```

状态文档中反复出现"no commercial approval is claimed / commercial readiness is not established /
commercial-delivery objective is not complete / remain open"（共 15 处），并与审计文档互链。

**判定：已闭环。** 检查点已改写并显式从属于本次商用审计，历史测试总数不再被当作放行依据。

**剩余缺口**：无（文档口径层面）。历史 Git 对象与已发布 release 未改写，符合审计的"不做历史重写"要求。

---

### CA-08 — 公开源码跟踪本地自治监督器配置

**审计原文要求**：把 `.automation` 从跟踪交付中移除，**保留本地文件不改动**；从 Docker 上下文与源码归档中排除；
不重写历史。

**独立证明**：

```
命令: git ls-files .automation | Measure-Object | Select -Expand Count      → 0
命令: git ls-tree -r HEAD --name-only | Select-String 'automation' | Count  → 0
命令: Test-Path .automation                                                 → False
命令: Get-ChildItem .automation -Recurse -File | Measure-Object             → 0
命令: git check-ignore -v .automation                                       → exit 1（未被忽略；目录已不存在且无跟踪）
命令: Get-Content .dockerignore
输出: …  .automation  .agent  output  artifacts  …  tests  docs  dist      ← Docker 上下文排除 .automation
命令: git archive HEAD（成员清单）| Select-String 'automation' | Count        → 0
             （实测口径：`git ls-tree -r HEAD --name-only` 全量列表过滤 automation = 0；
               说明：`git archive | tar -t` 经由 PowerShell 管道会破坏 tar 头，故改用等价且可靠的 ls-tree）
命令: git status --porcelain → 无 .automation；?? 条目均已被 /.dnx-* 覆盖
```

**判定：部分闭环。**

**剩余缺口（本机新发现，P1）**：

1. **公开 HEAD 仍跟踪一个乱码名残留文件**，内容正是 `.automation` 整棵树的 `git diff --stat`
   （38 个 `.automation/...` 路径名，含 `prompts/*.md`、`scripts/supervisor.py`、`config.toml` 等）。
   该文件会被 GitHub 自动源码 tarball 与任何 `git archive HEAD` 带出，**与"把自动化从源码归档排除"的意图直接冲突**。证据见 §6.3；
2. 审计要求"retain local files unchanged"，但**本地 `.automation` 目录已不存在**（`Test-Path` 为 False，
   桌面工作区内也搜不到 `.automation*` 目录）。这是相对审计指令的一处偏离：文件不是"保留在原地只是不跟踪"，
   而是从工作区消失了（是否另有备份不在本仓库内，本报告无法确认）。

---

### CA-09 — 无整产品可视化/交互验收证据（验收阻塞）

**审计原文要求**：提供整产品可视化/交互验收证据；9/23 已能登录，但完整工作流矩阵仍然开放。

**独立证明（工程侧可验证的部分）**：

```
命令: python -c "…print(p['ci_acceptance']['required_jobs'])"
输出: 包含 'Browser acceptance (EN/ZH, 3 viewports)'        ← 即 G1 的必查 job

命令: Select-String .github/workflows/ci.yml -Pattern '^  browser-acceptance:'
输出: name: Browser acceptance (EN/ZH, 3 viewports)
      run: node scripts/uat/browser_workflow_smoke.mjs
      env: EUROGAS_UAT_PLAYWRIGHT_PATH=scripts/ci/browser-acceptance/node_modules/playwright/index.js
           EUROGAS_UAT_AXE_PATH=scripts/ci/browser-acceptance/node_modules/axe-core/axe.min.js

命令: Test-Path scripts/uat/browser_workflow_smoke.mjs → True
命令: Test-Path scripts/uat/seed_browser_identity.py → True
命令: Test-Path $env:USERPROFILE\AppData\Local\ms-playwright\chromium-1187 → True

命令: Get-Content docs/engineering/Architecture-V2/20_AUTHENTICATED_HMI_AUDIT.md -Tail 18
输出:
Limits of this evidence: `/api/me` plus two authenticated GETs. It is not a persona business walkthrough,
it exercises no mutation, and it proves nothing about permitted/denied write behaviour per role.
No browser walkthrough is newly verified: the existing tab and a fresh tab both timed out during
inspection in this window and the root cause is open. … Disposition remains NOT APPROVED.
```

**判定：仍开放（验收阻塞）。** 自动化整套（Playwright + axe，EN/ZH × 3 视口）存在、被 G1 绑定为同 SHA 必查 job，
但审计要求的"整产品可视化/交互/业务工作流验收矩阵"没有完成，且审计 20 自述证据面只有 `/api/me` + 两次 GET。

**剩余缺口**：

1. 无人工/业务工作流验收记录（persona 走查、mutation 权限行为、完整工作流矩阵）；
2. 无 EN/ZH × 3 视口的可复核产物与结论（本机未重跑 sweep，原因见 §8.2）；
3. 审计 20 记录的浏览器 tab 超时"root cause is open"未见关闭证据。

---

### CA-10 — Windows 安装脚本的制表符路径与运营 ZIP 缺版本身份

**审计原文要求**：`tauri.conf.json` 回退路径含字面制表符，且该配置不在运营 ZIP 中；无 `EUROGAS_NEXUS_VERSION`
时连 preflight 都解析不出版本。要求：在 bundle 里交付显式不可变发布身份，并在**无源码 checkout** 的情况下
测试解压包 preflight；不得声称该 ZIP 已获安装批准。

**独立证明**：

```
命令: for f in Install-EurogasNexusServerRuntime.ps1, Deploy-EurogasNexus.ps1, package_deployment_bundle.ps1
      { 统计 [char]9 出现次数 }
输出:
scripts\install\windows\Install-EurogasNexusServerRuntime.ps1 : tab_count=0
scripts\install\windows\Deploy-EurogasNexus.ps1 : tab_count=0
scripts\release\package_deployment_bundle.ps1 : tab_count=0

命令: Select-String scripts/install/windows/*.ps1 -Pattern 'release-identity.json|tauri.conf.json|EUROGAS_NEXUS_VERSION'
输出（Deploy-EurogasNexus.ps1）:
L36: $ReleaseIdentityPath = Join-Path $BundleRoot "release-identity.json"
L38: $SourceTauriConfigPath = Join-Path $BundleRoot "clients\desktop\src-tauri\tauri.conf.json"
L101-110: Resolve-ReleaseIdentity —— 先读 bundle 的 release-identity.json；
          若同时给了 EUROGAS_NEXUS_VERSION/CHANNEL 且与 bundle 身份冲突则 throw（身份冲突而非静默覆盖）
L131: 两者都没有时 throw "Cannot resolve the release identity: … Use the released operator ZIP."（fail-closed）
```

```
命令: pytest -q tests/release/test_deployment_roles.py tests/release/test_release_dry_run.py
输出: 27 passed, 2 warnings in 75.49s

其中（-v 单独确认）:
tests/release/test_deployment_roles.py::test_extracted_deploy_preflight_resolves_identity_without_env_version PASSED
tests/release/test_deployment_roles.py::test_extracted_runtime_preflight_never_fails_with_an_identity_error PASSED
```

且 §CA-04 的真实构建已证明 `release-identity.json` **确实在运营 ZIP 内**，内容含：

```json
{
  "app_version": "0.5.0", "channel": "preview", "commit_sha": "b9977bc35cad…",
  "api_image_reference": "ghcr.io/eurogasnexus/eurogas-nexus-api@sha256:aaaa…",
  "product_name": "Eurogas Nexus", "release_version": "v0.5.0-preview.7.b9977bc35cad", "schema_version": 1
}
```

**判定：已闭环。** 制表符消失；不可变发布身份随包交付；无源码 checkout 的解压包 preflight 在 Windows 上实跑通过；
无身份时 fail-closed 并给出明确指引。

**剩余缺口 / 保留意见**：

1. 回退路径 `clients\desktop\src-tauri\tauri.conf.json` 仍不在 ZIP 内，只在源码 checkout 场景成立——但该分支已被
   现实身份文件短路，且否则 fail-closed，不构成静默错误；
2. **未做原生安装**（没有在干净 Windows 上执行 Install/Repair/Uninstall），因此**不得声称该 ZIP 已获安装批准**
   —— 与审计结尾"不得声称"的要求一致。

---

## 2. 静态检查（ruff）

### 2.1 核验窗口内的真实变化（重要）

| 时刻 | 命令 | 结果 |
| --- | --- | --- |
| 10:21（核验开始时） | `ruff check .` | **exit 1，1538 errors**；`ruff check . --exclude .dnx-cov` → `All checks passed!` exit 0 |
| 10:28（Lead 修复后，我独立复跑） | `ruff check .` | **exit 0，`All checks passed!`** |

10:21 的 1538 条**全部（1538/1538）**来自 `.dnx-cov/`（本轮新增的覆盖率依赖目标）：

```
命令: ruff check . -q --output-format concise | Select-String '^\.dnx-cov' | Measure-Object → 1538
命令: ruff check . -q --output-format concise | Measure-Object                      → 1538
```

根因是两处枚举式疏漏：`pyproject.toml [tool.ruff] exclude` 与 `.gitignore` 都列了 `.dnx-deps/.dnx-out/
.dnx-verify/.dnx-audit/.dnx-npm/.dnx-pg/.dnx-pgdata`，但**没有 `.dnx-cov`**（`git check-ignore .dnx-cov`
返回 exit 1，`git status` 显示 `?? .dnx-cov/`）。这是"同一个疏漏第三次发生"（先 `.dnx-verify`、再 `.dnx-audit`），
Lead 的修复改为**模式**而非再加一个名字。

### 2.2 对 Lead 修复的独立复核（不引用其结论）

```
命令: Select-String -Path pyproject.toml -Pattern 'exclude = \[' -Context 0,3
输出:
exclude = [
    ".automation",
    ".dnx-*",
]

命令: Select-String -Path .gitignore -Pattern 'dnx'
输出:
L83: /.dnx-*          ← 无尾斜杠；注释解释 /.dnx-*/ 只匹配目录内部，裸目录仍会显示为未跟踪

命令: git check-ignore -v .dnx-cov ; .dnx-cov/x.py ; .dnx-not-created-yet
输出: 三者 exit=0（含一个尚未创建的目录名）

命令: git status --porcelain | Select-String 'dnx' → 0 条

命令: ruff check . → All checks passed!  RUFF_EXIT=0

命令: pytest -q tests/contract/test_local_workspace_hygiene.py
输出: 6 passed
```

**结论：静态检查门禁现为绿（exit 0），且修复以 glob 形式钉住，新增回归测试 6 passed。**
（`fnmatch` 语义与"未创建目录名也被忽略"这两条，正是能提前抓住三次历史疏漏的检查。）

---

## 3. 覆盖率（独立复现）

### 3.1 复现命令（本轮 `requirements-coverage.lock`，不改动 runtime 依赖）

```
cd <repo>
$env:PYTHONPATH='<repo>\.dnx-cov;<repo>\.dnx-deps;<repo>\src;<repo>\packages\python-sdk\src'
$env:COVERAGE_FILE='<repo>\.dnx-out\.coverage-eng'
python -m pytest -q tests/unit tests/domain tests/contract tests/sdk tests/cli tests/security `
  tests/optimization tests/ingestion tests/evals tests/streaming tests/workflow tests/uat tests/release `
  --cov=eurogas_nexus --cov-report=term --cov-report=json:<repo>\.dnx-out\coverage-eng.json
```

### 3.2 实测结果

```
TOTAL    27943    6926    75%           （term 报告末行）
2640 passed, 6 skipped, 2 warnings in 440.29s (0:07:20)
Coverage JSON written to file …\.dnx-out\coverage-eng.json
EXIT=0
```

JSON 复核（`python .dnx-out/cov_lowest.py .dnx-out/coverage-eng.json`）：

```
TOTAL statements=27943 missed=6926 covered=21017 percent=75.21
files measured: 366
```

**对照上一轮 `.dnx-out/coverage.json`**（不是引用，是做一致性比对）：

```
命令: python .dnx-out/cov_lowest.py .dnx-out/coverage.json
输出: TOTAL statements=27943 missed=6926 covered=21017 percent=75.21
      files measured: 366
      （最低 15 个模块的名单、语句数、缺失行号前缀完全一致）
```

→ **独立复现成功：75.21%（四舍五入 75%），两次运行的 27943/6926/366 三项全等。**

### 3.3 按目录通过/跳过数

覆盖率命令跑完后，为取得按目录明细，用同一批目录再跑一次并落 JUnit XML
（这次**不计覆盖率**，故更快；两次收集数的差异原因见下）：

```
命令: python -m pytest -q tests/unit tests/domain tests/contract tests/sdk tests/cli tests/security `
        tests/optimization tests/ingestion tests/evals tests/streaming tests/workflow tests/uat tests/release `
        --junitxml=<repo>\.dnx-out\junit-eng.xml
输出: 2649 passed, 6 skipped, 2 warnings in 326.42s

命令: python .dnx-out/junit_by_dir.py .dnx-out/junit-eng.xml
输出:
directory               passed  skipped  failed   total
tests/cli                   19        0       0      19
tests/contract             525        0       0     525
tests/domain               256        0       0     256
tests/evals                 20        0       0      20
tests/ingestion             50        0       0      50
tests/optimization          36        0       0      36
tests/release              427        6       0     433
tests/sdk                   58        0       0      58
tests/security             367        0       0     367
tests/streaming              3        0       0       3
tests/uat                   81        0       0      81
tests/unit                 805        0       0     805
tests/workflow               2        0       0       2
TOTAL                     2649        6       0    2655
```

两点必须写清楚，否则数字不可复现：

1. **任务书给出的命令实际列出 13 个测试目录**（`unit, domain, contract, sdk, cli, security, optimization,
   ingestion, evals, streaming, workflow, uat, release`），不是 14 个；JUnit 聚合确认只有这 13 个目录被收集。
2. **两次收集数相差 9**（覆盖率为 2640+6=2646，JUnit 为 2649+6=2655）。核验窗口内有 2 个新测试文件被加入
   （`tests/contract/test_local_workspace_hygiene.py` 10:22:10、`tests/contract/test_openapi_surface_claim.py` 10:25:40），
   共 9 条用例，全部落在 `tests/contract`（525）。因此**覆盖率 TOTAL 对应 10:18–10:25 的测试集，
   目录明细对应 10:26–10:31 的测试集**；两者反的是同一份 `src/`（窗口内 `src/` 零改动）。

**6 个跳过全部在 `tests/release`，原因均为本机平台不允许创建符号链接**（JUnit skip message 原文）：
`test_symlinked_repository_root_is_refused` / `test_symlinked_source_file_is_refused` /
`test_symlinked_directory_escaping_the_repository_is_refused`（"creating symlinks is not permitted on this platform"）、
`test_symlinked_declared_file_is_refused` / `test_symlinked_package_directory_is_refused` /
`test_unsafe_destinations_and_symlinked_files_are_refused`（"symlinks are unavailable in this environment"）。
这些是**平台条件跳过**，与整改内容无关；符号链接之外的交接点（junction）拒绝用例在本机是**实跑通过**的。

### 3.4 覆盖率最低的 10 个模块（含缺失行号）

排序规则：`percent_covered` 升序，百分比相同按语句数降序（让"完全没测到的大模块"排在前面）。
缺失行号首 25 个，括号内为总缺失数。

| # | 覆盖率 | 语句数 | 缺失 | 模块 | 缺失行号（前 25） |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.00% | 181 | 181 | `src/eurogas_nexus/db/repositories/reference_network.py` | 7,8,10,12,23,24,27,28,29,30,31,32,33,34,35,36,37,38,39,42,43,46,47,48,49（+156） |
| 2 | 0.00% | 122 | 122 | `src/eurogas_nexus/application/data_products.py` | 18,20,21,22,24,31,32,36,41,44,65,66,72,73,83,84,97,100,101,102,103,104,105,107,110（+97） |
| 3 | 0.00% | 121 | 121 | `src/eurogas_nexus/application/data_platform_snapshots.py` | 21,23,24,25,26,28,32,40,41,45,53,55,56,57,60,86,87,88,89,91,92,93,94,97,98（+96） |
| 4 | 0.00% | 108 | 108 | `src/eurogas_nexus/db/repositories/decision.py` | 9,11,12,14,16,17,18,33,34,37,55,56,57,58,59,60,78,79,91,92,95,103,104,105,106（+83） |
| 5 | 0.00% | 27 | 27 | `src/eurogas_nexus/domain/route_cost/uk_public_tariffs.py` | 11,13,14,16,22,23,25,26,30,31,33,64,303,314,315,316,317,329,330,331,343,346,363,396,402（+2） |
| 6 | 0.00% | 23 | 23 | `src/eurogas_nexus/db/repositories/storage_nomination.py` | 3,5,7,9,16,24,25,26,27,28,29,30,31,34,42,50,53,60,65,73,74,75,76 |
| 7 | 0.00% | 15 | 15 | `src/eurogas_nexus/domain/agents/model_routing.py` | 3,5,8,9,10,11,12,13,14,17,70,71,72,73,74 |
| 8 | 0.00% | 9 | 9 | `src/eurogas_nexus/streaming/contracts.py` | 3,4,7,8,11,12,13,14,15 |
| 9 | 0.00% | 2 | 2 | `src/eurogas_nexus/core/errors.py` | 4,8 |
| 10 | 0.00% | 2 | 2 | `src/eurogas_nexus/streaming/__init__.py` | 3,5 |
| （11） | 0.00% | 1 | 1 | `src/eurogas_nexus/domain/route_cost/uk_rules.py` | 3 |
| （12） | 10.99% | 91 | 81 | `src/eurogas_nexus/domain/analysis/glossary_profile.py` | 31,32,33,34,46,53,61,62,69,70,76,77,79,80,81,101,102,103,104,109,110,111,112,122,123（+56） |
| （13） | 14.29% | 105 | 90 | `src/eurogas_nexus/domain/analysis/glossary_context.py` | 58,59,60,61,62,63,71,77,83,89,95,96,97,98,99,100,101,105,106,111,113,114,115,126,127（+65） |

> 说明：第 1–11 名都是 **0.00%**（整文件未被任何被测路径导入）。其中 4 个是 `db/repositories/*`
> 与 `application/*` 的持久化/装配模块，说明"DB 支撑的整产品路径"仍有大片未覆盖，
> 这与 §5 的 integration 143 passed 并不矛盾——integration 走的是另一批入口。

### 3.5 为什么"覆盖率不作为门禁阈值"（必须写明的理由）

1. **数字可以被刷，业务正确性不能被刷。** 覆盖率只度量"某行被执行过"，不度量断言强度。
   为了让 75% 变成 80%，最省力的做法是给上面第 1–4 名这种 0% 大模块写"import 即通过"的空测试——
   这恰好是审计反复禁止的"用测试数字代替证据"。
2. **最低覆盖模块与最高风险项不重合。** 当前真正的阻塞项是 **CA-09 全流程人工验收**、
   镜像启动/迁移/认证 smoke（CA-06）、外部审批路径（CA-02/G15–G18）——这些**没有一个能被行覆盖率度量**。
   把阈值当门禁会让团队优化被度量项、放弃未被度量项。
3. **没有经过评审的目标值。** 本仓库没有任何 measured、reviewed 的覆盖率目标；现在凭空定 80% 属于
   "从一台笔记本测试发明生产 SLO"，审计第 3 节明确要求不要这样做。
4. **放行门禁已经由证据契约承担。** `stable_gate_policy.json` 用 G1–G19 的**同 SHA + digest 绑定证据**放行，
   而不是一个百分比；加覆盖率阈值会形成一个与证据契约并行、且更容易被绕过的第二套门禁。
5. **覆盖率口径本身受测试集变化影响。** 本报告已实测：同一天相隔 8 分钟，收集数就相差 9（§3.3）。
   在这样一个仍在快速增加测试的仓库里把百分比设为硬门禁，会让"加测试"直接改变门禁结论。

**建议**：把覆盖率当作**趋势与盲区地图**（例如"0% 的持久化/装配模块名单"进评审），
而不是 threshold；若将来要设阈值，必须先有 owner 评审的目标值与口径冻结。

---

## 4. 安装 / 构建验证

### 4.1 三把哈希锁真实安装（`--require-hashes`）

```
命令（对每一把锁）:
  python -m pip install --require-hashes --target <fresh-dir> -r <lock>
```

| 目标目录 | 锁文件 | 结果 | 安装包数（节选关键包） |
| --- | --- | --- | --- |
| `.dnx-verify/eng-runtime` | `requirements-runtime.lock` | **EXIT=0** | 31 个：`fastapi 0.141.1`、`sqlalchemy 2.0.52`、`alembic 1.20.0`、`pydantic 2.13.5`、`pg8000 1.31.5`、`cryptography 50.0.1`、`uvicorn 0.52.4`、`starlette 1.6.0` |
| `.dnx-verify/eng-build` | `requirements-build.lock` | **EXIT=0** | 31 个：`setuptools 84.0.0`、`wheel 0.48.0`、`pip-audit 2.10.1`、`pip 26.2.1`、`cyclonedx-python-lib 11.12.0` |
| `.dnx-verify/eng-full` | `requirements.lock` | **EXIT=0** | 41 个：`pytest 9.1.1`、`ruff 0.16.7`、`pyyaml 6.0.3`、`rdflib 7.6.0`、`pyarrow 25.0.1` + runtime 全部 |

日志：`.dnx-out/locked-install-eng.txt`。

### 4.2 import 成功验证（每个锁独立目标）

```
命令: PYTHONPATH=<target> python -c "import …; print(version)"
输出:
=== eng-runtime ===
fastapi 0.141.1 / sqlalchemy 2.0.52 / alembic 1.20.0 / pydantic 2.13.5 / pg8000 1.31.5 / cryptography 50.0.1   EXIT=0
=== eng-build ===
pip_audit ok / setuptools 84.0.0 / wheel 0.48.0 / requests 2.34.2                                             EXIT=0
=== eng-full ===
pytest 9.1.1 / pyyaml 6.0.3 / rdflib 7.6.0 / pyarrow 25.0.1 / fastapi 0.141.1                                 EXIT=0
```

### 4.3 `alembic upgrade head` 在活库成功

```
命令:
$env:RUNTIME_STORE_DATABASE_URL='postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_verify'
python -m alembic upgrade head
输出: Context impl PostgresqlImpl. / Will assume transactional DDL.       UPGRADE_EXIT=0

命令: python -m alembic current
输出: 0039_identity_api_key_hash_width (head)                             CURRENT_EXIT=0
```

即：活库已处于 head，迁移链与仓库 `alembic/versions/` 一致（`nexus_browser` 同 revision）。

---

## 5. 测试执行矩阵（除覆盖率外）

| 套件 | 命令要点 | 结果 |
| --- | --- | --- |
| 13 个目录（覆盖率） | 见 §3.1 | **2640 passed, 6 skipped**，440.29s |
| 13 个目录（JUnit 明细） | 见 §3.3 | **2649 passed, 6 skipped, 0 failed**，2655 collected |
| `tests/integration`（活库） | 3 个 opt-in 变量 + `RUNTIME_STORE_DATABASE_URL` | **143 passed**，60.63s |
| `tests/api` 第 1 批（28 文件） | 见 §5.1 | **189 passed**，76.48s |
| `tests/api` 第 2 批（27 文件） | 见 §5.1 | **282 passed**，93.79s |
| release 契约 8 文件 | 见 CA-02 | **285 passed, 3 skipped**，73.66s |
| CA-01/02/05/10 定点 | 见 §1 | **37 passed**，13.28s |
| `tests/contract/test_local_workspace_hygiene.py` | 见 §2.2 | **6 passed** |
| 前端 `npm test` 等价 | `node --test "tests/*.test.ts"` | **exit 1，2 失败**（见 §6.1） |
| 双语 key 门禁 | `python scripts/uat/check_i18n_parity.py` | **exit 0，ok=true**，referenced 1770 / zh 2922 |

### 5.1 活库 integration 与 api 分两批的命令

```
$env:RUNTIME_STORE_DATABASE_URL='postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_verify'
$env:EUROGAS_NEXUS_ACK_INTEGRATION_TEST='1'
$env:EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST='1'
$env:EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST='1'
python -m pytest -q tests/integration
→ 143 passed

# tests/api 55 个文件按文件名字母序对半，两次运行（一次性跑完会被杀）
python -m pytest -q @(测试文件第 1–28 个)   → 189 passed
python -m pytest -q @(测试文件第 29–55 个)  → 282 passed
```

---

## 6. 独立新发现（工程侧，按严重度）

### 6.1 P1 — `npm test` 当前为红，且 release web 作业依赖它（CA-03 直接相关）

```
命令: cd clients/web; node --test "tests/*.test.ts"
输出: exit 1；▲ 859 个 ✔；2 个 ✖
  ✖ one resolution feeds both the layout class and the rendered task
  ✖ the identity gate returns before the hooks, and the component it mounts owns them
    AssertionError: AppShell is one component / 0 !== 1
```

**根因（已定位到可复现的最小事实，不是猜测）**：两个测试文件用
`readdirSync(dir, { withFileTypes: true, recursive: true })` 后依赖 `entry.isFile()`：

```
命令: node -e "readdirSync('src',{withFileTypes:true,recursive:true}) 统计"
输出（bundled Node v24.21.0）:
{ '(none)|isFile=false|isDir=true': 18,
  '.tsx|isFile=false|isDir=false': 70,     ← 70 个 .tsx 全部 isFile()===false
  '.ts|isFile=false|isDir=false': 121,
  '.css|isFile=false|isDir=false': 11,
  '.json|isFile=false|isDir=false': 2 }
```

即：**递归模式返回的 Dirent 对普通文件没有类型信息**（`type === UNKNOWN`），`isFile()` 恒为 false，
于是 `tsxFiles()` 返回空数组，两个结构性测试都失去扫描对象而失败。这不是本仓库源码缺陷，
而是测试辅助函数依赖了 Node 递归 Dirent 的类型字段（同类问题在其他项目里也出现过：
[stablyai/orca 的 source-scan 修复](https://github.com/stablyai/orca/commit/7a16059adc22d88c84471cb6a9255af3bd8e785b)、
[Deno 对 Dirent name/parentPath 的修复](https://app.semanticdiff.com/gh/denoland/deno/commit/6605058d4e80512d7d0ddbfb58a48fb57efb652d)）。

**影响**：

- `release.yml` 的 "Test Web client before packaging" 与 `ci.yml` 的 `web-client-build` 都跑这条命令 →
  在当前 Node 行为下会红，G4 前端证据无法产出；
- 本机上一轮落盘的 `.dnx-out/web-tests.txt`（文件时间 2026-10-07 05:20）里已有**完全相同的 2 个失败**，
  说明这是**稳定复现**、不是偶发，也不是本轮改动引入；
- CI 固定 `NODE_VERSION: "24.13.1"`，本机为 `24.21.0`：**CI 是否同样红，本机无法证实**（只能装一个 Node）。
  若 CI 绿而本机红，则说明该测试辅助函数对 Node 版本敏感，应按版本无关写法修（例如放弃 `isFile()`，
  或对候选路径 `statSync`）。

### 6.2 P2 — 覆盖率 0% 的模块集中在持久化与装配层

见 §3.4 第 1–4 名（`db/repositories/reference_network.py`、`application/data_products.py`、
`application/data_platform_snapshots.py`、`db/repositories/decision.py`，合计 532 条语句 0% 覆盖）。
它们不是"冷门工具函数"，而是决策/数据产品的落库路径。建议把它们作为**评审盲区清单**，
而不是通过加覆盖率阈值来"解决"。

### 6.3 P1 — 公开 HEAD 仍带出 `.automation` 清单的乱码名残留文件（CA-08 直接相关）

```
命令: git ls-files | Select-String 'eek-homemodels'
输出: "eek-homemodels.json\357\200\242 `"

命令: git ls-tree HEAD | Select-String 'eek'
输出: 100644 blob ec8160ac8ba0a9261911ce8e3686996ccc20be09  "eek-homemodels.json\357\200\242 `"

命令: Get-ChildItem -Force -File | Where Name -like 'eek*' | ForEach { 打印码点 }
输出: 码点 = U+0065…U+006E,F022,' ','`'   （即 eek-homemodels.json + U+F022 + 空格 + 反引号）
      len=4704

命令: git log --oneline -2 -- "<该路径>"
输出: 334c882 chore: establish Architecture V2 autonomous development baseline

命令: Get-Content -LiteralPath <该文件>
输出（节选）:
 .automation/.gitignore                             |   5 +
 .automation/README.md                              |  12 +
 .automation/SECURITY.md                            |  10 +
 .automation/codex/deepseek_model_catalog.json      |  35 +++
 .automation/prompts/deepseek_worker_prefix.md      |  21 ++
 .automation/scripts/supervisor.py                  |  92 +++++++
 ...
 65 files changed, 3757 insertions(+)
```

**性质**：这是把 `git diff --stat` 误重定向进文件、且文件名被乱码化成 "…json<U+F022> `" 的**事故产物**，
在提交 `334c882` 进入公开 HEAD 并**至今仍在跟踪**。它的内容恰好是审计 CA-08 要求移除的
`.automation` 目录清单（38 条 automation 路径 + 工程文档树形清单），会被 GitHub 自动源码 tarball
以及任何 `git archive HEAD` 带出客户可见渠道。

**与 CA-08 的关系**：`.automation` 目录本身已不跟踪（该做的做了），但"从源码归档排除自动化"的意图
被这个残留文件破坏 → 这是 CA-08 判"部分闭环"的直接依据。

**修复方向（不在本报告写入范围）**：`git rm` 该文件并提交；若担心公开历史，注意审计明确
"不要重写公开历史"，因此**只从 HEAD 移除**即可，历史对象保留。

---

## 7. 核验边界（哪些事本报告没有证明）

1. **没有执行 release workflow。** G1 的同 SHA GitHub API 反查、G19 的镜像内执行、最终证据组装，
   都只在单元/契约层（`tests/release/*`）与 workflow 文本层被证明，**没有真实 run 的端到端记录**。
2. **没有重跑浏览器验收 sweep。** 本机 8000/3000 端口当时已被另一位成员的运行实例占用
   （`port=8000 pid=10664`、`port=3000 pid=8268`），我启动的 Vite 被挤到 3001，因此**主动放弃**重复启动服务与
   重复 sweep，避免与在跑的实例互相污染（sweep 会写 `artifacts/uat-browser` 并可能重盖章 UAT fixture）。
   **CA-09 的自动化侧因此是"接线已核实 + 未本机重跑"，人工侧仍是审计的开放项。**
3. **没有做原生安装**（干净 Windows 上 Install/Repair/Uninstall）与**没有做容器启动+迁移+认证 smoke**。
4. **没有验证 `.automation` 本地副本是否另有备份**（工作区内 `Test-Path .automation` 为 False）。
5. **没有多 Node 版本对照**：前端失败只能归因到 bundled Node v24.21.0 的 Dirent 行为，
   CI 的 24.13.1 是否受影响未证实（§6.1）。
6. **被核验对象是脏工作树**，不是可复现的提交；`git status` 的 32 改 + 28 新增在核验窗口内持续变动
   （已出现"窗口内新增 2 个测试文件导致收集数 +9"的事实，§3.3）。

---

## 8. 复现命令总表

```powershell
# 0) 环境
$root = 'C:\Users\qqshu\Desktop\Dev Work\EurogasNexus'
$py   = 'C:\Users\qqshu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$node = 'C:\Users\qqshu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
$env:PYTHONPATH = "$root\.dnx-cov;$root\.dnx-deps;$root\src;$root\packages\python-sdk\src"
Set-Location $root

# 1) 静态检查
& "$root\.dnx-deps\bin\ruff.exe" check .                             # 期望: All checks passed! exit 0
& $py -m pytest -q tests/contract/test_local_workspace_hygiene.py   # 6 passed
git check-ignore -v .dnx-cov                                        # exit 0

# 2) 覆盖率
$env:COVERAGE_FILE = "$root\.dnx-out\.coverage-eng"
& $py -m pytest -q tests/unit tests/domain tests/contract tests/sdk tests/cli tests/security `
  tests/optimization tests/ingestion tests/evals tests/streaming tests/workflow tests/uat tests/release `
  --cov=eurogas_nexus --cov-report=term "--cov-report=json:$root\.dnx-out\coverage-eng.json"
& $py .dnx-out\cov_lowest.py .dnx-out\coverage-eng.json             # TOTAL + 最低 10 模块

# 3) 按目录明细
& $py -m pytest -q tests/unit tests/domain tests/contract tests/sdk tests/cli tests/security `
  tests/optimization tests/ingestion tests/evals tests/streaming tests/workflow tests/uat tests/release `
  "--junitxml=$root\.dnx-out\junit-eng.xml"
& $py .dnx-out\junit_by_dir.py .dnx-out\junit-eng.xml

# 4) 三把哈希锁安装 + import
& $py -m pip install --require-hashes --target .dnx-verify\eng-runtime -r requirements-runtime.lock
& $py -m pip install --require-hashes --target .dnx-verify\eng-build   -r requirements-build.lock
& $py -m pip install --require-hashes --target .dnx-verify\eng-full    -r requirements.lock
$env:PYTHONPATH = "$root\.dnx-verify\eng-runtime"; & $py -c "import fastapi,sqlalchemy,alembic,pydantic,pg8000,cryptography;print('ok')"
$env:PYTHONPATH = "$root\.dnx-verify\eng-build";   & $py -c "import pip_audit,setuptools,wheel;print('ok')"
$env:PYTHONPATH = "$root\.dnx-verify\eng-full";    & $py -c "import pytest,yaml,rdflib,pyarrow,fastapi;print('ok')"

# 5) 活库迁移 + integration + api 两批
$env:RUNTIME_STORE_DATABASE_URL = 'postgresql+pg8000://nexus:nexus@127.0.0.1:51356/nexus_verify'
$env:PYTHONPATH = "$root\.dnx-deps;$root\src;$root\packages\python-sdk\src"
& $py -m alembic upgrade head ; & $py -m alembic current            # 0039_identity_api_key_hash_width (head)
$env:EUROGAS_NEXUS_ACK_INTEGRATION_TEST='1'; $env:EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST='1'
$env:EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST='1'
& $py -m pytest -q tests/integration                                 # 143 passed
# tests/api：按文件名字母序对半，分两批（命令见 §5.1）              # 189 + 282 passed

# 6) CA 定点证明
& $py .dnx-out\proof_ca01_ca02.py                                    # CA-01/CA-02 负例
& $py -m pytest -q tests/release/test_deployment_roles.py tests/release/test_release_dry_run.py   # CA-10: 27 passed

# 7) 运营 bundle 真实构建（CA-04 / CA-10）
& $py scripts\release\package_deployment_bundle.py .dnx-out\bundle-ca04 `
  --release-context .dnx-out\bundle-context.json --image-digest ("sha256:" + ("a"*64))

# 8) 前端与双语门禁（CA-03）
Set-Location clients\web ; & $node --test "tests/*.test.ts"          # 当前 exit 1（§6.1）
Set-Location $root ; & $py scripts\uat\check_i18n_parity.py          # exit 0
```

---

## 9. 结论

- **CA-01 / CA-04 / CA-07 / CA-10 已闭环**，每一项都有本机实跑的命令与输出（§1）。
- **CA-02 / CA-03 / CA-05 / CA-06 / CA-08 部分闭环**，剩余缺口已在各节明确列出：
  非密码学 provenance 与未配置的外部审批身份（CA-02）、前端套件红与无同 SHA 端到端证据（CA-03）、
  持久化服务身份/双人控制/组织隔离未构建（CA-05）、镜像启动+迁移+认证 smoke 未做（CA-06）、
  公开 HEAD 的 `.automation` 清单残留文件（CA-08）。
- **CA-09 仍开放**，且属于工程证据无法闭合的验收阻塞项。
- 覆盖率 **75.21%（27943 statements / 6926 missed，366 文件）**独立复现成功，与前一轮完全一致；
  覆盖率**不作为门禁阈值**，理由见 §3.5。
- 静态检查在修复后 **exit 0**；三把哈希锁**真实安装且可 import**；`alembic upgrade head` 在活库**成功**；
  活库 integration **143 passed**，`tests/api` 两批 **471 passed**。
- **最重要的一条**：`npm test`（release 打包前的硬门禁）当前**为红**，根因是测试辅助函数依赖了
  Node 递归 Dirent 的类型字段（§6.1）；它会阻塞 G4 前端证据产出，应优先处理。
