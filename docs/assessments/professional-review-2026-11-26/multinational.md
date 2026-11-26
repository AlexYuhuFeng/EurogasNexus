# Eurogas Nexus: review from a multinational trading group

Reviewers: (1) the localisation/internationalisation lead, (2) the contracts and legal manager (EFET GTMA, NBP/ZBT
terms, bespoke supply agreements in DE/FR/IT/ES/NL/EN), (3) the COO of a group with desks in London, Geneva,
Düsseldorf, Madrid, Milan, Singapore and Houston. Code read: `/home/user/EurogasNexus-merge`. Demo walked as
`test_trader` from a de-DE browser with the clock set to Asia/Singapore (2026-11-26).

## 1. Verdict

Within one language pair the localisation is careful and well tested. Stable server note codes, a key-parity gate,
a gate that catches untranslated values, native units, and times that name their zone are all better than most
ETRM front-ends we have rolled out. But "Chinese and English" is built into the code, not held as data. There are
`startsWith("zh")` branches in about 33 client files. The server has 338 `T(en, zh)` pairs in its report and brief
writers and 12 API validators typed `Literal["en", "zh-CN"]`. The database has `_en`/`_zh_cn` columns on three
tables, and the answer bar has a hand-written English and Chinese grammar. So German, French, Spanish or Italian
each cost an engineering release, not a translation drop. The content side is English-only: contract PDF intake
reads only English EFET wording, news tagging matches only English keywords, and national-regulator feeds are not
wired. A Düsseldorf contracts team with a German Gasliefervertrag, or a Madrid analyst reading CNMC/Enagás notices,
gets nothing from it. We would adopt it now for the London and Singapore desks in English. A group-wide rollout is
blocked by the language architecture and by the missing legal-entity and jurisdiction model, not by translation
budget.

## 2. Per persona

### 2.1 Localisation / i18n lead

**The job:** keep 6 to 8 UI languages shippable every release, with a glossary per language, missing-key gates,
handoff to a TMS (XLIFF), and no developer needed to change a word.

**What works**
- i18next with flat dotted keys (`clients/web/src/i18n/en.json`, 7,670 keys, about 34k English words) and a single
  locale registry (`i18n/locales.ts`: code, native name, `intlLocale`, `direction`). English is the fallback, and
  the language is stored per principal on the server (`domain/settings/preferences.py`), so it follows the user
  from web to desktop.
- Gates. `tests/locales.test.ts` checks key parity. `tests/localeDistinctness.test.ts` fails when a value is left
  untranslated, with an allow-list where every entry states its reason. That is the right idea.
- The server notes catalogue (`domain/ontology/notes.py`) sends `{code, params, text}`. The client renders
  `warning.<code>` and falls back to `text`. `tests/unit/test_server_text_in_client_locales.py` requires every
  declared code in the locale files. This is the correct pattern and should become the pattern for all server
  text.
- Latin Extended fonts are self-hosted (`styles/fonts.css`), so Polish, Czech and Romanian diacritics render.
  Digit shortcuts use `event.code` (`app/experience/commandPalette.ts:556`), so Ctrl+Shift+1 works on AZERTY.

**Gaps**
- *Must:* languages are code, not data. The registry comment says one entry adds a language. In fact
  `formattingLocale()` (`app/time/timeFormat.ts:42`) returns only `zh-CN` or `en-GB`. `periodModel.ts` hard-codes
  `EN_MONTHS`/`ZH_WEEKDAYS`. `GlossaryWiki`, `AlertCenter`, `ReviewWorkspace`, `CargoBoard`, `TodayScreen`,
  `ReportsWorkspace` and others branch on `startsWith("zh")`. `ReportSchedules.tsx:97` offers a fixed
  `[English, 中文]` select. `intlLocaleFor()` is called nowhere, and `"en-GB"` is hard-coded in about 90
  `toLocaleString`/`Intl` calls.
- *Must:* plurals. 233 values use `{{count}}`, and 161 of them have no `_one`/`_other` variant
  (`context.sources_need_action` gives "1 sources need action"). Polish needs one/few/many/other, and none of that
  is modelled. There is no ICU MessageFormat (select or gender), and the server uses Python `{}` templates while
  the client uses `{{}}`. That gives two syntaxes for translators.
- *Must:* no TMS workflow. There is no XLIFF or PO export, no translator context or screenshots, no per-language
  term base, and no translation memory. Locale JSON is edited by developers (`index.ts` even overrides three keys
  in code).
