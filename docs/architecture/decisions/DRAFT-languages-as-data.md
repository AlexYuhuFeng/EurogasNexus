# DRAFT ADR: Languages are data; the server writes message codes

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.9. On acceptance it is appended to
[ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It generalises the existing
server-notes pattern (`domain/ontology/notes.py`) and the error codes of the backend audit (A2) to
all server text; it reverses the per-language columns.

**Context.** English and Chinese are written into code and schema:
`SUPPORTED_LANGUAGES = ("en", "zh-CN")` (`domain/settings/preferences.py`); `startsWith("zh")`
branches in 26 client files; about 640 `T(en, zh)` calls in the report and brief writers; `en`/`zh-CN`
literal types in API validators; `_en`/`_zh_cn` columns on monitoring, strategy and glossary
tables, and a bilingual AI summary written for every alert; a hand-written grammar per language
in the search bar; 161 of 233 count-bearing keys without plural forms; two placeholder syntaxes
(Python `{}` and i18next `{{}}`); contract intake, news tagging and OCR in English only. Each new
language therefore costs about 3 to 4 engineer-weeks of code, two migrations and a release
(multinational review). The correct pattern already exists for warnings: the server sends
`{code, params, text}` and the client renders `warning.<code>`.

**Decision.**

1. **One locale registry** (`config/locales.yaml`, served at `/api/i18n/locales`, baked into the
   client as a default): code, native name, Intl locale, fallback chain (`de-AT` to `de` to `en`),
   status `preview` or `shipping`, direction. The server validates language fields against it;
   client types are strings checked at run time. Administrators add a registry entry without a
   release.
2. **ICU MessageFormat** on both sides (FormatJS or `i18next-icu` in the client, Babel or PyICU on
   the server), one placeholder syntax, plural and select rules from CLDR, number and date
   skeletons.
3. **The server writes codes and parameters** for every sentence: warnings, refusals, alerts,
   report and brief lines, email. The client renders in-app; the server renders for email, PDF and
   scheduled reports in the recipient's language, from the same catalogues. Figures, units, hub
   codes and contract names are parameters, never translated.
4. **Catalogues**: UI chrome per namespace (`desk`, `deals`, `book`, `research`, `admin`,
   `warning`), lazy-loaded; server messages keyed by code; domain vocabulary (glossary, enum
   labels, hub and country names) and customer overlays in one table
   `localised_text(entity, id, field, language, text, status, translated_by, reviewed_by, tenant)`.
5. **Translation workflow**: XLIFF 2.0 export and import with key context and screenshots, a term
   base seeded from the glossary, ICU and placeholder validation on import, a pseudo-locale in CI
   (accented, 35 % longer), coverage thresholds for `shipping`.
6. **Format locale is separate from language** (number format, date order, first day of week),
   defaulting to the language's convention; semicolon CSV and US Letter as options.
7. **AI output** is generated in the reader's language on demand and cached by (item, version,
   language); there are no per-language summary columns. Quoted evidence stays in its original
   language, marked.
8. **Content in other languages**: document-language detection (an Apache-licensed detector, not
   the CC BY-SA fastText model), OCR with language packs, decimal parsing by document language,
   per-language rule packs or an evidence-checked extractor for contracts, keyword packs for news
   and REMIT.
9. **Gates**: no language literal outside `i18n/`; placeholder parity; ICU parses; every server
   code in the source catalogue; a shipping language may not equal English except on a reasoned
   allow-list.

**Alternatives.** (a) Keep adding languages as code: each costs a release and grows the
per-language branches. (b) Machine-translate at render time: unreviewed desk vocabulary and an
outside data flow. (c) A translation-management service inside the product: customers already run
XLIFF-capable tools.

**Consequences.** A one-off refactor of 5 to 8 engineer-weeks, mostly the report and brief writers
and the search grammar; afterwards each language is about 60,000 words of translation (roughly
9,000 to 15,000 EUR at specialist rates) and 3 to 5 days of desk review, with no engineering
except an optional search keyword pack. Right-to-left languages remain out of scope.

**Migration.** (1) The CI gate now, so the problem stops growing. (2) Registry and validators.
(3) Server codes module by module, keeping `text` as the English fallback. (4) ICU in both
clients and the plural fixes. (5) `localised_text`, then the per-language columns are dropped
after one release. (6) XLIFF and the Languages admin page. (7) German as the first translation
drop.

**Tests that make it observable.** Adding a language through the registry and an XLIFF import
reaches coverage without a code change; a German recipient receives a German alert email; the
pseudo-locale screenshot run shows no clipping at 1366 and 390 pixels.
