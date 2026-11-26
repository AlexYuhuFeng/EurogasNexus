/**
 * The answer bar's controller: one query, three tiers, cheapest and most certain first.
 *
 * - Tier 1 is computed synchronously on every keystroke (`app/answer/route.ts`): no network,
 *   no model. The units authority's factors and the held ECB rates are read once per session
 *   (the ontology read and one price-conversion read) and kept; until they arrive a conversion
 *   gives no answer rather than a guessed one.
 * - Tier 2 runs 250 ms after typing stops, through the existing public reads, and a newer
 *   query aborts the older read. Reads are shared for a minute so a refined query does not
 *   fetch the same payload again.
 * - Tier 3 runs only when asked (Enter on the Ask row, or `?` in front): `POST
 *   /api/analysis/ask`, cancellable with Escape.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type AskAnswerDTO, type UnitsReferenceDTO } from "@/api/client";
import type { AnswerView, LookupState } from "@/app/answer/answerModel";
import type { GlossaryEntry } from "@/app/answer/glossary";
import { instantAnswer } from "@/app/answer/instant";
import { intentKey } from "@/app/answer/intent";
import { lookup, type AnswerReads } from "@/app/answer/lookups";
import { routeQuery, type Route } from "@/app/answer/route";
import { fxHeldFrom, type FxHeld } from "@/app/answer/units";
import { useLiveTopics } from "@/app/hooks/useLive";

export const LOOKUP_DEBOUNCE_MS = 250;
const READ_TTL_MS = 60_000;

interface Reference {
  units: UnitsReferenceDTO | null;
  fx: FxHeld | null;
}

let referencePromise: Promise<Reference> | null = null;

/** The units authority's factors and the held ECB rates, read once per session. */
function loadReference(): Promise<Reference> {
  if (!referencePromise) {
    referencePromise = Promise.all([
      api.ontology().then((response) => response.data.units ?? null).catch(() => null),
      api.priceConversion(1, "EUR/MWh", "ECB").then((response) => fxHeldFrom(response.data)).catch(() => null),
    ]).then(([units, fx]) => {
      // A failed read is tried again next time the bar opens, not remembered as empty.
      if (!units) referencePromise = null;
      return { units, fx };
    });
  }
  return referencePromise;
}

const readCache = new Map<string, { at: number; value: Promise<unknown> }>();

function shared<T>(key: string, read: () => Promise<T>): Promise<T> {
  const hit = readCache.get(key);
  if (hit && Date.now() - hit.at < READ_TTL_MS) return hit.value as Promise<T>;
  const value = read();
  readCache.set(key, { at: Date.now(), value });
  value.catch(() => readCache.delete(key));
  return value;
}

/**
 * The reads tier 2 uses. A shared read is not tied to one query's AbortSignal (another query
 * may be waiting on it); the look-up itself is abandoned when its query is stale.
 */
const reads = (units: () => UnitsReferenceDTO | null): AnswerReads => ({
  deskToday: () => shared("today", () => api.deskToday().then((r) => r.data)),
  normalizedPrices: () => shared("normalized", () => api.normalizedMarketObservations(undefined, 2000).then((r) => ({ rows: r.data, limit: 2000 }))),
  quotes: () => shared("quotes", () => api.marketQuotes().then((r) => r.data)),
  storage: (code) => shared(`storage:${code}`, () => api.storageTargetTrajectory(code).then((r) => r.data)),
  lng: () => shared("lng", () => api.lngObservations().then((r) => r.data)),
  outages: () => shared("outages", () => api.outages(14).then((r) => r.data)),
  ladder: () => shared("ladder", () => api.positionLadder(12).then((r) => r.data)),
  credit: () => shared("credit", () => api.creditExposure().then((r) => r.data)),
  contracts: () => shared("contracts", () => api.upstreamContracts().then((r) => r.data)),
  normalise: (body) => shared(`normalise:${JSON.stringify(body)}`, () => api.normaliseMarket(body).then((r) => r.data)),
  units,
});

export type AskState =
  | { status: "idle" }
  | { status: "running"; question: string; stage: "reading" | "writing" }
  | { status: "done"; question: string; result: AskAnswerDTO }
  | { status: "error"; question: string };

export interface AnswerBarOptions {
  open: boolean;
  query: string;
  glossary: readonly GlossaryEntry[];
  permissions: readonly string[];
  language: string;
}

export interface AnswerBarController {
  route: Route;
  /** The answer row to show now: tier 1, or tier 2 once its read has answered. */
  answer: AnswerView | null;
  lookup: LookupState;
  /** Whether an Ask row is offered for this query. */
  askOffered: boolean;
  askQuestion: string;
  /** Whether this caller may have the model answer (the server re-checks). */
  aiAllowed: boolean;
  ask: AskState;
  runAsk: (question?: string) => void;
  cancelAsk: () => void;
}

