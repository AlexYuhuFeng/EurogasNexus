/**
 * RecordPicker (UX_REFERENCE rule 25, the live principle): choose a record that exists (a
 * contract in execution, a counterparty, a book, a trader, a point, a terminal) instead of typing
 * its identifier. One level of InstrumentPicker's pattern and look: a trigger showing the
 * choice by name (its id on hover), a search box over at most twelve options, recent picks
 * first, keyboard complete (ArrowUp/Down, Home/End, Enter, Escape), a bottom sheet on a phone.
 *
 * `multiple` keeps the panel open and ticks choices; `allowManual` adds "Use 'X', entered by
 * hand" for the cases a form must still accept (a counterparty not yet in any record), and
 * `onChange` then says the value was typed, so the result can name its manual inputs.
 *
 * Logic: `recordPickerModel.ts`. Styles: `instrumentPicker.css` (`ds-ipicker-*`).
 */
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Spinner } from "./Spinner";

import {
  moveActive,
  pickerEntries,
  readRecent,
  withRecent,
  writeRecent,
  type PickerEntry,
  type RecordOption,
} from "./recordPickerModel";
import { Icon } from "./Icon";

export type { RecordOption } from "./recordPickerModel";

export interface RecordChoice {
  id: string;
  /** True when the reader typed the value instead of choosing a record. */
  manual: boolean;
}

