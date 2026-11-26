/**
 * A hub's other names, to the one code the backend's market registry gives it
 * (`domain/ontology/markets.py`, `aliases`). The Danish hub is one hub written two ways: ETF
 * on EEX, GTF OTC and at Energinet; CEGH's trading point is the VTP; PEG's zone is TRF. A
 * code read from a person, a stored preference or a feed goes through `canonicalHub` so it
 * never becomes a second row of the same hub.
 */
export const HUB_ALIASES: Readonly<Record<string, string>> = {
  GTF: "ETF",
  GASPOINT: "ETF",
  VTP: "CEGH",
  TRF: "PEG",
};

/** The registry code of a hub code or alias (`GTF` → `ETF`); anything else upper-cased. */
export function canonicalHub(code: string): string {
  const upper = (code || "").trim().toUpperCase();
  return HUB_ALIASES[upper] ?? upper;
}
