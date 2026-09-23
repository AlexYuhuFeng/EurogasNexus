/**
 * The trading context a session resolves to (Architecture V2 Wave 5).
 *
 * Trader context mirrors what the operator is looking at, so it is only restored from the URL inside
 * an authenticated session; while identity is unresolved or denied it is the default, and nothing is
 * written back to history. The rule lives outside the hook because the store's projection reads
 * depend on it: the resolved context is published before a sign-in's first workspace batch builds
 * its requests, so no projection is asked about the default the previous session left behind.
 */

import { isIdentityGateOpen, type AuthState } from "@/stores/workspaceLoading";

import { readTraderContextUrl, resolveTraderContext } from "./contextUrl.ts";
import { DEFAULT_TRADER_CONTEXT, type TraderContext } from "./traderContext.ts";

export interface SessionTraderContextInputs {
  readonly authState: AuthState;
  /** The location's query string. */
  readonly search: string;
  readonly persisted: Partial<TraderContext>;
}

/** The context the session stands in: the URL's, or the default when there is no session. */
export function resolveSessionTraderContext({
  authState,
  search,
  persisted,
}: SessionTraderContextInputs): TraderContext {
  if (!isIdentityGateOpen(authState)) return DEFAULT_TRADER_CONTEXT;
  return resolveTraderContext(readTraderContextUrl(search), persisted);
}
