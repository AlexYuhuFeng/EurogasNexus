/**
 * The answer bar's controller: one query, three tiers, cheapest and most certain first.
 *
 * - Tier 1 is computed synchronously on every keystroke (`app/answer/route.ts`): no network,
 *   no model. The units authority's factors and the held ECB rates are read once per session
 *   (the ontology read and one price-conversion read) and kept; until they arrive a conversion
 *   gives no answer rather than a guessed one.
 * - Tier 2 runs 250 ms after typing stops, through the existing public reads, and a newer
 *   query aborts the older read. Reads are shared for a minute so a refined query does not
 *   fetch the same payload again; when every read a look-up needs is already held, it runs at
 *   once, with no debounce (the Today read is warmed when the bar opens, so "NBP" answers as
 *   it is typed).
 * - A live answer (a spread, a screen price) is read again while the bar is open: on each
 *   market update the session receives when a quote stream is open (`liveStamp`, the store's
 *   own quotes), and otherwise every {@link LIVE_ANSWER_REFRESH_MS} through the same reads.
 *   Nothing is read while the bar is closed.
 * - Tier 3 runs only when asked (Enter on the Ask row, or `?` in front): `POST
 *   /api/analysis/ask`, cancellable with Escape.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type AskAnswerDTO, type MarketQuoteDTO, type UnitsReferenceDTO } from "@/api/client";
import type { AnswerView, LookupState } from "@/app/answer/answerModel";
import type { GlossaryEntry } from "@/app/answer/glossary";
import { instantAnswer } from "@/app/answer/instant";
import { intentKey, type LookupIntent } from "@/app/answer/intent";
import { lookup, type AnswerReads } from "@/app/answer/lookups";
import { routeQuery, type Route } from "@/app/answer/route";
import { fxHeldFrom, type FxHeld } from "@/app/answer/units";

export const LOOKUP_DEBOUNCE_MS = 250;
const READ_TTL_MS = 60_000;
/** How often a live answer is read again while the bar is open and no quote stream is. */
export const LIVE_ANSWER_REFRESH_MS = 10_000;
/** With a quote stream open, a safety re-read; the stream's updates drive the rest. */
export const LIVE_ANSWER_STREAM_SAFETY_MS = 60_000;
/** At most one re-read per this many ms however fast the stream ticks. */
const LIVE_ANSWER_MIN_GAP_MS = 1_000;

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

const readCache = new Map<string, { at: number; value: Promise<unknown>; settled: boolean }>();

function shared<T>(key: string, read: () => Promise<T>): Promise<T> {
  const hit = readCache.get(key);
  if (hit && Date.now() - hit.at < READ_TTL_MS) return hit.value as Promise<T>;
  const value = read();
  const entry = { at: Date.now(), value: value as Promise<unknown>, settled: false };
  readCache.set(key, entry);
  value.then(() => { entry.settled = true; }, () => { if (readCache.get(key) === entry) readCache.delete(key); });
  return value;
}

/** Whether a shared read is held and answered (so a look-up on it needs no debounce). */
function held(key: string): boolean {
  const hit = readCache.get(key);
  return Boolean(hit && hit.settled && Date.now() - hit.at < READ_TTL_MS);
}

/**
 * The shared reads a look-up needs before it can answer without the network. A kind not
 * listed is always debounced.
 */
export function readsFor(intent: LookupIntent): readonly string[] | null {
  switch (intent.kind) {
    case "price":
      return intent.tenor.kind === "prompt" ? ["quotes"] : intent.tenor.kind === "front" ? ["today"] : null;
    case "storage":
      return intent.country ? null : ["today"];
    case "lng":
      return intent.country ? ["lng"] : ["today"];
    case "norway":
      return ["today"];
    case "outages":
      return ["outages"];
    case "spread":
      return ["quotes", "today"];
    case "portfolio":
      return ["ladder", "credit", "cargoes"];
    case "credit":
      return ["credit"];
    case "contract":
      return ["contracts"];
    default:
      return null;
  }
}

/** Drop the reads a live answer moves with, so the next look-up reads them again. */
function expireLive(): void {
  for (const key of ["quotes", "today"]) readCache.delete(key);
}

/**
 * The reads tier 2 uses. A shared read is not tied to one query's AbortSignal (another query
 * may be waiting on it); the look-up itself is abandoned when its query is stale.
 */
