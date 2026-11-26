/**
 * Basemap place names in the app language.
 *
 * OpenFreeMap's OpenMapTiles data sometimes carries both Chinese variants joined in `name:zh`
 * ("德国/德國"), so a Chinese desk read the same place twice. Chinese therefore prefers
 * `name:zh-Hans`, then uses `name:zh` only when it is one variant (no "/") and not just the
 * traditional name repeated in `name:zh-Hant`, and otherwise falls back to `name:en`. Two
 * variants are never joined: a label is one name.
 */

export type BasemapNameProperties = Record<string, unknown>;

const isChinese = (language: string): boolean => language.toLowerCase().startsWith("zh");

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** The one place name to show for a basemap feature, or null when the data has none. */
export function basemapName(properties: BasemapNameProperties, language: string): string | null {
  const latin = text(properties["name:en"]) || text(properties["name:latin"]) || text(properties.name) || null;
  if (!isChinese(language)) return latin;
  const hans = text(properties["name:zh-Hans"]);
  if (hans) return hans;
  const chinese = text(properties["name:zh"]);
  const traditional = text(properties["name:zh-Hant"]);
  // A joined "simplified/traditional" string, or the traditional name repeated, is not shown.
  if (chinese && !chinese.includes("/") && chinese !== traditional) return chinese;
  return latin;
}

/**
 * The MapLibre `text-field` expression for the language. It mirrors `basemapName`: MapLibre
 * expressions cannot call JavaScript, so the same order is written as a `coalesce`/`case`.
 */
export function basemapNameExpression(language: string): unknown {
  const fallback = ["get", "name:en"];
  if (!isChinese(language)) {
    return ["coalesce", fallback, ["get", "name:latin"], ["get", "name"]];
  }
  const chinese = ["coalesce", ["get", "name:zh"], ""];
  const traditional = ["coalesce", ["get", "name:zh-Hant"], ""];
  const singleVariant = [
    "all",
    ["==", ["index-of", "/", chinese], -1],
    ["!=", chinese, traditional],
  ];
  return [
    "coalesce",
    ["get", "name:zh-Hans"],
    ["case", singleVariant, ["get", "name:zh"], fallback],
    fallback,
    ["get", "name:latin"],
    ["get", "name"],
  ];
}
