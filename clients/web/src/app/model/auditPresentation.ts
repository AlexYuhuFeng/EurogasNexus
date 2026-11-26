/**
 * The audit trail in words. The server records stable codes (`auth.local.login`,
 * `identity_principal:principal-4c67…`, `listed`); the trail shows what happened in the reader's
 * language and keeps the code in the cell's title for anyone matching a log line.
 *
 * An action is a phrase when one is written (`audit.action.<code>`), otherwise its words put
 * together (`audit.word.<word>`); a word with no entry stays as written, so a new server code
 * is still readable and never a raw dotted key.
 */
type Translate = (key: string, options?: Record<string, unknown>) => string;

function has(t: Translate, key: string): boolean {
  const text = t(key, { defaultValue: "" });
  return text !== "" && text !== key;
}

function joinWords(words: string[], language: string): string {
  const zh = language.startsWith("zh");
  const text = words.filter(Boolean).join(zh ? "" : " ").trim();
  return zh || text === "" ? text : text.charAt(0).toUpperCase() + text.slice(1);
}

function wordsOf(code: string, t: Translate): string[] {
  return code
    .split(/[._:\s-]+/)
    .filter(Boolean)
    .map((word) => (has(t, `audit.word.${word}`) ? t(`audit.word.${word}`) : word));
}

/** The action in words ("Signed in", "User access changed", "LNG terminal terms update"). */
export function auditActionLabel(code: string, t: Translate, language: string): string {
  if (!code) return "–";
  if (has(t, `audit.action.${code}`)) return t(`audit.action.${code}`);
  return joinWords(wordsOf(code, t), language);
}

/** The outcome in words ("listed" -> "Viewed"; unknown outcomes keep their words). */
export function auditOutcomeLabel(code: string, t: Translate, language: string): string {
  if (!code) return "–";
  if (has(t, `audit.outcome.${code}`)) return joinWords([t(`audit.outcome.${code}`)], language);
  return joinWords(wordsOf(code, t), language);
}

/**
 * The resource in words: its kind, and for a person their name (`identity_principal:<id>` ->
 * "user · Test risk manager"). A job or other record id is left to the title: it means nothing
 * on screen.
 */
export function auditResourceLabel(
  resource: string,
  t: Translate,
  language: string,
  principalNames: ReadonlyMap<string, string> = new Map(),
): string {
  if (!resource) return "–";
  const [kind, ...rest] = resource.split(":");
  const id = rest.join(":");
  const kindLabel = has(t, `audit.resource.${kind}`)
    ? t(`audit.resource.${kind}`)
    : joinWords(wordsOf(kind ?? "", t), language);
  const name = id ? principalNames.get(id) : undefined;
  return name ? `${kindLabel} · ${name}` : kindLabel;
}

/** Who acted: the person's name when the directory knows the principal, else the principal. */
export function auditActorLabel(principal: string, principalNames: ReadonlyMap<string, string> = new Map()): string {
  return principalNames.get(principal) ?? principal;
}