const reads = (
  units: () => UnitsReferenceDTO | null,
  fx: () => FxHeld | null,
  /** The session's own quotes while a quote stream keeps them current; else null. */
  streamQuotes: () => readonly MarketQuoteDTO[] | null,
): AnswerReads => ({
  deskToday: () => shared("today", () => api.deskToday().then((r) => r.data)),
  normalizedPrices: () => shared("normalized", () => api.normalizedMarketObservations(undefined, 2000).then((r) => ({ rows: r.data, limit: 2000 }))),
  quotes: () => {
    const streamed = streamQuotes();
    return streamed?.length ? Promise.resolve([...streamed]) : shared("quotes", () => api.marketQuotes().then((r) => r.data));
  },
  storage: (code) => shared(`storage:${code}`, () => api.storageTargetTrajectory(code).then((r) => r.data)),
  lng: () => shared("lng", () => api.lngObservations().then((r) => r.data)),
  outages: () => shared("outages", () => api.outages(14).then((r) => r.data)),
  ladder: () => shared("ladder", () => api.positionLadder(12).then((r) => r.data)),
  credit: () => shared("credit", () => api.creditExposure().then((r) => r.data)),
  contracts: () => shared("contracts", () => api.upstreamContracts().then((r) => r.data)),
  normalise: (body) => shared(`normalise:${JSON.stringify(body)}`, () => api.normaliseMarket(body).then((r) => r.data)),
  units,
  fx,
  // The book's cargoes, as the map's "Our book" view reads them (own cargoes only are shown).
  cargoes: () => shared("cargoes", () => api.mapSituation(14).then((r) => r.data.cargoes ?? [])),
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
  /**
   * The session's latest market update (the store's `marketLastUpdatedAtUtc`): with a quote
   * stream open, a live answer is read again when it moves.
   */
  liveStamp?: string | null;
  /** Whether a quote stream is open (the store's `streamingActive`). */
  streaming?: boolean;
  /** The store's quotes, used for a live answer while the stream keeps them current. */
  liveQuotes?: readonly MarketQuoteDTO[];
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

export function useAnswerBar({
  open, query, glossary, permissions, language, liveStamp = null, streaming = false, liveQuotes,
}: AnswerBarOptions): AnswerBarController {
  const [reference, setReference] = useState<Reference>({ units: null, fx: null });
  const [lookupState, setLookupState] = useState<LookupState>({ status: "idle" });
  const [askState, setAskState] = useState<AskState>({ status: "idle" });
  /** Bumped to read a live answer again; it belongs to the query it was bumped for. */
  const [tickState, setTickState] = useState<{ key: string | null; count: number }>({ key: null, count: 0 });
  const askAbort = useRef<AbortController | null>(null);
  const unitsRef = useRef<UnitsReferenceDTO | null>(null);
  unitsRef.current = reference.units;
  const fxRef = useRef<FxHeld | null>(null);
  fxRef.current = reference.fx;
  const streamRef = useRef<readonly MarketQuoteDTO[] | null>(null);
  streamRef.current = streaming && liveQuotes?.length ? liveQuotes : null;

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
    // Warm the Today read when the bar opens: a hub, storage or Norway then answers as typed.
    if (open) void shared("today", () => api.deskToday().then((r) => r.data)).catch(() => undefined);
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
  const tick = tickState.key === key ? tickState.count : 0;
  const bump = useCallback(() => setTickState((current) => ({ key, count: current.key === key ? current.count + 1 : 1 })), [key]);

  useEffect(() => {
    if (!open || route.tier !== 2 || !key) {
      setLookupState({ status: "idle" });
      return;
    }
    const intent = route.intent;
    const controller = new AbortController();
    // A re-read of a live answer keeps the figure it has until the new one is in.
    setLookupState((current) => (current.status === "done" && current.key === key ? current : { status: "loading", key }));
    const needs = readsFor(intent);
    // The session's streamed quotes count as held.
    const ready = tick > 0 || Boolean(needs && needs.every((name) => (name === "quotes" && streamRef.current) || held(name)));
    const run = () => {
      lookup(intent, reads(() => unitsRef.current, () => fxRef.current, () => streamRef.current), controller.signal)
        .then((answer) => { if (!controller.signal.aborted) setLookupState({ status: "done", key, answer }); })
        .catch(() => {
          // A failed re-read keeps the figure shown; a first read says it failed.
          if (!controller.signal.aborted) setLookupState((current) => (current.status === "done" && current.key === key ? current : { status: "error", key }));
        });
    };
    const timer = window.setTimeout(run, ready ? 0 : LOOKUP_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
    // `route` changes identity with every keystroke; the intent key is what matters.
  }, [open, key, tick]);

  const liveShown = open && lookupState.status === "done" && lookupState.key === key && Boolean(lookupState.answer.live);
  // No stream: read a live answer again on a short interval, only while it is shown.
  useEffect(() => {
    if (!liveShown) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      expireLive();
      bump();
    }, streaming ? LIVE_ANSWER_STREAM_SAFETY_MS : LIVE_ANSWER_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [liveShown, streaming, bump]);
  // A stream open: each market update the session receives reads it again (at most once a second).
  const lastLive = useRef(0);
  const seenStamp = useRef(liveStamp);
  useEffect(() => {
    const moved = seenStamp.current !== liveStamp;
    seenStamp.current = liveStamp;
    if (!moved || !liveShown || !streaming || !liveStamp) return;
    const wait = Math.max(0, lastLive.current + LIVE_ANSWER_MIN_GAP_MS - Date.now());
    const timer = window.setTimeout(() => {
      lastLive.current = Date.now();
      bump();
    }, wait);
    return () => window.clearTimeout(timer);
  }, [liveShown, streaming, liveStamp, bump]);

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