- *Should:* no pseudo-locale. Accented, 35% longer strings would expose clipping. UX rule 14 and
  `phoneOverflow.mjs` check only EN and ZH, and German labels run about 30% longer than English.
- *Should:* server sentences parsed back by regex. `app/model/serverSentences.ts` and `limitBreaches.ts` recognise
  English server sentences and re-translate them, which is fragile. They should become declared notes.
- *Nice:* language negotiation. A de-DE browser gets English, which is acceptable, but the sign-in picker offers
  only EN/中文.
- *Out of scope, say so:* right-to-left. `direction` exists in the registry but nothing reads it, and no RTL
  market is in scope.

**Redundant:** the `title_en`/`title_zh_cn` and `llm_summary_en`/`llm_summary_zh_cn` columns, and the bilingual LLM
prompt that writes both summaries for every alert (`monitoring_service.py:235`). Store the code and params, then
render or translate on read in the reader's language.

**Organise as:** one "Languages" admin page with coverage per language, missing keys, the export/import button and
the glossary per language. It does not belong in the trader's settings.

### 2.2 Contracts and legal manager

**The job:** take signed EFET individual contracts, confirmations and long-term supply agreements (many in German,
Italian or Spanish, some bilingual, some scanned), and capture DCQ, flex, price formula, delivery point, term,
governing law and the master agreement. Track language-authoritative clauses.

**What works:** intake (`application/contract_intake.py`) proposes terms with page and snippet and never saves
without review. It handles continental number grouping (`1.234,56`) and converts kWh/h, MW, th/d and GJ/d to MWh/d.
It shows its evidence. That is the right legal posture.

**Gaps**
- *Must:* extraction is English-only. All patterns are English (`daily contract quantity`, `Seller`/`Buyer`,
  `delivery period`, `price`, and month names `jan…dec`). A German contract ("Tägliche Vertragsmenge",
  "Verkäufer/Käufer", "Lieferzeitraum", "1. Oktober 2027"), a French one ("Quantité Journalière Contractuelle",
  "Vendeur"), Italian ("Quantità Giornaliera Contrattuale"), Spanish ("Cantidad Diaria Contratada") or Dutch one
  yields almost no terms. Hubs are matched by name (PSV and PVB are listed), but nothing else.
- *Must:* OCR runs with no language pack. `tesseract … --psm 4` is called without `-l deu+fra+ita+spa+nld`, so
  umlauts and accents degrade on scans. Only JPEG scans are read.
- *Must:* decimal ambiguity. `_number("12,500")` reads 12,500. In a German contract that is 12.5. The parse needs
  the document's language to decide, and should flag the term when the language is unknown.
- *Should:* there is no GCV/NCV or reference-condition capture. German contracts state kWh (Hs or Hi, 25/0 °C).
  The platform assumes a single desk GCV of 11.0 kWh/m³ (`domain/market/units.DESK_ASSUMED_GCV_KWH_PER_M3`).
- *Should:* no record of the contract language, the authoritative language of a bilingual contract, or a
  side-by-side clause view (original text, plus an English working translation that is marked as a translation).
- *Should:* governing law and jurisdiction are captured as text only. They should be a controlled list (English
  law/LCIA, German law/DIS, Swiss law/Swiss Rules, …).
- *Nice:* clause library per language (EFET Appendix/Election Sheet variants, ZBT, NBP 2015).

**Organise as:** one contract record with *document language*, *authoritative language*, original clauses, and AI
translations marked as such. Intake is a language-aware pipeline, not a regex list.

### 2.3 COO of a seven-desk group

**The job:** one platform across entities (a UK Ltd, a Swiss SA, a German GmbH, Spanish and Italian branches, a
Singapore Pte and a US Inc). Local regulators, local holidays, alerts to whoever is on shift, licensed data used
only where it is licensed, and data kept where the law says.

**What works**
- Time. Instants are stored in UTC and shown in the device zone, UTC or "market" (Europe/Berlin), always with the
  zone named. In the demo from a Singapore clock: "NBP Last renomination 27 Nov 10:00 GMT+8", and the gas day is
  shown as "05:00 UTC → 05:00 UTC". Gas days are never shifted.
