# Small desk: an honest screen, the clock, and AI that can be switched off

Implements [the small-desk plan](../product/SMALL_DESK_PLAN.md) section 3 items 6 and 7 and the
targets in section 5. For the person who installs and supports the desk's PC.

## 1. When something stops updating

The product promises one thing here: the last known prices and position stay on screen, marked
stale with their time, and the desk falls back to the trading screen alone.

One mechanism in the client decides whether the screen is current
(`clients/web/src/app/data/connection.ts`). It is not current when:

| What happened | How it is noticed |
|---|---|
| The browser is offline | the browser's own online state |
| The server does not answer | any API request fails at the network, or the proxy in front of the API answers 502 or 504; then `/api/health` is asked every 5 s, doubling to 30 s, until it answers |
| The live connection has gone quiet | no event for 15 s on the tab's one live stream (three heartbeats) |

While the screen is not current:

- every figure keeps its last value; nothing is blanked (the read cache keeps the last good
  answer);
- every live cell (the price board, the prompt desk, Today, the position ladder, the spreads
  board, the cargo board) stops flashing and carries a small clock mark whose tooltip says
  "Stale: the last known value, as of 09:41";
- every live key figure (Today, the position summary) says "Stale" and the time beside the value;
- every other figure on every page is muted (one rule on the app root, `data-screen-stale`);
- when the server or the browser is the cause, one calm line under the top bar says "The server
  cannot be reached. The screen shows the last known picture, as of 09:41. Rely on the trading
  screen until this clears; it clears by itself." It goes away on recovery without a click.

A feed that stops while the server is fine is caught per figure: a quote older than its source's
cadence reads stale on the board (the age now counts on with a clock, so a quote turns stale on
time even when nothing arrives), Today's figures carry their late or stale state from the server,
and the risk rows show the day of their marks.

Alerts on stale inputs say so in their own words: a credit breach or watch computed from marks
older than one business day carries "(marks from 2026-11-20, stale)" in its title and message,
and a price-move alert between closes that are no longer current carries "(stale: no close since
20 Nov)". The separate "marks behind" alert still exists.

## 2. The clock

Deals and prices are ordered by their timestamps, so the PC keeps its clock by NTP (plan section
5). The server checks it (`src/eurogas_nexus/application/clock_check.py`):

- **Synchronisation** is read from the kernel's clock discipline (`adjtimex`), which `chronyd`,
  `ntpd` and `systemd-timesyncd` all steer. A container shares the host's kernel clock, so this
  is the PC's state.
- **Offset** is measured with one SNTP query against `EUROGAS_NEXUS_NTP_SERVER` (default
  `pool.ntp.org`; `off` skips it). Without an answer the kernel's own error estimate is reported
  as `reference: kernel_estimate`.
- The check runs in the background at most every 5 minutes; reading it never waits.

**Threshold: 0.5 s.** NTP over the internet keeps a PC within tens of milliseconds, so half a
second is ten times its normal error and means synchronisation is broken, while it is still below
the one-second resolution of the exchanges' trade exports, so a deal cannot yet land in the wrong
second against the exchange's record. The clock also warns when synchronisation is off.

Where it shows:

- `GET /api/health`: `server_time_utc` and `clock` (`state`, `offset_seconds`, `synchronised`,
  `reference`, `threshold_seconds`);
- `/metrics`: `eurogas_clock_offset_seconds{reference=...}`, `eurogas_clock_synchronised`,
  `eurogas_clock_warning` (also in the Runtime page's metrics text);
- Runtime → Delivery → Clock: the server's state and this computer's clock against it.

**This computer's clock.** The client measures the browser's clock against `server_time_utc`,
taking the middle of the round trip, every ten minutes. Above **5 s** a line under the top bar
says by how much and asks for the clock to be set: ages on screen and the stale rule for quotes
run on the browser's clock. Windows synchronises its clock weekly by default and drifts by
seconds, so a lower limit would nag; 5 s still catches a clock that is wrong.

## 3. AI: off, self-hosted, bounded

AI drafts text a person reads and accepts. No calculation depends on it.

### Switch it all off

Settings → Organisation → AI → untick **AI features on** (administrators). Or through the API:

```
PUT /api/settings/organisation   {"ai_enabled": false}
```

With it off no request leaves the server for any model: the provider adapter
(`src/eurogas_nexus/llm/deepseek.py`) checks the switch before it opens any connection, and
`tests/api/test_ai_off.py` traps every network connection while it exercises every AI feature.
Every feature still answers by rule: "Why?" gives the rule text, the morning brief and the
end-of-day draft are written from their sections, Ask shows the figures, the market report is
produced without the drafted paragraph, the report plan uses its keyword rules, the alert
analysis returns no answer, the news note gives the rule note. In the client the Ask button on
an alert and the palette's AI commands disappear, and the other places say "AI is off".

Turning AI back on is a security-relevant change: where four eyes are required a second
administrator confirms it. Two further switches remain:
`EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED=false` turns AI off for the installation whatever
the administrator sets, and the per-feature switches (`ai_features`) turn one use off.

### Point it at the desk's own model

Any OpenAI-compatible chat-completions endpoint (vLLM, Ollama, llama.cpp server, or a hosted
provider):

```
EUROGAS_NEXUS_LLM_BASE_URL=http://10.0.0.20:8000/v1   # HTTPS, or plain HTTP on a private address
EUROGAS_NEXUS_LLM_MODEL=qwen2.5-32b-instruct
EUROGAS_NEXUS_LLM_PROVIDER_NAME=desk                  # a label for audit rows
```

A key is optional for a model on the firm's own network (loopback, RFC 1918, `.local`,
`.internal`): with none stored, no `Authorization` header is sent. A model elsewhere needs a key,
stored in Data Sources (provider `LLM`) or as `EUROGAS_NEXUS_LLM_API_KEY`. In the trial and
release profiles only a private endpoint can be enabled.

