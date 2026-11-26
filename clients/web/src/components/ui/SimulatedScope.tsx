/**
 * Simulated scope (AGENTS.md rule 17): one rule for every page that can show simulated figures.
 *
 * - **All simulated**: the page names the source once, in one quiet source line ("Source:
 *   simulated"), and the per-figure "sim" pill is dropped, because a pill on every value says
 *   nothing the source line has not said. No banner, callout or repeated tip (owner, 2026-11-26).
 * - **Mixed**: the small source tag stays on each simulated figure, so a simulated value can never
 *   be read as a market price beside real ones.
 * - **None**: nothing is shown; real figures carry only their source and as-of time.
 *
 * A page wraps its content in `<SimulatedScope scope=…>`; a marker asks `useSimulatedPills()`.
 * Shared by Today, Prices and Spreads so the three say it the same way.
 */
import { createContext, useContext, type ReactNode } from "react";

export type SimulatedScopeKind = "all" | "mixed" | "none";

const ScopeContext = createContext<SimulatedScopeKind>("mixed");

/** The scope of a set of simulated flags: all, some or none. An empty set is "none". */
export function simulatedScopeOf(flags: readonly boolean[]): SimulatedScopeKind {
  if (flags.length === 0) return "none";
  const simulated = flags.filter(Boolean).length;
  if (simulated === 0) return "none";
  return simulated === flags.length ? "all" : "mixed";
}

/** Whether a figure's own simulated pill is shown: not when the whole page is simulated. */
export function useSimulatedPills(): boolean {
  return useContext(ScopeContext) !== "all";
}

export function SimulatedScope({
  scope,
  source,
  children,
}: {
  scope: SimulatedScopeKind;
  /**
   * The quiet source line said when every figure is simulated (`simulated.source_line`); omitted
   * for a part of the page whose source is already named elsewhere on it (the scope then only
   * drops the pills).
   */
  source?: string;
  children: ReactNode;
}) {
  return (
    <ScopeContext.Provider value={scope}>
      {scope === "all" && source && (
        <p className="simulated-scope-source" data-simulated-scope="all">
          {source}
        </p>
      )}
      {children}
    </ScopeContext.Provider>
  );
}
