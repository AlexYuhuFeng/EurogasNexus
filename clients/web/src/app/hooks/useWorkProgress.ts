/**
 * One way to show that the product is working (docs/product/UX_REFERENCE.md, rule 18).
 *
 * `useBusyAction(action, { stages })` runs an async action once at a time (a second press while it
 * runs does nothing), says it is busy, and walks named stages ("Reading prices", "Reading outages",
 * "Writing") so a reader sees progress rather than a frozen screen. Stages advance on a timer as an
 * honest estimate of where a server-side job usually is, never past the last one before the answer
 * arrives; a caller that knows better calls `advance()`. `visible` turns true only after 300 ms,
 * so a fast answer never flickers a spinner.
 *
 * `stageAt(elapsed, stages, stageMs)` is the pure part, exported for the unit test.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export const BUSY_VISIBLE_AFTER_MS = 300;
export const DEFAULT_STAGE_MS = 1800;

export function stageAt(elapsedMs: number, stageCount: number, stageMs = DEFAULT_STAGE_MS): number {
  if (stageCount <= 1) return 0;
  return Math.min(stageCount - 1, Math.floor(Math.max(0, elapsedMs) / stageMs));
}

export interface BusyAction<A extends unknown[], R> {
  run: (...args: A) => Promise<R | undefined>;
  busy: boolean;
  /** True once the action has run longer than 300 ms. */
  visible: boolean;
  stage: number;
  advance: () => void;
  error: unknown;
}

export function useBusyAction<A extends unknown[], R>(
  action: (...args: A) => Promise<R>,
  { stages = 1, stageMs = DEFAULT_STAGE_MS }: { stages?: number; stageMs?: number } = {},
): BusyAction<A, R> {
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [manual, setManual] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const running = useRef(false);
  const started = useRef(0);
  const actionRef = useRef(action);
  actionRef.current = action;

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setElapsed(Date.now() - started.current), 100);
    return () => window.clearInterval(timer);
  }, [busy]);

  const run = useCallback(async (...args: A) => {
    if (running.current) return undefined;
    running.current = true;
    started.current = Date.now();
    setElapsed(0);
    setManual(0);
    setError(null);
    setBusy(true);
    try {
      return await actionRef.current(...args);
    } catch (caught) {
      setError(caught);
      return undefined;
    } finally {
      running.current = false;
      setBusy(false);
    }
  }, []);

  return {
    run,
    busy,
    visible: busy && elapsed >= BUSY_VISIBLE_AFTER_MS,
    stage: Math.max(manual, stageAt(elapsed, stages, stageMs)),
    advance: () => setManual((value) => Math.min(stages - 1, value + 1)),
    error,
  };
}

/**
 * The same staged walk for work the component does not start itself (a read that begins when a
 * dialog opens): pass whether it is running.
 */
export function useStagedProgress(running: boolean, stages: number, stageMs = DEFAULT_STAGE_MS): { stage: number; visible: boolean } {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return undefined;
    }
    const start = Date.now();
    const timer = window.setInterval(() => setElapsed(Date.now() - start), 100);
    return () => window.clearInterval(timer);
  }, [running]);
  return { stage: stageAt(elapsed, stages, stageMs), visible: running && elapsed >= BUSY_VISIBLE_AFTER_MS };
}
