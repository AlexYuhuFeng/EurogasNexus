# Client Internationalization And Theme Spec

## Purpose

V1 clients must support English and Mandarin Chinese from the first client
implementation milestone. They must also support light, dark, and system theme
modes.

## Required Locales

Required locale IDs:

- `en-US`;
- `zh-CN`.

UI labels may use English as the source language, but no user-visible Web or
Windows string should be hard-coded directly in components. Strings belong in
locale resource files.

## Translation File Layout

Use this structure for Web:

```text
clients/web/src/i18n/
  index.ts
  locales/
    en-US.json
    zh-CN.json
```

Use the same keys for both locale files. Missing translation keys fail tests.

## Required Translation Namespaces

Use flat or shallow keys grouped by:

- `app`;
- `navigation`;
- `runtime`;
- `network`;
- `capacity`;
- `market`;
- `scenario`;
- `strategy`;
- `review`;
- `sources`;
- `glossary`;
- `settings`;
- `errors`;
- `states`;
- `units`;
- `analysis`.

## Mandarin Requirements

`zh-CN` should use clear Simplified Chinese/Mandarin business language. Keep
specialized market acronyms such as TTF, NBP, LNG, ENTSOG, GIE, EEX, ICE OCM,
HDD, and CDD unchanged unless a glossary entry defines a localized explanation.

The glossary should support localized definitions through backend/API models.

## Runtime Locale Behavior

Required behavior:

- default to browser/system language when it is `zh-CN` or English-compatible;
- otherwise default to `en-US`;
- allow explicit user override in Settings;
- store only the locale preference locally;
- never call live translation APIs.

## Theme Modes

Required modes:

- `light`;
- `dark`;
- `system`.

Theme selection behavior:

- default to `system`;
- respect `prefers-color-scheme`;
- allow explicit override in Settings;
- store only the theme preference locally;
- apply theme through `data-theme` on the root app element.

## Theme Token Requirements

Define CSS custom properties for:

- surfaces;
- panels;
- text;
- borders;
- map base;
- route/corridor overlays;
- capacity/contract overlays;
- live/delayed/demo/partial/unavailable states;
- warnings;
- critical/restricted states;
- source badges;
- LLM analysis/citation badges.

Do not use one-color themes. Light and dark themes must both preserve status
contrast without relying on color alone.

## Tests

Required client tests when Web tooling exists:

- every `en-US` key exists in `zh-CN`;
- navigation renders in both locales;
- theme switch sets `data-theme`;
- system theme does not overwrite explicit user preference;
- status badges include text or accessible labels, not color only.

