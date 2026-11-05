/** Server-sent events parsing, shared by EventSource-less (fetch) streams. */

/** Dispatch one server-sent event block ("event:" / "data:" lines) to its handler. */
export function dispatchSseBlock(block: string, handlers: Record<string, (data: unknown) => void>): void {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return;
  const handler = handlers[event];
  if (!handler) return;
  const text = data.join("\n");
  try {
    handler(JSON.parse(text));
  } catch {
    handler(text);
  }
}

