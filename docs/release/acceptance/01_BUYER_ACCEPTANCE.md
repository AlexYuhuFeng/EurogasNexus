# 01 — 甲方验收意见：Eurogas Nexus 供应商交付软件

> **English abstract (added 2026-10-30; the record below is unchanged and in its original
> language).** Buyer acceptance of the supplier-delivered software, audited on 2026-10-07
> against a working copy with uncommitted changes. Every figure was reproduced by commands
> run on the auditor's machine; supplier documents were treated as claims only.
> **Verdict: REJECT.** The engineering evidence was substantial, but legal and commercial
> deliverability decided the outcome (§8).

| 项目 | 内容 |
| --- | --- |
| 文档性质 | 采购方（甲方）对供应商交付软件的正式验收意见 |
| 审计日期 | 2026-10-07 |
| 被审对象 | 工作副本 `HEAD = b9977bc35cad2f89f9a9363fd001a6cc825f533d` **加上未提交的 28 个已修改文件 + 26 个未跟踪文件** |
| 最新已发布制品 | `v0.5-preview-107-df3bde9`（2026-09-03 发布，落后 HEAD **438 个提交**） |
| 审计方法 | 不采信仓库既有文档的任何结论；每个数字由本机实际执行的命令产生；供应商文档只作为"供应商自述"这一事实被引用 |
| **验收结论** | **不接收（REJECT）** |
| 证据落盘 | `<repo>/.dnx-out/buyer-acceptance/`（已被 `.gitignore` 第 83 行 `/.dnx-*` 覆盖，不进入交付物） |

> **甲方立场声明。** 本意见判断的是"该软件能否作为供应商交付物被接收并投入生产使用"，不是"代码写得好不好"。
> 工程证据的充分程度与法律/商业上是否可交付是两件事。本次结论由后者决定，理由见 §8。

---

## 0. 审计基线与方法的三个硬约束

### 0.1 被审对象是一个脏工作副本

```
命令: git status --porcelain | Where-Object { $_ -match '^ M' }   →  28
命令: git status --porcelain --untracked-files=all | ...          →  26
命令: git diff --shortstat                                        →  28 files changed, 1028 insertions(+), 134 deletions(-)
命令: git rev-parse HEAD                                          →  b9977bc35cad2f89f9a9363fd001a6cc825f533d
```

未提交内容包含 `src/eurogas_nexus/core/config_contract.py`、`core/preflight.py`、`security/cookie_policy.py`、
`scripts/ci/generate_env_template.py`、`scripts/ci/check_config_contract.py`、`docs/release/VENDOR_REMEDIATION_ACCEPTANCE.md` 等
—— 即供应商自己标注为"Fixed and verified"的那一整批整改。

**后果（本意见的最重要前提）：**

1. 我测到的任何通过，测的是**工作副本**，不是 HEAD，更不是任何已发布制品。
2. 已发布的最新制品 `df3bde9` 既不含这 28+26 处改动，也不含其后的 438 个提交。
3. **被审状态没有不可变身份**：没有 tag、没有 commit 能唯一指向"我审的这一份"。审计对象不可复现。

```
命令: git rev-list --count df3bde9..HEAD           →  438
命令: git tag -l | Measure-Object -Line            →  51   (全部形如 v0.5-preview-N-<sha>)
```

### 0.2 供应商自述与实测不符的实例已经出现

本次审计中至少抓到一起可复算的公开数字错误，说明"不得采信既有文档结论"不是形式要求，见 §1 第 3 行。

### 0.3 三态分类规则（本节先声明，全文一致使用）

| 状态 | 定义 |
| --- | --- |
| **已闭环** | 本次审计中我用命令产出了证据，且该证据不依赖任何外部输入 |
| **需外部条件** | 仅靠修改被审修订版本身无法闭合；需要环境、凭据、runner、工具链、目标机器或第三方参与 |
| **不可由代码解决** | 必须由自然人或法人作出法律/商业/制度性行为才能闭合 |

> 说明：有一类事项（如"CI 里补一个证据写入点"）确实是代码活，但其**证据**必须在真机/托管 runner/扫描器上产生。
> 按本规则这类归入"需外部条件"，并在表中逐条写明缺的外部输入是什么。

---

## 1. 供应商自我定位 vs 实际可交付状态

供应商自述只作"供应商这么说"这一事实引用；"实测"列全部由本机命令产生。

