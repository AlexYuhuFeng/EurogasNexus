import { useEffect } from "react";
import { notifyDesktopClientReady } from "@/api/client";
import {
  IDENTITY_SIGNAL_NAME,
  identitySignalPayload,
  type IdentitySignalPayload,
} from "@/stores/authGate";
import type { AuthState } from "@/stores/workspaceLoading";

declare global {
  interface Window {
    /**
     * Desktop startup signal. The Tauri shell owns window visibility, but only
     * this web app knows whether identity resolved, so the latest resolution is
     * published here (and re-emitted as the `eurogas:identity` event) for the
     * native side to read. The payload is non-secret: a state, a principal id
     * and a timestamp - never a token, cookie or credential.
     */
    __EUROGAS_IDENTITY__?: IdentitySignalPayload;
  }
}

/**
 * Publish identity resolution for the desktop shell. The Rust side can poll
 * `window.__EUROGAS_IDENTITY__` or subscribe to the `eurogas:identity` event;
 * both receive the same payload after every resolution change.
 */
export function useIdentitySignal(authState: AuthState, principalId: string | null): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const payload = identitySignalPayload(authState, principalId, new Date().toISOString());
    window.__EUROGAS_IDENTITY__ = payload;
    window.dispatchEvent(new CustomEvent(IDENTITY_SIGNAL_NAME, { detail: payload }));
    if (authState !== "unknown") {
      // Once resolution is known the desktop shell may reveal its window. The
      // call is idempotent, so a later sign-in or sign-out is harmless.
      void notifyDesktopClientReady();
    }
  }, [authState, principalId]);
}
