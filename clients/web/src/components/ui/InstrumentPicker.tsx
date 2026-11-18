/**
 * InstrumentPicker (design basis 2, D.2): choose a hub, then a product kind and a tenor, or
 * type desk shorthand ("ttf jan27", "nbp m+1", "the q1-27", "ztp da", "英国 次月").
 *
 * - A trigger shows the current pick (hub, tenor, native unit, `sim` for a simulated series).
 *   Opening it puts focus in the search box (an ARIA combobox) over a listbox of at most twelve
 *   options; the rest of a level is reached by typing.
 * - Keyboard: ArrowUp/Down move, Enter picks (a hub opens its tenors), ArrowLeft/Right change
 *   the product kind at level 2, Backspace in an empty box goes back to the hubs, Escape clears
 *   the text, then goes back, then closes and returns focus to the trigger. Typing filters.
 * - Level 2 offers presets (front month, next quarter, season, calendar year, day-ahead) that
 *   resolve to what the hub holds. Recent picks head level 1.
 * - On a phone the panel is a bottom sheet. Colours, sizes and spacing come from the tokens.
 *
 * All logic is in `app/model/instrumentPicker.ts`; this file renders and wires events.
 */
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";

import {
  CLOSED,
  PRESETS,
  enterHub,
  hubKinds,
  pickerKey,
  pickerOptions,
  presetInstrument,
  readRecent,
  selectionOf,
  unitLabel,
  withQuery,
  withRecent,
  writeRecent,
  type PickerCatalogue,
  type PickerHub,
  type PickerInstrument,
  type PickerOption,
  type PickerSelection,
  type PickerState,
} from "@/app/model/instrumentPicker";
import { displayTime } from "@/app/time/displayTime";