| # | 供应商自述（出处） | 我的验证命令 | 实测 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | `Status: RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`，`Release marker: RELEASE CANDIDATE`（`docs/release/RELEASE_READINESS.md:13,15`） | `Get-Content docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`（第 3 行） | 同一仓库的验收报告开篇即 `**Status: NOT ACCEPTED.**`，并记录 2026-09-19 一轮 **140 处功能失败** | **自相矛盾**：一份说 RC，一份说未通过 |
| 2 | 同一文件第 5 行 2026-09-22 覆盖声明 `NOT APPROVED FOR CUSTOMER PRODUCTION` | `Select-String ... 19_COMMERCIAL_ACCEPTANCE_AUDIT.md -Pattern 'NOT APPROVED'` | 第 4 行：`Disposition: **NOT APPROVED FOR CUSTOMER PRODUCTION**` | **一致**（且与我的结论同向） |
| 3 | `OpenAPI public surface: **163 paths**`（`RELEASE_READINESS.md:53`；`SECURITY_ACCEPTANCE_EVIDENCE.md:12` 同数） | `python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"` | **`OPENAPI_PATHS 182`** | **不符，差 19 条**。供应商自己的整改记录 `VENDOR_REMEDIATION_ACCEPTANCE.md:344` 也写 182 —— 即其发布就绪文档已过期 |
| 4 | `python scripts/release/run_release_dry_run.py` 产出 `release-assets/release-manifest.json`、SPDX SBOM、`SHA256SUMS`、签名状态、漏洞证据（`RELEASE_READINESS.md:59-61`） | `python scripts/release/run_release_dry_run.py --channel rc --output-dir .dnx-out/buyer-acceptance/rc-dry-run` | SBOM 4 份 ✓、`SHA256SUMS` ✓、签名状态 `{}`（空）⚠、**`release-manifest.json` 未生成** ✗；步骤 `checksums-and-manifest` 报 `ok=true` 但 `validate-release-artifacts` 随后以 `FileNotFoundError: ...release-manifest.json` 失败 | **部分不符**，且存在"步骤自报成功、产物缺失"的内部不一致 |
| 5 | `Every successful release workflow publishes: ... release-manifest.json, SHA256SUMS, SPDX SBOM set, THIRD_PARTY_NOTICES.md, and GitHub attestation metadata`（`RELEASE_READINESS.md:162-170`） | GitHub Releases API 遍历全部 51 个 release 的 asset 名 | **51 个 release 中，`release-manifest` / `SHA256SUMS` / `spdx` / `sbom` / `NOTICES` / `attest` 命名的资产数为 0** | **不符（已被实证推翻）** |
| 6 | `python scripts/release/check_version_consistency.py` passes across ...（`RELEASE_READINESS.md:56-58`） | `python scripts/release/check_version_consistency.py` | 24 项全部 `ok`，`[exit=0]` | **一致** |
| 7 | 依赖版本哈希锁定（`RELEASE_READINESS.md:119-120`） | `Select-String .github/workflows/*.yml -Pattern 'pip install'` | 全部 10 处 Python 安装均为 `--require-hashes -r *.lock`；npm 全部为 `npm ci` | **一致** |
| 8 | Windows 代码签名 `unsigned_pending_external`，stable 受阻（`RELEASE_READINESS.md:149-150`） | `python scripts/release/validate_stable_release.py ...` | G17 状态 `PENDING_EXTERNAL` | **一致** |
| 9 | 本地 dry-run 门禁报告 fail-closed（`RELEASE_READINESS.md:66-77`） | 同上门禁校验命令 | `ok=false`，并且**拒绝**仅凭本地证据放行出版 | **一致**（机制有效） |

**§1 结论：** 供应商的工程自述在可机械校验处大体成立，但在**发布就绪文档的核心数字（API 面）**和**发布物清单**两处与实际不符；
且仓库内并存"RC"与"NOT ACCEPTED"两种状态声明。甲方不能以该文档作为接收依据。

---

## 2. 交付物清单完整性

| 交付项 | 状态 | 证据（命令与结果） |
| --- | --- | --- |
| **可安装件**（面向被审修订版） | **缺失** | `Get-ChildItem -Recurse -File -Include *.exe,*.deb,*.msi,*.zip,*.tar.gz,*.whl` → **0 个**（排除 `.dnx-*`/`node_modules`/`.git`）。`dist/releases/` 仅有 `.gitkeep`。RC dry-run 中 `package-windows`、`build-container`、`package-deployment` 三步均 `ok=false` |
| **可安装件**（历史预览版） | **部分具备** | 最新 51 个 release 全为 `prerelease=true`，最新一个 `v0.5-preview-107-df3bde9`（2026-09-03）含 AllInOne exe(74.3MB)/Client exe(2.2MB)/Server zip/Web tar.gz/amd64.deb/arm64.deb；**全部 `download_count=0`** |
| **SBOM** | **部分具备** | RC dry-run 产出 4 份 SPDX-2.3 + `sbom-manifest.json`（含各 lock 的 `sha256`）。但 `artifacts: {}`（无制品/镜像级覆盖），且许可证元数据大面积缺失，见下 |
| ├ SBOM 许可证元数据 | **部分具备（严重）** | `component_packages`：`desktop-rust` **0/434** 已声明、`python-runtime` **0/30** 已声明；即 **464/562 个组件无许可证表达式**（`license_unknown`） |
| ├ SBOM 验收声明 | **供应商自己未主张** | `sbom-manifest.json:inventory_scope.acceptance_note` = `lock-derived documents only; not artifact-complete SBOM coverage and not G10 acceptance` |
| **许可证与声明文件** | **部分具备** | `LICENSE`（1832B，专有许可）✓、`THIRD_PARTY_NOTICES.md` ✓。**无 EULA、无 SLA、无支持策略、无 EOL 政策**（`git ls-files` 匹配 `EULA|SLA|SUPPORT|EOL` 无法务文件） |
| **校验和 / 来源证明** | **部分具备（不足）** | dry-run 产出 `SHA256SUMS`（5 条）✓。但 51 个 release 中 **41 个完全没有校验和**，10 个仅对 1 个资产（AllInOne exe）提供 `.sha256`，其余 6 个资产（Client exe、Server zip、web tar.gz、两个 deb）无校验和；**0 个 release 带 attestation** |
| **版本化配置模板** | **已具备** | `python scripts/ci/check_config_contract.py` → `declared 69 / read 62 / templates 2`，`[exit=0]`；`python scripts/ci/generate_env_template.py --check` → `.env.example`、`deploy/runtime/env.server.example` 均 `ok`，`[exit=0]`。模板由 `config_contract.py` 生成，非手写 |
| **安装 / 升级 / 灾备手册** | **已具备（文档层面）** | `docs/release/INSTALL_WINDOWS.md`、`INSTALL_LINUX.md`、`docs/operations/BACKUP_RESTORE.md`、`DISASTER_RECOVERY.md`、`RELEASE_ROLLBACK.md`、`docs/release/UPDATE_POLICY.md`、`SUPPLY_CHAIN.md`、`DEPLOYMENT_CONTRACT.md` 均 `Test-Path = True` |
| ├ 但升级与灾备**未演练** | **部分具备** | 门禁 G7（升级冒烟）、G13（备份/恢复）在 CI 中**无任何证据写入点**，见 §3 |
| **兼容性与支持策略** | **部分具备** | 有兼容性机制（`/api/runtime/release` 兼容元数据、`docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`）；**无支持策略、无受支持版本窗口、无 EOL 承诺**。`docs/operations/SLO.md:4` 与 `PERFORMANCE_BUDGET.md:32` 均自述 `not contractual SLAs` / `No contractual SLAs` |
| **发布说明与已知问题** | **部分具备** | `CHANGELOG.md` ✓、dry-run 生成 `release-notes.md` ✓、每个 preview release 带 body ✓。但最新 release 说明仍宣传已被废弃的 `sha-<commit>` 镜像标签（`RELEASE_READINESS.md:176` 明确该别名已退役）；**被审修订版没有任何发布说明或已知问题清单**（因为根本没发布） |