- Units and currency. Native units come first (NBP in p/th and th/d, TTF in EUR/MWh). A secondary reporting
  currency covers the ECB table (EUR, GBP, CHF, USD, SGD …) and always names the rate and its date ("ECB 25 Nov:
  EURGBP 0.8373"). Contract terms and tariffs are never converted.
- Licences per office. `domain/market_data/licences.py` enforces site licences against the user's office, with
  seat counts.
- `docs/architecture/GLOBAL_DEPLOYMENT.md` covers a primary installation plus a sovereign China spoke, with signed
  one-way exports.

**Gaps**
- *Must:* legal entity is a free-text string on the book (`db/models/books.py: legal_entity String(64)`). There is
  no entity table with base currency, regulator(s), REMIT ACER code/LEI, VAT or jurisdiction. There is no
  intercompany relation or entity-level entitlements. A book has a `base_currency`, but nothing aggregates by
  entity in its functional currency.
- *Must:* no jurisdiction model. Nothing distinguishes ACER REMIT, UK REMIT (Ofgem), Swiss (ElCom/FINMA where
  relevant) or US (FERC/CFTC) obligations per entity. Houston's Henry Hub gas day (09:00 CT) and US units are not
  modelled. The "market" zone is Berlin only.
- *Must:* alerts route by job function, not by desk, office or working hours (`application/alert_routing.py`).
  An outage at 03:00 CET goes to "TRADER", not "the Singapore desk, which is awake". Email notifications always go
  out in English (`notifications.py:131` uses `title_en`/`message_en`), whatever the recipient's language.
- *Should:* no holiday calendars. `domain/monitoring/freshness.py:102` says "Exchange holidays are not modelled (a
  holiday reads one day late)". UK bank holidays, ICE Endex and EEX calendars, Swiss and Spanish regional holidays
  and US holidays are all missing.
- *Should:* data residency covers UK/CA/SG/CN, but not the Swiss nFADP or an EU-only installation for
  Düsseldorf/Milan/Madrid personal data. LLM calls (desk brief, news note) send facts to a provider with no
  per-entity residency switch.
- *Should:* reports are A4 only (`reports/render.py:287 @page{size:A4}`). Houston needs Letter. CSV exports are
  comma-delimited (`api/csv_export.py`), so they open in one column in German, French, Italian and Spanish Excel.
  XLSX exists, which mitigates this.
- *Nice:* number format follows the UI language, never the person. UX rule: "numbers follow the app's language,
  never the browser's". A German analyst in an English UI sees `1,234.5`, which matches Trayport, so it is
  defensible. Make it a preference, not a side effect.

## 3. Cross-cutting gaps

| # | Missing | Why a firm needs it | Evidence | Severity | Fix size |
|---|---|---|---|---|---|
| 1 | Languages as data | Adding a language for DE/FR/ES/IT staff without a release | `startsWith("zh")` in ~33 client files; `T(en, zh)` ×338 in `application/reports/*`, `desk_ask.py`, `desk_brief.py`; `Literal["en","zh-CN"]` ×12 in `api/routes/public/{explain,monitoring,news,reports,spreads}.py`; `SUPPORTED_LANGUAGES = ("en","zh-CN")` | Blocker | Architectural (one-off refactor) |
| 2 | Per-language DB columns | Every new language becomes a migration plus double LLM cost | `title_en/title_zh_cn`, `message_*`, `llm_summary_*` (`db/models/monitoring.py`), `strategy.py:201`, `definition_zh_cn` (`glossary.py`) | Major | Architectural |
| 3 | Plurals / ICU | Polish, Czech and Russian plural rules; correct English | 161 of 233 `{{count}}` keys have no plural form | Major | Feature |
| 4 | TMS pipeline | Translators and reviewers outside engineering | No XLIFF/PO, no context, no TM | Major | Feature |
| 5 | Multilingual contract intake | Most continental contracts are not in English | `contract_intake.py` English regexes; OCR without `-l` | Blocker for DE/IT/ES legal | Feature |
| 6 | Multilingual news and UMM | CNMC, ARERA, BNetzA, CRE and TSO notices are national-language | `domain/news/tagging.py` English `EVENT_KEYWORDS`; `national-regulators-unread` source `feed_url=None` | Major | Feature |
| 7 | Answer bar beyond EN/ZH | The answer bar is the fastest path | Demo: "TTF Frontmonat", "Gastag heute", "Bilanzkreis", "3,5 EUR/MWh in p/th" return no match, while "35 EUR/MWh in p/th" works; grammar is EN/ZH regex in `app/answer/*.ts` (~600 CJK chars) | Major | Feature |
| 8 | Glossary per language with native aliases | Desk words are national: Bilanzkreis, MGV, Konvertierungsentgelt, PSV "stoccaggio" | `glossary_desk.py` aliases are English only; `/api/glossary?language=de` silently returns English | Should | Config/content |
| 9 | Legal-entity and jurisdiction model | Per-entity books, functional currency, regulator, LEI | `books.legal_entity` free text; no regulator anywhere in `src/` | Major | Architectural |
| 10 | Desk/office/shift alert routing; localised email | 24-hour follow-the-sun desks | `alert_routing.py` routes by function; emails are English-only | Major | Feature |
| 11 | Holiday calendars | Settlement, staleness and expiry are correct only with them | `freshness.py:102`; `in_transit.last_trading_day(holidays=())` | Should | Feature |
| 12 | Pseudo-locale and expansion test | Catches clipping before translators do | Only EN/ZH in UX rule 14 | Should | Config |
| 13 | Locale-aware exports | European Excel, US Letter | `csv_export.py` comma; `@page A4` | Minor | Config |
| 14 | Mixed-language output | Credibility | Demo, Chinese UI: gas-day answer shows "Thu, 26 Nov 2026" in English | Minor | Config |
| 15 | Server sentences parsed by regex | Fragile i18n | `serverSentences.ts`, `limitBreaches.ts` | Minor | Feature |

