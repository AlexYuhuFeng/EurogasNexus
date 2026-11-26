/**
 * Simulated scope (AGENTS.md rule 17): one rule for every page that can show simulated figures.
 *
 * - **All simulated**: one quiet source line ("Source: simulated prices") stands where the page's
 *   provenance is read, and the per-figure "sim" pill is dropped, because a pill on every value
 *   says nothing a reader has not been told. It is a source mark, never a banner or a callout.
 * - **Mixed**: the pill stays on each simulated figure, so a simulated value can never be read as
 *   a market price beside real ones.
 * - **None**: nothing is shown.
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
  notice,
  children,
}: {
  scope: SimulatedScopeKind;
  /**
   * The one source line said when every figure is simulated; omitted for a part of the page
   * whose source line is already shown elsewhere on it (the scope then only drops the pills).
   */
  notice?: string;
  children: ReactNode;
}) {
  return (
    <ScopeContext.Provider value={scope}>
      {scope === "all" && notice && (
        <p className="simulated-scope-notice" data-simulated-scope="all">
          {notice}
        </p>
      )}
      {children}
    </ScopeContext.Provider>
  );
}