---

## 3. 放行门槛：哪些门禁 CI 无法自行产出证据

**权威来源：** `scripts/release/policy/stable_gate_policy.json`（19 个门禁：G1–G19）+ 实际运行校验器得到的门禁表。

```
命令: python scripts/release/validate_stable_release.py \
        --context .dnx-out/buyer-acceptance/rc-dry-run/release-context.json \
        --artifacts-dir .dnx-out/buyer-acceptance/rc-dry-run \
        --sbom-dir .dnx-out/buyer-acceptance/rc-dry-run/sbom \
        --evidence-dir .dnx-out/buyer-acceptance/rc-dry-run/release-evidence \
        --allow-local-dry-run-evidence --allow-missing-platform-artifacts
结果: [exit=1]
errors:
  - release-manifest.json missing
  - mandatory gates not satisfied for rc: G1, G2, G3, G5, G11, G12, G14, G19
```

### 3.1 实测门禁表（rc 通道，放开本地 dry-run 与缺件豁免后仍然失败）

| 门禁 | 名称 | 类型 | required_for | 实测状态 | `producers` |
| --- | --- | --- | --- | --- | --- |
| G1 | CI workflow | internal | all | PENDING_EXTERNAL | ci-verification, dry-run |
| G2 | Unit/integration tests | internal | all | PENDING_EXTERNAL | validate, dry-run |
| G3 | PostgreSQL migration | internal | all | PENDING_EXTERNAL | reliability, dry-run |
| G4 | Frontend build | internal | all | PASS | web, dry-run |
| G5 | Desktop packaging | internal | all | PENDING_EXTERNAL | **dry-run（仅此一个）** |
| G6 | Installer smoke | internal | stable | PENDING_EXTERNAL | **（空）** |
| G7 | Upgrade smoke | internal | stable | PENDING_EXTERNAL | **（空）** |
| G8 | Security tests | internal | all | PASS | validate, dry-run |
| G9 | Dependency vulnerability | internal | all | PASS | dependency-scan, dry-run |
| G10 | SBOM | internal | all | PASS | **dry-run（仅此一个）** |
| G11 | Provenance | internal | rc | PENDING_EXTERNAL | **dry-run（仅此一个）** |
| G12 | Checksums | internal | all | **FAIL** | assemble, dry-run |
| G13 | Backup/restore evidence | internal | stable | PENDING_EXTERNAL | **（空）** |
| G14 | Performance budget | internal | all | PENDING_EXTERNAL | reliability, dry-run |
| G15 | External security acceptance | **external** | stable | PENDING_EXTERNAL | **（空）** |
| G16 | Commercial provider certification | **external** | stable | PENDING_EXTERNAL | **（空）** |
| G17 | Windows code signing | **external** | stable | PENDING_EXTERNAL | **（空）** |
| G18 | User acceptance | **external** | stable | PENDING_EXTERNAL | **（空）** |
| G19 | Container acceptance by digest | internal | rc | PENDING_EXTERNAL | container-acceptance |

### 3.2 CI 到底能自己产出哪些门禁的证据

```
命令: Select-String -Path .github/workflows/*.yml -Pattern '--gate-id\s+(\S+)'
结果: release.yml 中 G2, G3, G14, G9, G4, G12, G19
      （另 release.yml:128 用 write_ci_run_evidence.py 写 G1；release.yml:155 用 run_security_evidence.py 写 G8）
命令: foreach ($g in @('G5','G6','G7','G10','G11','G13','G15','G16','G17','G18')) { ... }
结果: 全部 0 hit —— 这些门禁 ID 在任何 workflow 中都不出现
```

| 分类 | 门禁 | 数量 |
| --- | --- | --- |
| CI 有证据写入点 | G1, G2, G3, G4, G8, G9, G12, G14, G19 | **9** |
| `producers` 为空（无任何生产者） | G6, G7, G13, G15, G16, G17, G18 | **7** |
| `producers` 只有 `dry-run`（而 dry-run 是 `local_only: true`，校验器默认拒绝其证据放行出版） | G5, G10, G11 | **3** |
| **合计 CI 无法自行产出证据** | G5, G6, G7, G10, G11, G13, G15, G16, G17, G18 | **10 / 19** |

**stable 通道要求 17 个门禁**（`required_for ∈ {all, stable}`：G1–G5、G6–G10、G12–G18，共 10 个 `all` + 7 个 `stable`）。
其中 G5、G6、G7、G10、G13、G15、G16、G17、G18 共 **9 个在 CI 中完全没有产出路径**，
`stable` 因此在结构上无法通过门禁——这不是"还差一点证据"，是**流程缺环**。

### 3.3 外部门禁永远无法完成（空审批白名单）

```
命令: Get-Content scripts/release/policy/stable_gate_policy.json  (第 82 行)
结果: "authorized_external_approvals": []
```

策略文件自己写明：外部门禁必须"carries an approval identity configured in `authorized_external_approvals`"。
白名单为空 → **G15/G16/G17/G18 无论提交多少证据都不会被接受**，必须先由人配置审批身份。

### 3.4 两个必须记录的门禁行为缺陷

**(a) G9 在 rc/preview 通道"因未测量而变绿"。**

