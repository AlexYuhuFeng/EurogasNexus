# Economics workflow acceptance — capacity billing and LNG economics-only

Status: **bounded synthetic browser and installed-SDK acceptance passed on 2026-10-28.**
Root independently executed the scripts against the dedicated PostgreSQL-backed
loopback API/Web stack. These results cover the two compute-only workflows;
final immutable native artifacts and complete customer acceptance remain open.

## 1. Scope

The two existing research sandboxes are exercised as existing capabilities:

| Workflow | Screen | Endpoint |
| --- | --- | --- |
| Capacity billing | Contracts → Routes → Capacity billing sandbox | `POST /api/research/capacity-billing` |
| LNG economics-only | Contracts → Resources → LNG economics tab | `POST /api/research/lng-economics-only` |

The scripts do **not** add a capability, change a backend formula, seed data,
write database rows, change grants/ACLs, activate a source, call a provider, or
retrieve commercial data. The research endpoints are compute-only. The browser
harness creates an ordinary authenticated development session through the
existing sign-in form; that session is the only non-read side effect.

All numeric inputs below are explicitly synthetic. Nothing in this document
establishes booked capacity, physical readiness, terminal access, a cargo,
delivery feasibility, invoice authority, settlement, or customer approval.

## 2. Files

- Browser harness: `scripts/uat/economics_workflow_smoke.mjs`
- Typed SDK example: `scripts/examples/lng_capacity_economics.py`
- Focused Python tests: `tests/unit/test_economics_acceptance_scripts.py`
- Focused Node tests: `tests/unit/test_economics_workflow_smoke.mjs`

## 3. Synthetic goldens

### 3.1 Capacity billing

| Case | Wall-clock window | Rate and basis | Booked / billed / delivered | Exact total | Exact per delivered | Duration |
| --- | --- | --- | --- | ---: | ---: | ---: |
| 23 h | `2026-01-01T00:00Z` → `2026-01-01T23:00Z` | `2` `EUR/(MWh/h)/h` | `10` / `230` / `115` MWh | `460.0000` EUR | `4.0000` EUR/MWh | `82,800,000,000` µs |
| 25 h | `2026-01-02T00:00Z` → `2026-01-03T01:00Z` | `2` `EUR/(MWh/h)/h` | `10` / `250` / `125` MWh | `500.0000` EUR | `4.0000` EUR/MWh | `90,000,000,000` µs |
| 24 h pence | `2026-01-04T00:00Z` → `2026-01-05T00:00Z` | `0.035827` `p/(kWh/h)/h` | `10` / `240` / `120` MWh | `85.9848` GBP | `0.7165` GBP/MWh | `86,400,000,000` µs |

The pence result uses the exact documented conversion `1000 kWh/MWh ÷
100 pence/GBP = 10`; no FX, annualisation or calendar assumption is applied.

The refusal case keeps the 23 h basis but sends billed capacity energy `240`
instead of the exact `230`. The backend must answer `422` with outer code
`capacity_billing_refused` and stable violation
`BILLED_CAPACITY_ENERGY_INCONSISTENT`.

Every successful response must also report `physical_readiness=NOT_ASSESSED`
and metadata with references unverified, booked rights unestablished and
customer approval false.

### 3.2 LNG economics-only

- purchased `100` MWh at `20` EUR/MWh → `2,000.00` EUR;
- delivered `90` MWh at `30` EUR/MWh → `2,700.00` EUR;
- one separately invoiced `150.00` EUR downstream cash cost;
- purchase and downstream cost paid on valuation date `2026-09-29` with an
  explicit discount factor `1`;
- sale paid `2026-11-30` with an explicit discount factor `0.975`.

Expected exact result:

| Item | Expected |
| --- | ---: |
| purchase outlay | `2000.0000` EUR |
| sale proceeds | `2700.0000` EUR |
| downstream cash cost | `150.0000` EUR |
| cargo margin / undiscounted cash | `550.0000` EUR |
| net present value | `482.5000` EUR |
| total consumed in kind | `7` MWh |
| physical loss | `3` MWh |
| total reduction (purchased − delivered) | `10` MWh |
| physical readiness | `NOT_ASSESSED` |
| readiness assessed | `false` |

The explicit ordered energy chain is:

1. `100 → 96`, consumed `3`, physical loss `1`;
2. `96 → 90`, consumed `4`, physical loss `2`.