Shared-account observation: midway through the demo the `test_trader` UI switched to Chinese without any action on
our side. The server-side preference sync applied another session's change, correctly. Language belongs to the
person. On shared or test logins that surprises people, so document it.

## 4. Structural limits

1. **Bilingualism is in the type system and the schema.** The `en | zh-CN` literal types (`stores/api.ts:1019`,
   `reportsModel.ts`), Pydantic literals, `_zh_cn` columns, `T(en, zh)` and a regex grammar per language mean N
   languages cost N times the code. Until this is inverted, every language is a project.
2. **Rule-written prose is composed in Python f-strings per language.** The report engine (`reports/derive.py`,
   `joins.py`, `render.py` with `WORDS`, `KIND_ZH`, `TABLE_ZH`, `STATE_WORDS_ZH`) writes sentences with word order
   baked in. German verb-final order and Romance gender agreement need message templates with named placeholders,
   not concatenation.
3. **Content understanding is English-shaped.** Intake, tagging and the answer bar are deterministic regex, which
   is good for auditability. But each language needs its own rules unless an LLM-assisted, evidence-checked
   extractor is added with the same "quote the source span" guard the news note already uses
   (`news_grounding.py`).
4. **No entity dimension.** Positions, limits, licences and reporting hang off books, offices and roles. Group
   consolidation, per-entity regulation and intercompany need a first-class entity. This is a data-model change,
   not a screen.
5. **One installation equals one residency zone.** That is fine. But AI providers and email are global settings,
   and need per-entity residency policy.

## 5. Top 10 changes, in priority order

1. Make languages data. Read the server `SUPPORTED_LANGUAGES` from configuration and the locale registry. Replace
   every `Literal["en","zh-CN"]` with a validator against that registry. Replace `startsWith("zh")` and
   `formattingLocale` with `intlLocaleFor()`. Add a CI gate: no `zh` literal outside `i18n/`.
2. Move all server text to message catalogues, extending `notes.py`. Each sentence becomes a code, its params and
   ICU templates per language. Retire `T(en, zh)`, the `_zh_cn` columns and `serverSentences.ts`. Store alerts as
   code and params, and render them in the reader's language, including email.
3. Adopt ICU MessageFormat (i18next-icu or FormatJS) on both sides, with one placeholder syntax, plural, select
   and number/date skeletons. Fix the 161 non-plural `{{count}}` keys.
4. Add a TMS pipeline: XLIFF 2.0 export and import (or PO), key context and screenshots, a per-language term base
   seeded from the glossary, a pseudo-locale (`en-XA`) in CI, and coverage thresholds per language for "shipping"
   versus "preview".
5. Make contract intake multilingual. Use per-language rule packs (de, fr, it, es, nl) or an evidence-checked LLM
   extractor. Run Tesseract with language packs. Detect document language and use it for decimals. Store
   document and authoritative language. Show the original and translated clause side by side.
6. Add a legal-entity model: entity, LEI/ACER code, functional currency, regulator(s), jurisdiction, data-residency
   zone and holiday calendar. Books reference an entity, and consolidation happens in functional currency.
7. Route alerts by desk, office and shift calendar, with follow-the-sun handover. Send notifications in the
   recipient's language.
8. Add holiday calendars per market and exchange (EEX, ICE Endex, UK, CH, ES, IT, US) and use them in freshness,
   expiry and the ladder.
9. Make news and UMM multilingual: keyword packs per language, wired national regulator and TSO feeds, and AI
   notes in the reader's language that quote the original text.
10. Separate the format locale from the UI language (number, date and first-day-of-week preference), and add a
    Letter page option and semicolon CSV for continental Excel.