```
命令: python scripts/release/scan_vulnerabilities.py --channel stable   → ok:false, blocking=[5 个组件全列], [exit=1]
命令: python scripts/release/scan_vulnerabilities.py --channel rc       → ok:true,  blocking=[],            [exit=0]
```

两次运行的扫描明细**完全相同**：`container` = `TOOL_UNAVAILABLE`（无扫描器）、`desktop-node`/`web-node` = `SCAN_FAILED`（`command not found: npm.cmd`）、
`desktop-rust` = `TOOL_UNAVAILABLE`、`python-runtime` = `TOOL_UNAVAILABLE`。
即 **5 个组件一个都没扫成**，stable 诚实报 FAIL，rc 却报 PASS。RC 是可发布通道，这构成"未进行任何 CVE 扫描即可获得绿色漏洞门禁"。

**(b) stable 通道连发布上下文都解析不出来。**

```
命令: python scripts/release/run_release_dry_run.py --channel stable --output-dir .dnx-out/buyer-acceptance/stable-dry-run
结果: [exit=1]
RuntimeError: ...
release-context: Stable releases require a pushed semantic tag vX.Y.Z; workflow_dispatch stable is not permitted.
```

不存在 `vX.Y.Z` 形式的 tag（51 个 tag 全为 `v0.5-preview-*`），**stable 发布在第一步就被拒绝**——

**(c) 而 HEAD 的 CI 是红的，G1 因此不可能满足。**

```
命令: Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/runs?per_page=20
结果: total_count=606
  run 608  failure  2026-10-06  b9977bc  ← 当前 HEAD
  run 607  failure  2026-10-06  a0c8e60
  run 606  failure  2026-10-06  2b826e7
  ...连续 10 次 failure...
  run 597  success  2026-10-05  c08499f  ← 最近一次成功，HEAD 之前
```

G1 的规则是"re-derives the run from the read-only GitHub API ... requiring a completed successful run"。
HEAD 的 CI 运行结论为 `failure`，**即使所有外部证据齐备，stable 也不可能从被审修订版发布**。

---

## 4. LICENSE 授予的实际权利边界与合同义务

### 4.1 LICENSE 原文（`LICENSE`，1832 字节）

> "This repository is source-visible for review, demonstration, internal evaluation, and controlled collaboration only.
> **No license is granted to use, copy, modify, merge, publish, distribute, sublicense, sell, host, deploy, commercialize,
> or create derivative works from this software except under a separate written agreement signed by the copyright holder.**"

> "THE SOFTWARE AND DOCUMENTATION ARE PROVIDED "AS IS" FOR REVIEW AND EVALUATION PURPOSES ONLY. TO THE MAXIMUM EXTENT
> PERMITTED BY LAW, THE COPYRIGHT HOLDER **DISCLAIMS ALL WARRANTIES**, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, ACCURACY, AVAILABILITY, AND SUITABILITY FOR TRADING, LEGAL,
> ACCOUNTING, REGULATORY, OPERATIONAL, OR COMMERCIAL DECISIONS."

### 4.2 权利边界实测

| 甲方需要的权利 | LICENSE 是否授予 | 依据 |
| --- | --- | --- |
| 评估/演示/内部评测 | ✅ 授予 | 第 1 段 |
| 部署到生产环境 | ❌ **明确排除**（`deploy`、`host`） | 第 1 段 |
| 内部商业使用 | ❌ **明确排除**（`commercialize`） | 第 1 段 |
| 修改/衍生作品 | ❌ 排除 | 第 1 段 |
| 再分发/转授权/销售 | ❌ 排除 | 第 1 段 |
| 质保、适用性、可用性 | ❌ 全部免责 | 第 3 段 |
| 获得源码以外的东西（支持、更新、培训、文档） | ❌ 无任何承诺 | 全文无相关条款 |

**结论：按现有 LICENSE，甲方连"部署"和"商用"这两项最基本的交付权利都没有取得。**
必须先签署一份单独的书面协议；该协议在本仓库中不存在。

`VENDOR_REMEDIATION_ACCEPTANCE.md:489` 是供应商自己的同一结论（作为"供应商承认"引用，非我的依据）：
> "`LICENSE` grants no right to deploy or host. No support, warranty, upgrade or EOL commitment exists, and no breach-notification channel."

### 4.3 EULA / SLA / 支持 / 漏洞响应 / EOL / 责任限制

```
命令: git ls-files | Select-String -Pattern 'EULA|SLA|SUPPORT|EOL|LICENSE|NOTICE'
结果: LICENSE, THIRD_PARTY_NOTICES.md 及若干代码/测试文件名 —— 无任何 EULA/SLA/支持政策/EOL 文件
命令: Select-String docs/release/*.md,docs/operations/*.md -Pattern 'support policy|EOL|SLA'
结果: 仅命中"SLA"一词，且全部用于自述"不是合同 SLA"（SLO.md:4, PERFORMANCE_BUDGET.md:32, PERFORMANCE_BASELINE.md:4）
```

| 合同要素 | 是否存在 | 实测依据 |
| --- | --- | --- |
| EULA / 最终用户许可协议 | **无** | 文件不存在 |
| SLA（服务水平协议） | **无** | 仅 `SLO.md`/`PERFORMANCE_BUDGET.md`，且自述"非合同 SLA" |
| 支持承诺（渠道、时限、级别） | **无** | 无支持政策文件 |
| 漏洞响应承诺（时限/联络/披露流程） | **无实质承诺** | `SECURITY.md` 只写"Report them through the private project security channel for the repository owner"，**无地址、无邮箱、无响应时限、无披露期限** |
| EOL / 版本支持周期 | **无** | 无相关政策；`UPDATE_POLICY.md` 只描述更新机制，未承诺支持多久 |
| 责任限制 / 赔偿 / 保险 | **无**（仅单方全免责） | LICENSE 第 3 段为供应商单方免责，无对甲方的救济条款 |
| 数据处理 / 保密协议 | **无** | 无相关文件；且仓库为**公开仓库**（见 §5），保密性无制度保障 |