### Time limits

| Setting | Default | Applies to |
|---|---|---|
| `EUROGAS_NEXUS_AI_TIMEOUT_SECONDS` | 3 | interactive: Why?, Ask, the brief's lead, a question about an alert, the Copilot analysis, the report plan, a spread described in words, the news note |
| `EUROGAS_NEXUS_AI_DRAFT_TIMEOUT_SECONDS` | 240 | drafts read later: the market report editor, the background note on a new alert |

The limit is the whole call (connect, model time and reply). The call runs on a small worker
pool; the caller stops waiting at the limit and carries on without the AI part. All AI routes run
on request threads, never on the server's event loop, and no calculation waits for a model.

### What may be sent

Settings → Organisation → AI → "What the model may be sent", or
`PUT /api/settings/organisation {"ai_data_sharing": {"counterparty_names": true}}`. Both
categories are off until an administrator turns them on (four-eyed):

- **Counterparty names**: off, every name the firm's records hold (credit lines and their ETRM
  spellings, and every table with a `counterparty` column) is replaced by "Counterparty A",
  "Counterparty B"... before a message leaves, and put back in the reply.
- **Individual deals, contracts, cargoes and nominations**: off, the Copilot analysis sends no
  contract rows and the news note is written by rule when the item touches the book. Totals by
  hub, book or counterparty are still sent.

Identifiers are never sent, whatever these say (`application/ai_payloads.py`).

## 4. Performance targets

| Target | How it is held |
|---|---|
| A price change on screen within 200 ms of arriving | Server share: a price reaches every open stream at the next poll of the live poller. `tests/api/test_stream_latency.py` asserts commit to stream within one interval plus 0.35 s at 0.15 s. The interval is `EUROGAS_NEXUS_STREAM_POLL_SECONDS` (default 1.5 s); **the desk sets 0.15** to meet the target. |
| A new deal changes position and P&L within one second | A deal stored through the API (an upload, a hand entry, a correction, a close, a physical-or-financial choice) wakes the live poller at once and makes the position views (ladder, Today, limits) compute afresh; its `deals` notice reaches every open stream in milliseconds (`tests/api/test_deal_stream_latency.py`: under 1 s with the default 1.5 s poll; measured 3 to 8 ms in the container). Position pages re-read on `deals` past their 5 s price throttle (`useLiveTopics` `immediateTopics`). A deal stored by another process (the watched folder) is seen at the next poll (`EUROGAS_NEXUS_STREAM_POLL_SECONDS`; at the desk's 0.15 s, well inside the target), and the folder's own scan interval comes first. The rest is the ladder's own read time on the desk's PC (step 3 below). |
| An AI call abandoned after 3 s | `EUROGAS_NEXUS_AI_TIMEOUT_SECONDS`; `tests/unit/test_llm_provider.py` asserts it. |

On the real PC:

1. Server share: `python scripts/ops/measure_live_latency.py notice --samples 20 --gap 1` with
   the API running; it commits a mark and times its notice on `/api/stream/live`.
2. Browser share: open Market → Prices, then in the browser's developer tools record a
   performance profile while step 1 runs; the time from the stream event to the paint of the cell
   is the browser's share. Add the two; the sum is the 200 ms figure.
3. Deal to position: `python scripts/ops/measure_live_latency.py deal --book <book> --samples 10
   --gap 1` with the API running; it enters a 1 MW test deal by hand, times its `deals` notice
   and the position ladder's re-read, and cancels every test deal at the end. The browser's
   share (notice to painted figures) is timed in the browser as in step 2.