## 6. Proposed i18n architecture

**Principles.** A language is a row of data plus files, never a branch. English is the source language. The
server owns everything it writes and sends codes, never prose, to clients that can render. Original-language
content is preserved, and translations are marked as translations.

**Registry (one source of truth).** `config/locales.yaml`, served at `GET /api/i18n/locales` and baked into the
client build as a default. Each entry:
`{code: "de-DE", nativeName: "Deutsch", intlLocale: "de-DE", fallback: ["de", "en"], status: shipping|preview,
dir: ltr, numberLocaleDefault: "en-GB"}`. The server validates `language` fields against this list. Client types
become `string` checked at runtime, not unions.

**Where translations live**

| Layer | Content | Storage | Format |
|---|---|---|---|
| UI chrome | ~7.7k keys | `clients/web/src/i18n/<lang>/*.json`, split by namespace (`desk`, `deals`, `book`, `research`, `admin`, `warning`) and lazy-loaded | ICU MessageFormat |
| Server messages | notes, report and brief sentences, alert titles, email | `src/eurogas_nexus/i18n/<lang>.json` keyed by note code | ICU (Python: `pyicu` or `babel` plus an ICU formatter) |
| Domain vocabulary | glossary definitions, enum labels, hub/zone/country names | DB table `localised_text(entity, id, field, lang, text, status, translated_by, reviewed_by)` | text |
| Customer overlay | firm terms ("our book" names), desk words, corrections | same table, `tenant` scope; overrides shipped text | ICU |
| Long-form docs | guides, manual | `docs/<lang>/…` per language (today `-CN.md` twins) | Markdown |

**Server/client split.** The server sends `{code, params, text_en}` for everything it writes: warnings, alerts,
report sentences, brief lines. The client renders in-app using bundled plus overlay catalogues. The server renders
for out-of-app channels (email, PDF/HTML reports, scheduled reports, MCP/API consumers asking with
`Accept-Language`). Both resolve the same catalogue through the same fallback chain, `de-AT → de → en`. Figures,
units, hub codes and contract names are never translated: they are params.

**AI.** Prompts carry `reader_language` and require quoted evidence in its original language, marked
(`„…" (de, BNetzA)`). `language_ok()` is generalised from a CJK-ratio check to a language-ID check (e.g. fastText
`lid.176`, which is CC BY-SA, or a CLD3 equivalent; confirm commercial terms per AGENTS rule 18). There are no
per-language summary columns: a summary is generated on demand per reader language and cached by
`(alert, version, lang)`.

**How a customer adds a language without a release**
1. An admin adds a registry entry in status `preview` through the Languages page (stored in organisation settings
   and validated server-side).
2. The admin exports XLIFF for UI, server and domain-vocabulary namespaces, with key context, screenshots and the
   term base.
3. The firm's translators or vendor (Phrase, Lokalise, Crowdin, memoQ; any XLIFF-capable tool) translate, and a
   desk reviewer approves terms.
4. The admin imports the XLIFF. The server validates ICU syntax, placeholder parity and length budgets against the
   pseudo-locale results, then stores it in the overlay table, signed and audited.
5. Clients fetch `GET /api/i18n/catalogue/<lang>/<namespace>?v=<hash>`. Missing keys fall back by chain and are
   counted on the coverage page. The admin promotes the language to `shipping` once it reaches the threshold
   (for example 98% UI, 100% warnings).
6. Shipped releases bring new English keys. The coverage page lists the delta, and a release never breaks a
   customer language: it falls back key by key.

**Gates (CI).** No language literal outside `i18n/`. Key and placeholder parity for shipping languages. ICU parses.
Pseudo-locale screenshot run on the main routes at 1366 px and 390 px. Every server note code is in the source
catalogue. The `localeDistinctness` idea is generalised: a shipping language may not equal English except on the
reasoned allow-list.

**Cost.** One-off refactor (items 1 to 3) is about 5 to 7 engineer-weeks, mostly the report and brief writers and
the answer-bar grammar. After that, each language is about 60k words (UI 34k, server messages and reports about
10k, glossary about 8k, guides about 10k). At specialist energy-translation rates of €0.15–0.25/word that is
roughly €9–15k, plus 3 to 5 days of desk review per language. There is no engineering beyond an answer-bar
keyword pack, about 1 week per language for its grammar if natural-language parsing in that language is wanted.
Polish adds the plural work that item 3 enables. Today, without the refactor, each language would be roughly 3 to
4 engineer-weeks of code, two migrations and a release.