---

## 5. 供应商主体风险

### 5.1 作者与提交

```
命令: git rev-list --count HEAD                 → 659
命令: git shortlog -sne --all
  659  Fluffy Dog <qqshuyy@gmail.com>
```

**唯一作者、单一提交者、659 个提交。** 无第二贡献者，无代码评审的第二双眼睛（从 git 历史无法证明），无"巴士因子"缓冲。

```
命令: git log --reverse --format="%ad %an" --date=short | Select-Object -First 1   → 2026-05-26
命令: git log -1 --format="%ad %an %s" --date=short                                → 2026-10-06
```
开发周期约 4 个月。

### 5.2 托管位置与主体性质

```
命令: git remote -v
  origin  https://github.com/AlexYuhuFeng/EurogasNexus.git (fetch/push)

命令: Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus
  "private": false,  "visibility": "public"
  "owner": { "login": "AlexYuhuFeng", "type": "User" }     ← 个人账号，非 Organization
  "license": { "key": "other", "spdx_id": "NOASSERTION" }  ← GitHub 无法归类为任何标准许可证
  "created_at": "2026-05-26", "pushed_at": "2026-10-06"
  "stargazers_count": 1, "forks_count": 0, "open_issues_count": 0, "has_downloads": false
```

| 风险 | 事实 |
| --- | --- |
| **无法律主体** | 托管在个人 GitHub 账号下（`type: User`），无组织/公司实体可签约、可被追责、可开票、可承担赔偿责任 |
| **公开仓库 vs 专有软件** | 仓库为 `public`。LICENSE 声明专有，但**任何人都可以读取全部源码**（含 438 个未发布提交）。甲方为独占性/保密性付费的理由不成立 |
| **许可证不可识别** | GitHub 返回 `NOASSERTION`，CI/合规工具无法自动识别许可义务，甲方合规团队需人工介入 |
| **无源代码托管（escrow）** | 无托管协议、无第三方托管安排。若作者停止维护，甲方无任何接管途径 |
| **无连续性安排** | 无公司、无托管、无第二维护者、无交接文档承诺（`docs/deployment/HANDOVER_INDEX.md` 是技术交接索引，不是组织连续性承诺） |

### 5.3 发布史：整批整改从未交付

```
命令: git tag -l | Measure-Object -Line                                    → 51（全部 v0.5-preview-N-<sha>）
命令: Invoke-RestMethod .../releases?per_page=100
  release count=51;  prerelease=51;  draft=0
  最新: v0.5-preview-107-df3bde9  published=2026-09-03
命令: Invoke-RestMethod .../actions/workflows/release.yml/runs?per_page=15
  total_count=107;  最新一次 run 107 = success @ df3bde9, 2026-09-03
  （2026-09-03 之后 release.yml 未再运行）
命令: git rev-list --count df3bde9..HEAD                                   → 438
```

**结论：51 个发布全部是 `prerelease`；0 个 stable 发布；release 流水线自 2026-09-03 起停摆；已发布制品落后 438 个提交，且不含当前工作副本里那 28+26 处未提交改动。**

### 5.4 无合法市场数据（产品可用性的根问题）

```
命令: Get-ChildItem src/eurogas_nexus/ingestion/connectors -File
  base.py  cost_source.py  ecb.py  eex.py  entsog.py  gie.py  ice_ocm.py  trayport.py  weather.py
命令: Get-Content src/eurogas_nexus/ingestion/connectors/{eex,ice_ocm,trayport,weather,ecb,entsog,gie}.py
命令: Get-Content src/eurogas_nexus/ingestion/connectors/base.py
```

实测：**EEX、ICE OCM、Trayport、Weather、ECB、ENTSOG、GIE 七个连接器全部是 `MockConnector` 的子类**，
`MockConnector.fetch()` 固定返回 `raw_data=[]`（空载荷）。文件自述如 `"Mock Weather connector — returns empty payloads by default"`。

即：甲方若为"欧洲天然气市场数据终端"付费，实际交付的是一个**没有任何授权市场数据的壳**。
这不是代码缺陷，是**数据权利问题**——供应商无数据权利可授予。对应门禁 G16（`Commercial provider certification`，`producers: []`）。

---

## 6. 三类状态汇总

| 状态 | 项目数 |
| --- | --- |
| **已闭环** | **9** |
| **需外部条件** | **13** |
| **不可由代码解决** | **9** |
| 合计 | 31 |

> §6.3 的表按"缺什么"列出 11 行，其中 ②（许可证）与 ④（支持/漏洞响应）各含 2 行，
> 归并为 **9 个类别**：①法律主体 ②LICENSE/EULA ③SLA ④支持与漏洞响应 ⑤EOL ⑥责任限制 ⑦代码签名证书 ⑧源码托管 ⑨数据权利。

### 6.1 已闭环（9 项，均以本机命令产出证据）

| # | 事项 | 证据命令 | 结果 |
| --- | --- | --- | --- |
| C1 | 版本一致性契约（24 个面） | `python scripts/release/check_version_consistency.py` | 全部 ok，exit 0 |
| C2 | 环境变量配置契约 | `python scripts/ci/check_config_contract.py` | 69 declared / 62 read / 2 templates，exit 0 |
| C3 | 配置模板与契约同步 | `python scripts/ci/generate_env_template.py --check` | 2/2 ok，exit 0 |
| C4 | 依赖哈希锁定 | `Select-String .github/workflows/*.yml -Pattern 'pip install\|npm ci'` | Python 全 `--require-hashes`；npm 全 `npm ci` |
| C5 | Python 测试可收集 | `python -m pytest --collect-only -q tests` | `3260 tests collected in 12.56s` |
| C6 | SPDX SBOM 生成机制 | RC dry-run | 4 份 SPDX-2.3 + lock `sha256` + `inputs` 溯源 |
| C7 | 门禁校验器 fail-closed | `python scripts/release/validate_stable_release.py ...` | exit 1，拒绝仅凭本地证据放行 |
| C8 | release.yml 的 9 个证据写入点存在 | `Select-String .github/workflows/*.yml -Pattern '--gate-id'` + `write_ci_run_evidence` / `run_security_evidence` | G1,G2,G3,G4,G8,G9,G12,G14,G19 |
| C9 | 安装/升级/回滚/灾备/更新/供应链/部署契约七份手册齐备 | `Test-Path` 逐项 | 7/7 True |