interface CommonProps {
  label: string;
  /** null while the records are loading. */
  options: readonly RecordOption[] | null;
  /** Remembers recent picks per kind of record ("counterparty", "contract"). */
  recentKey?: string;
  placeholder?: string;
  /** Said when there is nothing to choose from: why, and where records come from. */
  emptyText?: string;
  allowManual?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

interface SingleProps extends CommonProps {
  multiple?: false;
  value: string | null;
  onChange: (choice: RecordChoice | null) => void;
}

interface MultipleProps extends CommonProps {
  multiple: true;
  value: readonly string[];
  onChange: (ids: string[]) => void;
}

export type RecordPickerProps = SingleProps | MultipleProps;

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function RecordPicker(props: RecordPickerProps) {
  const { label, options, recentKey, placeholder, emptyText, allowManual = false, disabled = false, id, className } = props;
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const storageKey = recentKey ? `egn.record-picker.${recentKey}` : null;
  const [recent, setRecent] = useState<string[]>(() => (storageKey ? readRecent(storage(), storageKey) : []));
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const baseId = useId();
  const listId = `${baseId}-list`;
  const labelId = `${baseId}-label`;
  const records = options ?? [];
  const chosen = props.multiple ? props.value : props.value ? [props.value] : [];
  const { entries, hidden } = pickerEntries(records, query, { recent: props.multiple ? [] : recent, allowManual: allowManual && !props.multiple });
  const current = entries[Math.min(active, entries.length - 1)];
  const entryId = (entry: PickerEntry, index: number) => `${baseId}-opt-${index}`;

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    setQuery("");
    setActive(0);
    if (returnFocus) triggerRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    inputRef.current?.focus({ preventScroll: true });
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, close]);

  const choose = (entry: PickerEntry) => {
    if (entry.type === "manual") {
      if (!props.multiple) props.onChange({ id: entry.text, manual: true });
      close(true);
      return;
    }
    if (entry.option.disabled) return;
    if (props.multiple) {
      const has = props.value.includes(entry.option.id);
      props.onChange(has ? props.value.filter((item) => item !== entry.option.id) : [...props.value, entry.option.id]);
      return;
    }
    if (storageKey) {
      const next = withRecent(recent, entry.option.id);
      setRecent(next);
      writeRecent(storage(), storageKey, next);
    }
    props.onChange({ id: entry.option.id, manual: false });
    close(true);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const next = moveActive(active, event.key, entries.length);
    if (next !== null) {
      event.preventDefault();
      setActive(next);
      document.getElementById(entryId(entries[next], next))?.scrollIntoView?.({ block: "nearest" });
      return;
    }
    if (event.key === "Enter" && current) {
      event.preventDefault();
      choose(current);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (query) setQuery("");
      else close(true);
    }
  };

  const byId = new Map(records.map((option) => [option.id, option]));
  const names = chosen.map((value) => byId.get(value)?.label ?? value);
  const triggerText = options === null
    ? t("record_picker.loading")
    : names.length === 0
      ? placeholder ?? t("record_picker.choose")
      : props.multiple && names.length > 2
        ? t("record_picker.n_chosen", { first: names[0], count: names.length - 1 })
        : names.join(", ");
  const manualValue = !props.multiple && props.value && !byId.has(props.value) && options !== null;

  return (
    <div
      ref={rootRef}
      className={["ds-ipicker", "ds-rpicker", className].filter(Boolean).join(" ")}
      data-record-picker={id ?? ""}
      data-open={open ? "true" : "false"}
      onBlur={() =>
        window.setTimeout(() => {
          const focused = document.activeElement;
          if (focused && rootRef.current && !rootRef.current.contains(focused)) close(false);
        }, 0)
      }
    >
      <span className="ds-ipicker-label" id={labelId}>{label}</span>
      <button
        ref={triggerRef}
        type="button"
        className="ds-ipicker-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-labelledby={`${labelId} ${baseId}-value`}
        title={chosen.join(", ") || undefined}
        disabled={disabled || options === null}
        onClick={() => (open ? close(false) : setOpen(true))}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span id={`${baseId}-value`} className="ds-ipicker-value">
          {options === null ? (
            // The ring shows it is reading; the words stay for assistive technology (aria-labelledby).
            <>
              <Spinner size="xs" />
              <span className="ds-visually-hidden">{triggerText}</span>
            </>
          ) : (
            triggerText
          )}
        </span>
        {manualValue && <span className="ds-ipicker-meta">{t("record_picker.typed")}</span>}
        <Icon name="chevron-down" size="xs" className="ds-ipicker-caret" />
      </button>
      {open && (
        <div className="ds-ipicker-panel" role="dialog" aria-label={label} data-level="hub">
          <div className="ds-ipicker-head">
            <span className="ds-ipicker-title">{label}</span>
            <button type="button" className="ds-ipicker-close" onClick={() => close(true)} aria-label={t("instrument_picker.close")}>
              <Icon name="close" />
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
            aria-activedescendant={current ? entryId(current, Math.min(active, entries.length - 1)) : undefined}
            aria-label={t("record_picker.search", { what: label })}
            placeholder={t("record_picker.search", { what: label })}
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <ul className="ds-ipicker-list" role="listbox" id={listId} aria-label={label} aria-multiselectable={props.multiple ? true : undefined}>
            {entries.map((entry, index) => {
              const isActive = index === Math.min(active, entries.length - 1);
              if (entry.type === "manual") {
                return (
                  <li
                    key="manual"
                    id={entryId(entry, index)}
                    role="option"
                    aria-selected={isActive}
                    className="ds-ipicker-option"
                    data-active={isActive ? "true" : undefined}
                    data-manual="true"
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => choose(entry)}
                  >
                    <span className="ds-ipicker-code">{t("record_picker.use_typed", { text: entry.text })}</span>
                    <span className="ds-ipicker-name">{t("record_picker.typed_hint")}</span>
                  </li>
                );
              }
              const { option } = entry;
              const ticked = chosen.includes(option.id);
              return (
                <li
                  key={option.id}
                  id={entryId(entry, index)}
                  role="option"
                  aria-selected={props.multiple ? ticked : isActive}
                  aria-disabled={option.disabled ? true : undefined}
                  className="ds-ipicker-option"
                  data-active={isActive ? "true" : undefined}
                  data-ticked={ticked ? "true" : undefined}
                  title={option.id}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => choose(entry)}
                >
                  {props.multiple && <span className="ds-ipicker-tick" aria-hidden="true">{ticked ? "✓" : ""}</span>}
                  <span className="ds-ipicker-code">{option.label}</span>
                  <span className="ds-ipicker-name">
                    {[entry.recent ? t("instrument_picker.recent") : null, option.detail].filter(Boolean).join(" · ")}
                  </span>
                </li>
              );
            })}
          </ul>
          {entries.length === 0 && (
            <p className="ds-ipicker-empty" role="status">
              {records.length === 0 ? emptyText ?? t("record_picker.none") : t("instrument_picker.no_match")}
            </p>
          )}
          {hidden > 0 && <p className="ds-ipicker-hidden">{t("instrument_picker.more_by_search", { count: hidden })}</p>}
          {props.multiple && (
            <button type="button" className="ds-rpicker-done" onClick={() => close(true)}>
              {t("record_picker.done")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
