/**
 * First-run setup, the pure part: the state each entry is in, from what the server already
 * reports (the source registry with its approval object, the credential providers, the licence
 * register), and the summary of what is on and what is left. Nothing here decides access or
 * stores a key; it reads and words.
 */

import type { CredentialProviderDTO, SetupItemDTO, SetupViewDTO } from "@/api/client";

/** The subset of a source row the flow reads. */
export interface SetupSourceFacts {
  source_id: string;
  operational_status?: string | null;
  connectivity_status?: string | null;
  credential_state?: string | null;
  approval?: { required: boolean; state: string } | null;
}

export interface SetupContext {
  sources: Record<string, SetupSourceFacts>;
  providers: Record<string, CredentialProviderDTO>;
  licensedFamilies: ReadonlySet<string>;
  userCount: number;
  /** LNG terminal tariffs held, as the setup view reports them. */
  terminalTariffs?: SetupViewDTO["terminal_tariffs"];
}

/** `on`: works; `action`: the administrator can set it up here; `later`: needs work elsewhere. */
export type SetupTone = "on" | "action" | "later" | "info";

export interface SetupItemState {
  tone: SetupTone;
  /** i18n key of the short state words. */
  key: string;
  /** The saved key's redacted preview (last characters), never the key. */
  preview?: string | null;
}

/** Whether a provider's key is available to the backend (store, environment or key file). */
export function keySaved(provider: CredentialProviderDTO | undefined): boolean {
  if (!provider) return false;
  if (provider.effective_source) return !["missing", "disabled"].includes(provider.effective_source);
  return provider.configured;
}

/** The last characters of a stored key as the server redacted it ("…a1b2"). */
export function keyPreview(provider: CredentialProviderDTO | undefined): string | null {
  const preview = provider?.redacted_preview;
  if (!preview) return null;
  const tail = preview.replace(/[^A-Za-z0-9]/g, "").slice(-4);
  return tail ? `…${tail}` : null;
}

export function itemState(item: SetupItemDTO, context: SetupContext): SetupItemState {
  const source = item.source_id ? context.sources[item.source_id] : undefined;
  const provider = item.credential_provider ? context.providers[item.credential_provider] : undefined;
  switch (item.connection) {
    case "approval":
    case "approval_and_key": {
      const state = source?.approval?.state ?? "not_approved";
      if (state === "running" || state === "approved") return { tone: "on", key: `source_approval.state.${state}` };
      if (state === "not_approved") return { tone: "action", key: "setup.state.needs_approval" };
      if (state === "approved_waiting_for_key") {
        return { tone: "action", key: "setup.state.needs_key", preview: keyPreview(provider) };
      }
      return { tone: "later", key: `source_approval.state.${state}` };
    }
    case "key":
    case "model":
      return keySaved(provider)
        ? { tone: "on", key: "setup.state.key_saved", preview: keyPreview(provider) }
        : { tone: "action", key: "setup.state.needs_key" };
    case "licensed_key":
      return keySaved(provider)
        ? { tone: "on", key: "setup.state.key_saved", preview: keyPreview(provider) }
        : { tone: "later", key: "setup.state.not_connected" };
    case "licensed_import":
    case "licensed_none":
      return item.licence_family && context.licensedFamilies.has(item.licence_family.toUpperCase())
        ? { tone: "on", key: "setup.state.licence_recorded" }
        : { tone: "later", key: "setup.state.not_connected" };
    case "open":
      return { tone: "on", key: "setup.state.runs_itself" };
    case "public_tariffs":
      return (context.terminalTariffs?.held ?? 0) > 0
        ? { tone: "on", key: "setup.state.tariffs_held" }
        : { tone: "later", key: "setup.state.tariffs_not_held" };
    case "register":
      return { tone: "info", key: "setup.state.kept_by_operations" };
    case "template":
      return { tone: "info", key: "setup.state.no_vendor" };
    case "admin":
      return context.userCount > 1
        ? { tone: "on", key: "setup.state.people_added" }
        : { tone: "action", key: "setup.state.only_you" };
    default:
      return { tone: "info", key: "setup.state.available" };
  }
}

/** The pages in order and the index helpers the flow moves with. */
export function stepIds(view: SetupViewDTO | null): string[] {
  return view?.catalogue.steps.map((step) => step.step) ?? [];
}

export function startStep(view: SetupViewDTO | null): string {
  const steps = stepIds(view);
  const current = view?.state.current_step;
  return current && steps.includes(current) && view?.state.status === "in_progress" ? current : steps[0] ?? "welcome";
}

export interface SetupSummaryRow {
  step: string;
  on: string[];
  left: string[];
}

/** Per page: what is on, and what is left to do (with the page that finishes it). */
export function setupSummary(view: SetupViewDTO, context: SetupContext): SetupSummaryRow[] {
  return view.catalogue.steps
    .filter((step) => step.items.length > 0)
    .map((step) => {
      const on: string[] = [];
      const left: string[] = [];
      for (const item of step.items) {
        const state = itemState(item, context);
        if (state.tone === "on") on.push(item.item_id);
        else if (state.tone === "action" || state.tone === "later") left.push(item.item_id);
      }
      return { step: step.step, on, left };
    });
}

/** Where a page's remaining work is finished in the product. */
export const FINISH_WHERE: Record<string, string> = {
  open_data: "setup.where.connectors",
  prices: "setup.where.licences",
  lng_shipping: "setup.where.licences",
  weather: "setup.where.connectors",
  fx_rates: "setup.where.licences",
  book: "setup.where.book",
  ai: "setup.where.connectors",
  people: "setup.where.users",
};