export function useAnswerBar({ open, query, glossary, permissions, language }: AnswerBarOptions): AnswerBarController {
  const [reference, setReference] = useState<Reference>({ units: null, fx: null });
  const [lookupState, setLookupState] = useState<LookupState>({ status: "idle" });
  const [askState, setAskState] = useState<AskState>({ status: "idle" });
  const askAbort = useRef<AbortController | null>(null);
  const unitsRef = useRef<UnitsReferenceDTO | null>(null);
  unitsRef.current = reference.units;

  // Read once a signed-in caller is known (not at the first keystroke), and again on open
  // if the first read failed.
  // Both reads are commercial market reads: a platform administrator (no market.read) is
  // refused them, and the refusal showed as reads that did not load (2026-11-17).
  const signedIn = permissions.length > 0;
  const marketAllowed = permissions.includes("market.read");
  useEffect(() => {
    if (!marketAllowed || (!open && !signedIn)) return;
    let live = true;
    void loadReference().then((loaded) => { if (live) setReference(loaded); });
    return () => { live = false; };
  }, [open, signedIn, marketAllowed]);

  const bookAllowed = permissions.includes("portfolio.read");
  const aiAllowed = permissions.includes("analysis.query");
  const zh = language.toLowerCase().startsWith("zh");

  const route = useMemo(
    () => routeQuery(query, { units: reference.units, fx: reference.fx, glossary, bookAllowed, zh }),
    [query, reference, glossary, bookAllowed, zh],
  );
  const instant = useMemo(() => instantAnswer(route), [route]);
  const key = route.tier === 2 ? intentKey(route.intent) : null;

  // A quote on the open bar follows the market: a price notice drops the cached market reads
  // and looks the answer up again (it stays on screen meanwhile).
  const [marketVersion, setMarketVersion] = useState(0);
  useLiveTopics(
    ["prices"],
    () => {
      for (const cached of ["quotes", "normalized", "today"]) readCache.delete(cached);
      setMarketVersion((version) => version + 1);
    },
    { enabled: open && marketAllowed },
  );

  useEffect(() => {
    if (!open || route.tier !== 2 || !key) {
      setLookupState({ status: "idle" });
      return;
    }
    const intent = route.intent;
    const controller = new AbortController();
    setLookupState((current) => (current.status === "done" && current.key === key ? current : { status: "loading", key }));
    const timer = window.setTimeout(() => {
      lookup(intent, reads(() => unitsRef.current), controller.signal)
        .then((answer) => { if (!controller.signal.aborted) setLookupState({ status: "done", key, answer }); })
        .catch(() => { if (!controller.signal.aborted) setLookupState({ status: "error", key }); });
    }, LOOKUP_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
    // `route` changes identity with every keystroke; the intent key is what matters.
  }, [open, key, marketVersion]);

  const cancelAsk = useCallback(() => {
    askAbort.current?.abort();
    askAbort.current = null;
    setAskState({ status: "idle" });
  }, []);

  // A new query or closing the bar leaves the answer that was asked.
  useEffect(() => {
    if (!open) cancelAsk();
  }, [open, cancelAsk]);

  const askQuestion = route.tier === 3 ? route.question : query.trim().replace(/^[?？]/, "").trim();

  const runAsk = useCallback(
    (question?: string) => {
      const text = (question ?? askQuestion).trim();
      if (text.length < 3) return;
      askAbort.current?.abort();
      const controller = new AbortController();
      askAbort.current = controller;
      setAskState({ status: "running", question: text, stage: "reading" });
      // The server reads the desk's figures, then (when the model may be used) writes.
      const writing = window.setTimeout(() => {
        if (!controller.signal.aborted && aiAllowed) {
          setAskState((current) => (current.status === "running" ? { ...current, stage: "writing" } : current));
        }
      }, 700);
      api
        .ask(text, zh ? "zh-CN" : "en", { signal: controller.signal })
        .then((response) => {
          if (!controller.signal.aborted) setAskState({ status: "done", question: text, result: response.data });
        })
        .catch(() => {
          if (!controller.signal.aborted) setAskState({ status: "error", question: text });
        })
        .finally(() => window.clearTimeout(writing));
    },
    [askQuestion, aiAllowed, zh],
  );

  const answer = instant ?? (lookupState.status === "done" && lookupState.key === key ? lookupState.answer : null);

  return {
    route,
    answer,
    lookup: lookupState,
    askOffered: route.tier === 3,
    askQuestion,
    aiAllowed,
    ask: askState,
    runAsk,
    cancelAsk,
  };
}