### 6.2 需外部条件（13 项）

| # | 缺什么 | 外部条件是什么 |
| --- | --- | --- |
| E1 | G1：HEAD 同 SHA 的绿色 CI 运行（当前 `failure`） | 先修好 CI 并推送到 GitHub，由托管 runner 产生成功运行 |
| E2 | G2：全量 Python 套件在 CI 实跑的证据 | CI runner；本机只验证了收集（3260），未跑全量 |
| E3 | G3：PostgreSQL 迁移 + DB 冒烟 | 目标运行时库（PostgreSQL 16），`alembic upgrade head` |
| E4 | G5：桌面打包证据（CI 无写入点，只有 dry-run） | Tauri/NSIS/DEB 工具链 + Windows/Linux/ARM64 runner；须在 CI 增加 G5 写入点 |
| E5 | G6：干净 Windows 安装/启动/卸载冒烟（`producers: []`） | 受控 Windows 测试机；须新增证据写入点 |
| E6 | G7：上一版本 → 新版本升级冒烟（`producers: []`） | 需存在"上一版本"制品 + 测试机；被审修订版无任何制品 |
| E7 | G11：来源证明 / GitHub OIDC attestation（仅 dry-run 生产者） | 托管 CI 的 OIDC 身份；本地无法产生 |
| E8 | G12：校验和门禁 FAIL + `release-manifest.json` 缺失 | 修复打包步骤（`checksums-and-manifest` 自报成功但产物不存在），并在真实打包后重跑 |
| E9 | G13：备份/恢复演练证据（`producers: []`） | 真实部署环境 + 演练窗口；须新增证据写入点 |
| E10 | G14：性能预算证据 | 真实部署规模的负载环境（本机 dry-run 为 PENDING_EXTERNAL） |
| E11 | G19：容器按 digest 验收 | 已推送到 GHCR 的镜像 digest（本地构建 id 不构成证据） |
| E12 | G15：外部安全验收 | 甲方或第三方渗透测试团队出报告 |
| E13 | G18：真实交易员 UAT | 甲方业务用户 + 可用的受权数据（见 §5.4） |

### 6.3 不可由代码解决（9 类 / 11 行）

| # | 类别 | 缺什么 | 需要谁提供 | 提供后如何验证 |
| --- | --- | --- | --- | --- |
| L1 | ① 法律主体 | **无公司/组织实体**，托管在个人 GitHub 账号（`type: User`） | 供应商法人（营业执照/公司注册号/签约代表） | 核验营业执照与签约授权书；在合同签署主体名下开票与收款；`git remote` 指向组织账号且管理员为组织成员 |
| L2 | ② 许可证 | **LICENSE 的部署与商用授权**：现许可明确排除 `deploy`/`host`/`commercialize` | 版权持有人（Alex Yuhu Feng）签署的书面许可/转让协议 | 仓库内出现经签署的许可协议；其授予条款覆盖部署、商用、修改、衍生作品、再分发；由甲方法务书面确认与现行 LICENSE 不冲突 |
| L3 | ② 许可证 | **EULA 缺失** | 供应商法务 | EULA 文本入库并随安装包分发；条款含许可范围、限制、终止、审计权 |
| L4 | ③ SLA | **SLA 缺失**：仅有自述"非合同 SLA"的 SLO | 供应商商务 | 签署含可用性目标、度量口径、统计周期、未达标补救（服务信用/退款）的 SLA；抽样核对监控口径可复算 |
| L5 | ④ 支持 | **支持承诺缺失**：无渠道、无时限、无级别 | 供应商商务 | 合同中写明支持级别、响应/恢复时限、升级路径、联络方式；由甲方运维试单验证渠道可达 |
| L6 | ④ 漏洞响应 | **漏洞响应承诺缺失**：`SECURITY.md` 无地址、无时限、无披露期 | 供应商安全负责人 | 书面漏洞响应政策（受理渠道、确认时限、修复时限、协调披露期）；用一次演练提交验证受理与时限 |
| L7 | ⑤ EOL | **EOL / 版本支持周期缺失** | 供应商产品负责人 | 书面支持周期政策（版本受支持月数、弃用提前通知期）；核对 `UPDATE_POLICY.md` 与合同一致 |
| L8 | ⑥ 责任限制 | **责任限制/赔偿/保险**：现文本为单方全免责 | 双方商务与法务 | 合同中的责任上限、赔偿、保密、数据处理、保险条款；由甲方风控出具书面接受意见 |
| L9 | ⑦ 代码签名证书 | **Windows 代码签名证书**（门禁 G17） | 供应商（须以组织身份持有的 OV/EV 代码签名证书） | 用 `signtool verify /pa /v` 或 PowerShell `Get-AuthenticodeSignature` 在交付的 `.exe` 上验出**组织名与合同主体一致**的签名及可信时间戳 |
| L10 | ⑧ 源码托管 | **源代码托管 / 连续性安排**：无 escrow、无主体、无第二维护者（659 提交 / 1 作者） | 供应商 + 第三方托管机构 | 签署源码托管协议与触发条件；托管方出具持有证明；至少再增加一名有提交权的维护者 |
| L11 | ⑨ 数据权利 | **合法市场数据权利**（门禁 G16）：7 个商业连接器全部为 `MockConnector` 返回空载荷 | 供应商**无法提供**——须由甲方自行取得 EEX/ICE/Trayport/Weather 等许可 | 供应商出具数据授权证明，或合同明确列为甲方自负责任；连接器从 mock 切换为真实实现并有 live 接入验收记录 |

