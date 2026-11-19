/**
 * Change notices from the server, delivered on the session's existing stream (`/api/stream/
 * alerts` carries `map` notices: a group and a time, no row). A page answers a notice with a
 * conditional read of its own (a 304 when nothing it shows changed), so the notice itself never
 * carries data the page would have to entitle.
 *
 * The stream's state is published too: while it is down a page falls back to a conditional poll.
 */
type Listener = (payload: unknown) => void;

const listeners = new Map<string, Set<Listener>>();
const statusListeners = new Set<(open: boolean) => void>();
let open = false;

export function publishChangeNotice(topic: string, payload: unknown): void {
  for (const listener of listeners.get(topic) ?? []) listener(payload);
}

export function onChangeNotice(topic: string, listener: Listener): () => void {
  const set = listeners.get(topic) ?? new Set<Listener>();
  set.add(listener);
  listeners.set(topic, set);
  return () => {
    set.delete(listener);
  };
}

export function setChangeStreamOpen(next: boolean): void {
  if (next === open) return;
  open = next;
  for (const listener of statusListeners) listener(open);
}

export function changeStreamOpen(): boolean {
  return open;
}

export function onChangeStreamStatus(listener: (open: boolean) => void): () => void {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
}