The refusal case changes the first stage physical loss from `1` to `2`, so the
chain is no longer conserved. The backend must answer `422` with outer code
`lng_economics_only_refused` and stable violation
`STAGE_CONSERVATION_FAILED`.

No terminal slot, cargo custody, storage right, TSO access or nomination
authority is claimed by a successful result.

## 4. Browser acceptance

### 4.1 Configuration

The harness has no default Web URL, login, Playwright package or fixture file.
It reads only these environment variables:

| Variable | Required | Meaning |
| --- | --- | --- |
| `EUROGAS_NEXUS_DEV_LOGIN_USERNAME` | yes | Existing development fixture principal. No principal is created. |
| `EUROGAS_NEXUS_DEV_LOGIN_PASSWORD` | yes | Existing fixture password. Never logged or captured. |
| `EUROGAS_UAT_BASE_URL` | yes | Web origin only, no path/query/fragment/userinfo. |
| `EUROGAS_UAT_PLAYWRIGHT_PATH` | yes | Absolute path to the installed Playwright entry. |
| `EUROGAS_UAT_OUTPUT_DIR` | no | Optional directory for bounded JSON and viewport PNGs. |
| `EUROGAS_UAT_AXE_PATH` | no | Optional axe-core file. When absent the harness tries the dependency beside Playwright. |
| `EUROGAS_UAT_ALLOW_NON_LOOPBACK` | no | Unset, or exactly `1`; non-loopback also requires an HTTPS base URL. |

No secret/config file is read. Access is loopback-only unless the operator sets
the explicit remote-UAT opt-in above. Plain HTTP is refused off loopback because
the browser sends the fixture password to that origin.

PowerShell example (replace placeholders from the approved local session; do not
commit values):

```powershell
$env:EUROGAS_NEXUS_DEV_LOGIN_USERNAME = '<existing synthetic fixture user>'
$env:EUROGAS_NEXUS_DEV_LOGIN_PASSWORD = '<existing synthetic fixture password>'
$env:EUROGAS_UAT_BASE_URL = 'http://127.0.0.1:3000'
$env:EUROGAS_UAT_PLAYWRIGHT_PATH = 'C:\path\to\scripts\ci\browser-acceptance\node_modules\playwright\index.js'
$env:EUROGAS_UAT_OUTPUT_DIR = '.dnx-out\economics-20261028'
node scripts/uat/economics_workflow_smoke.mjs
```

For an explicit remote UAT only:

```powershell
$env:EUROGAS_UAT_ALLOW_NON_LOOPBACK = '1'
$env:EUROGAS_UAT_BASE_URL = 'https://<approved-uat-host>'
```

### 4.2 Checks

The harness runs English and Simplified Chinese and, for the golden result,
desktop `1440×900` and narrow `390×844` viewports.

It must observe:

1. The capacity panel is mounted on Contracts → Routes; the LNG form is opened
   through the existing Contracts task tab.
2. The capacity fields are typed through their actual inputs/selects; the LNG
   scope, purchase/sale, two energy-stage rows, one downstream-cost row and two
   discount rows are created through the product's own add-row controls and
   typed through their labelled controls.
3. `Ctrl+Enter` inside each panel submits. The response is the **actual backend**
   response. The script asserts exact response strings and the exact rendered
   strings; it does not compute money or accept a mocked amount.
4. Success moves focus to the monetary result. The active element has a visible
   computed outline and the result contains the documented amounts.
5. Editing a field removes the previous result before the next submit.
6. The inconsistent capacity and broken-conservation LNG requests return `422`
   with the stable codes above; the UI shows the refusal and no partial result
   remains.
7. For one actual success request per panel, Playwright routing delays the
   request before `route.continue()`. A second synthetic Ctrl+Enter chord is
   dispatched while `aria-busy` is true; exactly one backend request may exist.
   The handler never calls `route.fulfill`, never mocks the response and never
   replaces an amount.
8. Axe (when installed) runs over the whole document with no exclusions at both
   widths. If axe is unavailable, the summary states that and no axe claim is
   made. There is no rule exclusion or threshold change.
9. Document horizontal overflow at 390px and 1440px stays within the existing
   allowance (`scrollWidth <= clientWidth + 2`).
10. No credential appears in the JSON summary or screenshots. Screenshots are
    optional viewport captures taken only after sign-in and contain no sign-in
    form.