---

## 7. 已闭环 / 需外部条件 / 不可由代码解决 的分布判断

- **工程基本面是真实的**：C1–C9 九项均由我本机复算通过。版本一致性、配置契约、依赖哈希锁定、SBOM 生成、门禁 fail-closed
  这些机制确实存在且有效。供应商的工程记录在可机械校验处基本诚实。
- **但可发布性是零**：stable 通道要求 17 个门禁，当前**一个都不满足**；19 个门禁里 **10 个 CI 根本没有产出路径**；
  4 个外部门禁因 `authorized_external_approvals: []` 永远无法完成；HEAD 的 CI 运行是 `failure`；stable dry-run 在解析发布上下文时即被拒绝。
- **且已交付的版本不存在**：没有任何制品对应被审修订版，最新发布落后 438 个提交 + 28/26 处未提交改动。
- **最根本的一条与代码无关**：LICENSE 不授予部署与商用权利，无主体、无 SLA、无支持承诺。
  即使把上面所有工程门禁都做绿，甲方仍然**无权合法使用这套软件**。

---

## 8. 验收结论

# **不接收（REJECT）**

**判定理由（按决定性排序）：**

1. **法律上不可交付。** `LICENSE` 明确排除 `deploy`、`host`、`commercialize`，且无独立书面协议。
   按现状，甲方取得交付物后无权部署、无权商用。这不是可以通过验收委员会放宽的技术项。
2. **无合同主体。** 供应商是个人 GitHub 账号（`type: User`），无公司实体，无签约、开票、赔偿、被追责的对象。
3. **无任何合同保障。** 无 EULA、无 SLA、无支持承诺、无漏洞响应时限、无 EOL 政策、无责任限制条款（仅单方全免责）。
4. **没有可交付的版本。** 0 个 stable 发布；51 个发布全为 prerelease；最新制品落后 HEAD 438 个提交；
   被审修订版含 28 个已修改 + 26 个未跟踪文件且无 tag，**审计对象不可复现、不可复算**。
5. **发布流程在结构上无法通过。** stable 需 17 个门禁、19 个门禁中 10 个无 CI 产出路径、4 个外部门禁白名单为空、
   最新 stable dry-run 在解析上下文即被拒绝、HEAD 的 CI 为 `failure`。
6. **产品核心价值不成立。** 七个商业数据连接器全部返回空载荷（`MockConnector`），供应商无数据权利可授予；
   为"市场数据终端"付费却收到无数据的壳。
7. **供应商自己的文档也记录了同样的结论**：`19_COMMERCIAL_ACCEPTANCE_AUDIT.md:4` = `NOT APPROVED FOR CUSTOMER PRODUCTION`；
   `FUNCTIONAL_ACCEPTANCE_REPORT.md:3` = `**Status: NOT ACCEPTED.**`。甲方无需推翻供应商的判断，只需确认它。

### 8.1 放行前必须闭环的条件（未全部满足则维持"不接收"）

**A 组——法律与合同（不可由代码解决，缺一不可，任一未闭环则直接否决）**

| 编号 | 条件 |
| --- | --- |
| A1 | 签约主体为依法登记的公司/组织，提供营业执照与授权代表证明 |
| A2 | 签署书面许可协议，明确授予**部署、商用、修改、衍生、再分发**权利，并声明与现行 `LICENSE` 的冲突以协议为准 |
| A3 | 交付 EULA 并随安装包分发 |
| A4 | 签署 SLA，含可用性目标、度量口径、未达标补救 |
| A5 | 书面支持政策：渠道、响应/恢复时限、升级路径 |
| A6 | 书面漏洞响应政策：受理渠道、确认时限、修复时限、协调披露期 |
| A7 | 书面 EOL / 版本支持周期政策 |
| A8 | 合同含责任上限、赔偿、保密、数据处理条款，经甲方风控书面接受 |
| A9 | 源码托管（escrow）协议，或等价的组织连续性安排（第二维护者 + 交接承诺） |
| A10 | 数据权利落定：供应商出具授权证明，**或**合同明确将数据许可列为甲方自负责任且产品定位相应调整 |

**B 组——交付物与发布门禁（可由代码加外部环境解决）**

| 编号 | 条件 |
| --- | --- |
| B1 | 修复 CI 使 HEAD 的 `ci.yml` 运行为 `success`，且 G1 要求的 5 个必需 job 全部成功 |
| B2 | 提交全部未提交改动，建立不可变 tag（`vX.Y.Z`），使被审对象可复现、可复算 |
| B3 | 为 G5/G6/G7/G10/G11/G13 在 CI 增加证据写入点，并使 `producers` 非空 |
| B4 | 安装并运行容器 CVE 扫描器（trivy/grype 等），消除 G9 在 rc/preview 通道"未扫即绿"的行为 |
| B5 | 修复 `checksums-and-manifest` 步骤自报成功却不产出 `release-manifest.json` 的问题，使 G12 转 PASS |
| B6 | 在 `authorized_external_approvals` 中配置审批身份，使 G15–G18 可被判定 |
| B7 | 产出真实可安装件（Windows NSIS、Linux x64/ARM64 DEB、Server ZIP、API 镜像 digest），每个资产均带校验和 |
| B8 | **实测补齐**：在干净 Windows 机上完成安装/启动/卸载冒烟（G6）与上一版本升级冒烟（G7），并留证 |
| B9 | 在目标环境完成备份/恢复演练（G13）与性能预算复测（G14） |
| B10 | SBOM 补齐许可证元数据（当前 `desktop-rust` 0/434、`python-runtime` 0/30 未声明）并做到制品级覆盖 |
| B11 | 将发布物清单（manifest、SHA256SUMS、SBOM、NOTICES、attestation）**实际作为 release 资产发布**，而非仅在文档中声明 |
| B12 | 修正 `RELEASE_READINESS.md:53` 的 API 面数字（163 → 实测 182），消除与 `VENDOR_REMEDIATION_ACCEPTANCE.md:344` 的自相矛盾 |

