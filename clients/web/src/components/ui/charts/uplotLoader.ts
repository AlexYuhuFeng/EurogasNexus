/**
 * Loads the chart library on first use, safely.
 *
 * uPlot builds a number formatter from `navigator.language` while its module evaluates. A
 * browser whose language is not a valid locale tag (a headless Chromium under the C/POSIX
 * locale reports "en-US@posix") makes that throw, and with a static import the throw took the
 * whole application down before sign-in. So the library is imported on demand, after the
 * language has been checked, and a failure leaves the chart's table view standing instead of a
 * blank page.
 */
import { useEffect, useState } from "react";
import type uPlot from "uplot";

export type UPlotConstructor = typeof uPlot;

const FALLBACK_LANGUAGE = "en-US";

/** True when `Intl` accepts the tag; the check uPlot's module would otherwise fail on. */
export function isUsableLocale(tag: unknown): boolean {
  if (typeof tag !== "string" || tag === "") return false;
  try {
    new Intl.NumberFormat(tag);
    return true;
  } catch {
    return false;
  }
}

/** Give the page a language `Intl` accepts, when the browser reports one it does not. */
export function ensureUsableLanguage(target: { language?: unknown } | undefined = globalThis.navigator): void {
  if (!target || isUsableLocale(target.language)) return;
  try {
    Object.defineProperty(target, "language", { value: FALLBACK_LANGUAGE, configurable: true });
  } catch {
    // A frozen navigator: the import below then fails and the table view stands.
  }
}

let pending: Promise<UPlotConstructor | null> | null = null;

export function loadUplot(): Promise<UPlotConstructor | null> {
  pending ??= (async () => {
    ensureUsableLanguage();
    try {
      const [library] = await Promise.all([import("uplot"), import("uplot/dist/uPlot.min.css")]);
      return library.default;
    } catch {
      return null;
    }
  })();
  return pending;
}

/** The library once loaded: `undefined` while loading, `null` when it cannot be used. */
export function useUplot(): UPlotConstructor | null | undefined {
  const [library, setLibrary] = useState<UPlotConstructor | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void loadUplot().then((loaded) => {
      // The library is itself a function: handed over bare, React would call it as a state
      // updater (with the previous state as its only argument) and the page would go blank.
      if (live) setLibrary(() => loaded);
    });
    return () => {
      live = false;
    };
  }, []);
  return library;
}
