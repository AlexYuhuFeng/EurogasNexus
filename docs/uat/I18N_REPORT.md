# I18N Report — CR-13

## Method

- Programmatic key-parity check across `en.json` and `zh.json`.
- Static scan of all `t("...")` usages for missing keys.
- Layout smoke for EN and zh-CN at 1440×900.
- Terminology review against the professional terminology dictionary.

## Results

- Key sets: 1,247 keys each; **no missing keys and no only-en/only-zh keys**.
- Static usage scan: all referenced keys resolve.
- zh-CN layout: build and browser smoke pass without overflow/clipping in
  reviewed workspaces.
- Standard market identifiers (TTF, NBP, THE, PEG, ZTP, PSV, GBP, EUR, MWh)
  are not translated.
- Removed English fragments from zh-CN capacity labels and strategy period;
  standardized warning-code translations.

## Remaining

- Native-speaker commercial terminology review remains PENDING_EXTERNAL for
  formal customer acceptance; the automated parity gate is green.