export interface InstrumentPickerProps {
  catalogue: PickerCatalogue | null;
  /** The picked instrument id (`TTF:M+1`), or a hub code when `scope` is `hub`. */
  value: string | null;
  onChange: (selection: PickerSelection) => void;
  /** Visible label and the panel's accessible name. */
  label: string;
  /** `instrument` (default): hub then tenor; `hub`: the first level only. */
  scope?: "hub" | "instrument";
  loading?: boolean;
  /** Anchor for relative codes (`m+1`); today by default. */
  today?: Date;
  className?: string;
  id?: string;
  /** Render open (a story page, a server-rendered test). */
  defaultOpen?: boolean;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function findInstrument(catalogue: PickerCatalogue | null, id: string | null): { hub: PickerHub; instrument: PickerInstrument } | null {
  if (!catalogue || !id) return null;
  for (const hub of catalogue.hubs) {
    for (const kind of hub.kinds) {
      const instrument = kind.instruments.find((item) => item.id === id);
      if (instrument) return { hub, instrument };
    }
  }
  return null;
}

export function InstrumentPicker({
  catalogue,
  value,
  onChange,
  label,
  scope = "instrument",
  loading = false,
  today,
  className,
  id,
  defaultOpen = false,
}: InstrumentPickerProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<PickerState>(defaultOpen ? { ...CLOSED, open: true } : CLOSED);
  const [recent, setRecent] = useState<string[]>(() => readRecent(storage()));
  /** `end` when the panel would run past the right edge from the trigger's left (a control at
   * the end of a chart header): it then opens aligned to the trigger's right edge. */
  const [align, setAlign] = useState<"start" | "end">("start");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const baseId = useId();
  const listId = `${baseId}-list`;
  const labelId = `${baseId}-label`;
  const anchor = useMemo(() => today ?? new Date(), [today]);
  const empty: PickerCatalogue = useMemo(() => ({ hubs: [] }), []);
  const data = catalogue ?? empty;

  const currentHub = state.level === "tenor" ? data.hubs.find((hub) => hub.hub === state.hub) ?? null : null;
  const kinds = hubKinds(currentHub);
  const { options, hidden } = pickerOptions(state, data, { recent, today: anchor, scope });
  const optionId = (option: PickerOption) => `${baseId}-opt-${option.id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
  const active = options[Math.min(state.active, options.length - 1)];

  const close = useCallback((returnFocus: boolean) => {
    setState(CLOSED);
    if (returnFocus) triggerRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!state.open) return undefined;
    const box = rootRef.current?.getBoundingClientRect();
    // The panel is 380 px wide (instrumentPicker.css); on a phone it is a sheet and ignores this.
    setAlign(box && box.left + 380 > window.innerWidth - 16 ? "end" : "start");
    inputRef.current?.focus({ preventScroll: true });
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [state.open, state.level, close]);

  // Keep the active option in view when moving through a scrolled list.
  useEffect(() => {
    if (!state.open || !active || typeof document === "undefined") return;
    document.getElementById(optionId(active))?.scrollIntoView?.({ block: "nearest" });
  });

  const choose = (option: PickerOption) => {
    const selection = selectionOf(option, scope);
    if (!selection) {
      setState((current) => enterHub(current, option.hub));
      return;
    }
    const remembered = selection.instrument ? selection.instrument.id : selection.hub;
    const next = withRecent(recent, remembered);
    setRecent(next);
    writeRecent(storage(), next);
    onChange(selection);
    close(true);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const { state: next, effect } = pickerKey(state, event.key, { options, kinds });
    const handled = next !== state || effect.type !== "none";
    if (!handled) return;
    if (event.key !== "Backspace" || next !== state) event.preventDefault();
    if (event.key === "Escape") event.stopPropagation();
    if (effect.type === "close") {
      close(true);
      return;
    }
    setState(next);
    if (effect.type === "choose") choose(effect.option);
  };

  const onInput = (event: ChangeEvent<HTMLInputElement>) => setState((current) => withQuery(current, event.target.value));

  const onBlur = () => {
    // Focus leaving both the trigger and the panel closes it (Tab out).
    window.setTimeout(() => {
      const focused = document.activeElement;
      if (focused && rootRef.current && !rootRef.current.contains(focused)) setState(CLOSED);
    }, 0);
  };

  const picked = scope === "hub" ? null : findInstrument(catalogue, value);
  const pickedHub = scope === "hub" ? data.hubs.find((hub) => hub.hub === value) ?? null : picked?.hub ?? null;
  const hubName = (hub: PickerHub) => t(`instrument_picker.hub_name.${hub.hub}`, { defaultValue: hub.name });
  const kindLabel = (kind: string) => t(`instrument_picker.kind.${kind}`);

  const triggerText = picked
    ? `${picked.hub.hub} ${picked.instrument.code}`
    : pickedHub
      ? pickedHub.hub
      : t("instrument_picker.choose");
  const triggerUnit = picked ? unitLabel(picked.instrument.nativeUnit) : pickedHub ? unitLabel(pickedHub.nativeUnit) : null;
  const triggerSimulated = picked ? picked.instrument.simulated : Boolean(pickedHub?.simulated);

  const presets = currentHub && scope === "instrument" && !state.query
    ? PRESETS.map((preset) => ({ preset, instrument: presetInstrument(currentHub, preset, anchor) })).filter(
        (item): item is { preset: (typeof PRESETS)[number]; instrument: PickerInstrument } => item.instrument !== null,
      )
    : [];

  const classes = ["ds-ipicker", className].filter(Boolean).join(" ");
  return (
    <div ref={rootRef} className={classes} data-instrument-picker={id ?? ""} data-open={state.open ? "true" : "false"} onBlur={onBlur}>
      <span className="ds-ipicker-label" id={labelId}>{label}</span>
      <button
        ref={triggerRef}
        type="button"
        className="ds-ipicker-trigger"
        aria-haspopup="dialog"
        aria-expanded={state.open}
        aria-labelledby={`${labelId} ${baseId}-value`}
        disabled={loading && !catalogue}
        onClick={() => (state.open ? close(false) : setState({ ...CLOSED, open: true }))}
        onKeyDown={(event) => {
          if (!state.open && (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            setState({ ...CLOSED, open: true });
          }
        }}
      >
        <span id={`${baseId}-value`} className="ds-ipicker-value">{loading && !catalogue ? t("instrument_picker.loading") : triggerText}</span>
        {triggerUnit && <span className="ds-ipicker-unit">{triggerUnit}</span>}
        {triggerSimulated && <span className="ds-ipicker-sim" title={t("instrument_picker.simulated_hint")}>{t("instrument_picker.sim")}</span>}
        <span className="ds-ipicker-caret" aria-hidden="true">▾</span>
      </button>
      {state.open && (
        <div
          className="ds-ipicker-panel"
          role="dialog"
          aria-label={label}
          data-level={state.level}
          data-align={align}
          onKeyDown={(event) => {
            if (event.key === "Escape" && event.target !== inputRef.current) {
              event.preventDefault();
              event.stopPropagation();
              close(true);
            }
          }}
        >
          <div className="ds-ipicker-head">
            {state.level === "tenor" && currentHub ? (
              <button
                type="button"
                className="ds-ipicker-back"
                onClick={() => setState((current) => ({ ...current, level: "hub", hub: null, kind: null, query: "", active: 0 }))}
              >
                <span aria-hidden="true">‹ </span>
                {t("instrument_picker.back_to_hubs")}
              </button>
            ) : (
              <span className="ds-ipicker-title">{t(scope === "hub" ? "instrument_picker.hubs_only" : "instrument_picker.hubs")}</span>
            )}
            {currentHub && (
              <span className="ds-ipicker-crumb">
                {currentHub.hub} · {hubName(currentHub)} · {unitLabel(currentHub.nativeUnit)}
              </span>
            )}
            <button type="button" className="ds-ipicker-close" onClick={() => close(true)} aria-label={t("instrument_picker.close")}>
              <span aria-hidden="true">×</span>
            </button>
          </div>
          <input
            ref={inputRef}
            className="ds-ipicker-search"
            type="text"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={active ? optionId(active) : undefined}
            aria-label={t("instrument_picker.search_label")}
            placeholder={t(scope === "hub" ? "instrument_picker.search_hub_placeholder" : "instrument_picker.search_placeholder")}
            autoComplete="off"
            spellCheck={false}
            value={state.query}
            onChange={onInput}
            onKeyDown={onKeyDown}
          />
          {currentHub && kinds.length > 0 && !state.query && (
            <div className="ds-ipicker-kinds" role="group" aria-label={t("instrument_picker.kinds")}>
              {kinds.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={(state.kind ?? kinds[0]) === kind}
                  onClick={() => {
                    setState((current) => ({ ...current, kind, active: 0 }));
                    inputRef.current?.focus({ preventScroll: true });
                  }}
                >
                  {kindLabel(kind)}
                </button>
              ))}
            </div>
          )}
          {presets.length > 0 && (
            <div className="ds-ipicker-presets" role="group" aria-label={t("instrument_picker.presets")}>
              {presets.map(({ preset, instrument }) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => choose({ type: "instrument", id: instrument.id, hub: currentHub!, instrument, recent: false })}
                >
                  {t(`instrument_picker.preset.${preset}`)}
                  <span className="ds-ipicker-preset-code">{instrument.code}</span>
                </button>
              ))}
            </div>
          )}
          <ul className="ds-ipicker-list" role="listbox" id={listId} aria-label={label}>
            {options.map((option, index) => {
              const selected = index === state.active;
              if (option.type === "hub") {
                const hub = option.hub;
                return (
                  <li
                    key={option.id}
                    id={optionId(option)}
                    role="option"
                    aria-selected={selected}
                    className="ds-ipicker-option"
                    data-active={selected ? "true" : undefined}
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => choose(option)}
                  >
                    <span className="ds-ipicker-code">{hub.hub}</span>
                    <span className="ds-ipicker-name">{hubName(hub)}</span>
                    <span className="ds-ipicker-meta">{unitLabel(hub.nativeUnit)}</span>
                    {hub.simulated && <span className="ds-ipicker-sim">{t("instrument_picker.sim")}</span>}
                    {scope === "instrument" && <span className="ds-ipicker-more" aria-hidden="true">›</span>}
                  </li>
                );
              }
              const item = option.instrument;
              return (
                <li
                  key={option.id}
                  id={optionId(option)}
                  role="option"
                  aria-selected={selected}
                  className="ds-ipicker-option"
                  data-active={selected ? "true" : undefined}
                  data-thin={item.thin ? "true" : undefined}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => choose(option)}
                >
                  <span className="ds-ipicker-code">{state.level === "tenor" && !state.query && !option.recent ? item.code : item.label}</span>
                  <span className="ds-ipicker-name">
                    {/* Under a kind's tab the kind is already said: only search results and
                        recent picks name it. */}
                    {[
                      option.recent ? t("instrument_picker.recent") : null,
                      state.level !== "tenor" || state.query ? kindLabel(item.productKind) : null,
                      item.thin ? t("instrument_picker.thin", { count: item.observations }) : null,
                    ].filter(Boolean).join(" · ")}
                  </span>
                  <span className="ds-ipicker-meta">
                    {unitLabel(item.nativeUnit)}
                    {item.lastAsOf ? ` · ${displayTime(item.lastAsOf, "")}` : ""}
                  </span>
                  {item.simulated && <span className="ds-ipicker-sim">{t("instrument_picker.sim")}</span>}
                </li>
              );
            })}
          </ul>
          {options.length === 0 && (
            <p className="ds-ipicker-empty" role="status">
              {data.hubs.length === 0 ? t("instrument_picker.no_series") : t("instrument_picker.no_match")}
            </p>
          )}
          {hidden > 0 && <p className="ds-ipicker-hidden">{t("instrument_picker.more_by_search", { count: hidden })}</p>}
          <p className="ds-ipicker-hint">{t(scope === "hub" ? "instrument_picker.keys_hub" : "instrument_picker.keys")}</p>
        </div>
      )}
    </div>
  );
}
