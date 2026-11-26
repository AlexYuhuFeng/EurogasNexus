/**
 * After sign-in, ask the server for the heavy first-screen reads of the tabs this user can open,
 * one at a time while the browser is idle, so the first open of a tab finds them computed.
 *
 * The server keeps the last result of each heavy read per caller and refreshes it when the data
 * behind it changes (`application/warm_views.py`); a read it already holds answers in
 * milliseconds. Without this, the first open of Prices, Fundamentals, Spreads, Limits or Reports
 * computed its read while the user waited (1-10 s each). The answers are not used here: the
 * page reads them again, and the server answers from what it kept, with its computed time.
 *
 * - Only the reads of tasks the identity can use (the step's permission); the server still
 *   authorises every request.
 * - One read at a time, each after the browser was idle, and none while the page is hidden.
 * - Once per signed-in principal; a change of principal or sign-out stops the run.
 * - A failed read is skipped: this is a head start, never a dependency.
 */

export interface WarmUpStep {
  readonly id: string;
  /** Any one of these makes the step useful (none listed: every commercial identity). */
  readonly permissions: readonly string[];
  readonly read: (signal: AbortSignal) => Promise<unknown>;
}

export type IdleWait = (signal: AbortSignal) => Promise<void>;

/** The steps an identity with `permissions` would use, in their order. */
export function warmUpStepsFor(permissions: readonly string[] | null | undefined, steps: readonly WarmUpStep[]): WarmUpStep[] {
  const held = new Set(permissions ?? []);
  return steps.filter((step) => step.permissions.length === 0 || step.permissions.some((name) => held.has(name)));
}

/** Wait until the browser is idle (and the page visible), at most `timeoutMs`. */
export const browserIdle: IdleWait = (signal) =>
  new Promise<void>((resolve) => {
    if (signal.aborted) return resolve();
    const done = () => {
      signal.removeEventListener("abort", done);
      resolve();
    };
    signal.addEventListener("abort", done);
    const attempt = () => {
      if (signal.aborted) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        setTimeout(attempt, 2_000);
        return;
      }
      const idle = (globalThis as { requestIdleCallback?: (cb: () => void, options?: { timeout: number }) => number }).requestIdleCallback;
      if (idle) idle(done, { timeout: 3_000 });
      else setTimeout(done, 500);
    };
    attempt();
  });

/** Run `steps` one at a time, each after `idle`; how many answered. Stops when `signal` aborts. */
export async function runWarmUp(steps: readonly WarmUpStep[], signal: AbortSignal, idle: IdleWait = browserIdle): Promise<number> {
  let answered = 0;
  for (const step of steps) {
    await idle(signal);
    if (signal.aborted) break;
    try {
      await step.read(signal);
      answered += 1;
    } catch {
      // A head start only: the page reads it itself when opened.
    }
  }
  return answered;
}

let running: { principal: string; controller: AbortController } | null = null;

/** Start the warm-up for `principal` unless it already ran or runs for them; stop another's. */
export function startWarmUp(
  principal: string | null | undefined,
  permissions: readonly string[] | null | undefined,
  steps: readonly WarmUpStep[],
  idle: IdleWait = browserIdle,
): Promise<number> | null {
  if (running && running.principal === principal) return null;
  stopWarmUp();
  if (!principal) return null;
  const controller = new AbortController();
  running = { principal, controller };
  return runWarmUp(warmUpStepsFor(permissions, steps), controller.signal, idle);
}

/** Stop a running warm-up (sign-out, change of principal). */
export function stopWarmUp(): void {
  running?.controller.abort();
  running = null;
}
