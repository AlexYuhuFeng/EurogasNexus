/**
 * "Method" next to a risk figure (NUM-05, UX-05): what the figure is, what it includes and what
 * it leaves out, from the server's method note. Opens in a Popover; nothing is fetched, the
 * note travels with the figure.
 *
 * Text comes from the note's i18n keys (`risk.method.<key>.*`) filled with its params, falling
 * back to the server's English sentence when a key is not in this build.
 */
import type { RiskMethodNoteDTO } from "@/api/client";
import { Popover } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function translated(t: Translate, key: string | undefined, fallback: string, params: Record<string, unknown>): string {
  if (!key) return fallback;
  const text = t(key, params);
  return !text || text === key ? fallback : text;
}

/** The note's three parts in the reader's language. Exported for tests. */
export function methodText(method: RiskMethodNoteDTO, t: Translate) {
  const params = { ...method.params } as Record<string, unknown>;
  return {
    summary: translated(t, method.i18n?.summary, method.summary, params),
    includes: method.includes.map((text, index) => translated(t, method.i18n?.includes?.[index], text, params)),
    excludes: method.excludes.map((text, index) => translated(t, method.i18n?.excludes?.[index], text, params)),
  };
}

export function MethodNote({
  method,
  subject,
  t,
}: {
  method: RiskMethodNoteDTO | null | undefined;
  /** What the figure is, for the accessible name ("Value at risk"). */
  subject: string;
  t: Translate;
}) {
  if (!method) return null;
  const label = t("method.label", { subject });
  const text = methodText(method, t);
  const asOf = Object.entries(method.inputs_as_of ?? {}).filter(([, value]) => Boolean(value));
  return (
    <Popover
      label={label}
      id="method"
      width="md"
      placement="bottom-start"
      trigger={(props) => (
        <button {...props} type="button" className="ds-note-trigger" aria-label={label} title={label} data-method={method.key}>
          {t("method.button")}
        </button>
      )}
    >
      <p className="ds-method-summary">{text.summary}</p>
      {text.includes.length > 0 && (
        <>
          <h3>{t("method.includes")}</h3>
          <ul>{text.includes.map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      )}
      {text.excludes.length > 0 && (
        <>
          <h3>{t("method.excludes")}</h3>
          <ul>{text.excludes.map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      )}
      {asOf.length > 0 && (
        <p className="ds-popover-meta">
          {t("method.inputs_as_of")}: {asOf.map(([name, value]) => `${t(`method.input.${name}`, { defaultValue: name })} ${String(value).slice(0, 16).replace("T", " ")}`).join(" · ")}
        </p>
      )}
    </Popover>
  );
}