**C 组——验收证据（必须在甲方环境或由甲方参与产生）**

| 编号 | 条件 |
| --- | --- |
| C1 | 外部渗透测试报告 + 在甲方环境复跑依赖 CVE 扫描（G15） |
| C2 | 真实企业 IdP 验收（OIDC issuer/JWKS/TLS/redirect URI 逐项核对） |
| C3 | 真实交易员 UAT 签字（G18），且必须在有受权数据的部署上进行 |
| C4 | 浏览器功能验收在真实环境实际跑通（本机 Playwright 未安装，供应商自己记录"no live browser run was performed"） |

### 8.2 可考虑"有条件接收"的路径（供甲方决策参考，非本次结论）

若甲方出于商务原因必须在 A 组未完全闭环时推进，**最低可接受形态**是：
仅作为**受限评估用途**接收（禁止生产部署、禁止商用、禁止对外交付），并同时满足 B1、B2、B7、B11 与 C4。
这需要甲方书面确认接受"A 组全部风险由甲方自担"，且不得对外称该软件为"已验收交付"。
本审计**不建议**采用该路径。

---

## 附录 A — 本次审计执行的命令清单

```powershell
# 仓库与主体
git rev-list --count HEAD
git shortlog -sne --all
git tag -l
git remote -v
git status --porcelain
git status --porcelain --untracked-files=all
git diff --shortstat
git rev-list --count df3bde9..HEAD
Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus
Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus/releases?per_page=100
Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus/actions/workflows/ci.yml/runs?per_page=20
Invoke-RestMethod api.github.com/repos/AlexYuhuFeng/EurogasNexus/actions/workflows/release.yml/runs?per_page=15

# 交付物
Get-ChildItem -Recurse -File -Include *.exe,*.deb,*.msi,*.zip,*.tar.gz,*.whl
Get-ChildItem -Recurse -File -Include *.spdx,*.spdx.json,*SHA256SUMS*,sbom*.json
Get-ChildItem -Recurse release-assets,dist,artifacts,output -File
git ls-files | Select-String -Pattern 'EULA|SLA|SUPPORT|EOL|LICENSE|NOTICE'

# 门禁与发布
python scripts/release/validate_stable_release.py --context ... --artifacts-dir ... --sbom-dir ... --evidence-dir ... --allow-local-dry-run-evidence --allow-missing-platform-artifacts
python scripts/release/run_release_dry_run.py --channel rc     --output-dir .dnx-out/buyer-acceptance/rc-dry-run
python scripts/release/run_release_dry_run.py --channel stable --output-dir .dnx-out/buyer-acceptance/stable-dry-run
python scripts/release/scan_vulnerabilities.py --channel stable
python scripts/release/scan_vulnerabilities.py --channel rc
Select-String -Path .github/workflows/*.yml -Pattern '--gate-id\s+(\S+)'
Select-String -Path .github/workflows/*.yml -Pattern 'pip install|npm ci'

# 工程基本面复算
python scripts/release/check_version_consistency.py
python scripts/ci/check_config_contract.py
python scripts/ci/generate_env_template.py --check
python -m pytest --collect-only -q tests
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"

# 产品实质
Get-Content src/eurogas_nexus/ingestion/connectors/{base,eex,ice_ocm,trayport,weather,ecb,entsog,gie}.py
```

**环境：** `PYTHONPATH=<repo>\.dnx-deps;<repo>\src;<repo>\packages\python-sdk\src`，
解释器 `C:\Users\qqshu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`。

## 附录 B — 证据文件

| 路径 | 内容 |
| --- | --- |
| `.dnx-out/buyer-acceptance/rc-dry-run/` | RC 通道 dry-run 全部产物：`release-context.json`、`SHA256SUMS`、`signing-state.json`（空）、`release-notes.md`、`release-evidence/*.json`、`sbom/*.spdx.json` |
| `.dnx-out/buyer-acceptance/rc-dry-run/release-dry-run-report.json` | 17 个步骤的逐项 ok/fail（7 个失败） |
| `.dnx-out/buyer-acceptance/rc-gate-report.json` | 19 个门禁的实测状态表（本次审计的核心证据） |
| `.dnx-out/buyer-acceptance/stable-dry-run.log` | stable 通道被拒的完整输出 |
| `.dnx-out/buyer-acceptance/gates.py`、`gates2.py`、`ev.py`、`sbom.py`、`rep.py` | 解析上述 JSON 的临时脚本 |

## 附录 C — 本意见的局限

1. 全部测量在**脏工作副本**上进行，不等于 HEAD、不等于任何已发布制品。见 §0.1。
2. 我未运行全量 Python 测试套件（只验证了可收集数 3260），未运行 Web 测试与构建，未安装 Playwright，
   未做真实浏览器验收。这些项目的状态依据是供应商自述 + 仓库中的测试代码，**不构成我的实测**。
3. 我未验证 `resources/app.asar` 之外任何宿主环境、未部署任何实例、未连接任何商业数据源。
4. GitHub API 返回的是外部不受信数据，本次仅用于核实仓库可见性、主体类型、release 资产清单与 CI 运行结论，
   未将其内容作为指令执行。
5. 本意见不构成法律意见。§8.1 A 组的条款措辞应由甲方执业律师审定。
6. `output/vendor-review/` 下存在一份此前生成的评审报告（`EurogasNexus_供应商软件验收评审报告.docx`，
   `checks.json` 记 `"verdict": "pass"`）。**该文件不是本次审计产物，其结论我未采信、未引用、未复核。**