The optional output directory receives `economics-workflow.json` and bounded
viewport PNGs under `screenshots/`. Without `EUROGAS_UAT_OUTPUT_DIR`, the script
writes nothing and prints the same bounded JSON to stdout.

## 5. Typed SDK example

### 5.1 Configuration

```powershell
$env:EUROGAS_UAT_API_BASE_URL = 'http://127.0.0.1:8000'
$env:PYTHONPATH = 'src;packages/python-sdk/src'
python scripts/examples/lng_capacity_economics.py
```

The API base URL is required and is loopback-only unless
`EUROGAS_UAT_ALLOW_NON_LOOPBACK=1` is also set with an HTTPS origin.

Public token and identity are read **only** by the existing SDK helpers from
`EUROGAS_NEXUS_PUBLIC_API_TOKEN` (or the legacy `EUROGAS_NEXUS_API_TOKEN`)
and, when required by the deployment, `EUROGAS_NEXUS_PRINCIPAL` /
`EUROGAS_NEXUS_IDENTITY_BEARER`. The example never reads, prints, constructs or
persists those values itself. Do not place tokens on the command line or in this
document.

### 5.2 Behaviour

The example:

- builds `CapacityBillingRequest` and `LngEconomicsOnlyRequest` typed objects;
- sends actual HTTP through `eurogas_nexus_sdk.research.calculate_*`;
- reports `sdk_mode` as `source` or `installed` from the imported package
  location, so evidence states which artifact was exercised;
- asserts the three capacity goldens, the LNG money/energy goldens and both
  stable refusal codes;
- emits one safe JSON object with status, checks and stable refusal codes only;
- emits no response body, traceback, credential, token or identity value.

Exit codes: `0` all checks pass, `1` acceptance failure, `2` clean
configuration/import failure. A missing SDK or missing base URL reports a clean
JSON error rather than a traceback.

## 6. Focused tests

```powershell
python -m pytest tests/unit/test_economics_acceptance_scripts.py -q
node --test tests/unit/test_economics_workflow_smoke.mjs
```

The Python tests load the example by path, verify the exact goldens and typed
fixture, exercise loopback/HTTPS/credential URL refusal, prove refusal summaries
drop free text, and syntax-check the browser module when Node is available. The
Node tests import the browser module without environment or Chromium, exercise
its actual URL/sanitizer/golden functions, and assert there is no
`route.fulfill` or secret-file assumption.

## 7. Required root run

The root operator should run this bounded acceptance only against the existing
dedicated synthetic PostgreSQL-backed API/Web acceptance stack:

1. Confirm the API/Web are the intended synthetic UAT processes and the existing
   development fixture principal is valid. Do not seed, grant or reset data.
2. Run the browser harness with the approved environment above.
3. Run the typed SDK example against the same synthetic API.
4. Retain the safe JSON summaries and any screenshots under the ignored output
   directory.
5. Run both focused test commands.
6. Record exact pass/fail counts and any unavailable axe/SDK mode. Do not infer a
   full delivery pass from this bounded workflow.

## 8. Current evidence and gaps

- Actual Chromium run: **203 checks passed**, English/Simplified Chinese,
  1440px/390px, actual backend responses, duplicate-submit protection, stale-result
  invalidation, exact goldens and refusal codes. **Eight whole-document axe runs
  passed with zero violations**, without exclusions. The run found a real mobile
  accessibility issue: LNG horizontally scrollable tables now have keyboard focus
  and accessible region labels.
- Evidence: ignored local `economics-browser-durable/economics-workflow.json`
  beneath `.local-runtime/delivery-20261027`, generated
  `2026-10-27T17:27:30.440Z` (2026-10-28 local time).
- Installed unified backend/SDK checkpoint wheel: **six actual HTTP checks passed**,
  `sdk_mode=installed`, isolated interpreter; evidence in ignored
  `installed-sdk-economics-example.log`. This wheel predates the latest tariff-date
  bridge and does not bind final delivery source or native artifacts.
- Focused script tests: **nine Python tests and seven Node tests passed**; Ruff
  passed. Expected monetary constants are fixtures, while the run evidence above
  records actual server and rendered results.
- Native/desktop, production SSO/certification, provider licensing, real
  terminal/cargo/slot evidence and customer/practitioner acceptance remain
  outside this bounded workflow.

No source activation, grant change, database write, provider call, trade,
nomination or settlement is authorised by any result in this document.
