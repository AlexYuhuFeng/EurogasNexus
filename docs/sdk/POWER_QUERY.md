# Refreshing market data in Excel with Power Query

How to load the price strip, settlements and closes, and FX fixings into an Excel workbook
that refreshes from a Eurogas Nexus server, live or as known at an instant. This how-to covers
Excel on the desktop (Data > Get Data). The figures are for decision support and research;
nothing here trades or nominates.

## What you can refresh

Three market reads answer `format=csv`: one header line, then one flat row per figure. The
header names and their order are fixed (new columns are only ever added at the end), and the
header is the same whether there are rows or not, so a query you build once keeps working.

| Read | Path | Useful parameters | One row per |
|---|---|---|---|
| Price strip (curve) | `/api/market/prices` | `hub` (one or more, comma-separated), `start` (`YYYY-MM`), `months` (1 to 36), `side` (`mid`, `bid`, `ask`), `as_of` | hub and delivery month |
| Settlements and closes | `/api/market/observations` | `as_of` | stored observation |
| FX fixings | `/api/market/fx` | `as_of` | fixing |

- **Price strip.** The price every screen uses for that hub and month, with `kind`
  (`live_tick`, `settlement`, `firm_mark` and so on), `source_system`, `price_as_of_utc`
  and `state`. A month with no price still has its row, with the price columns empty.
  Simulated prices are left out unless you add `include_simulated=true`, and the row then
  says `simulated` is true.
- **`as_of`** (ISO 8601 UTC, for example `2026-11-20T17:30:00Z`) answers what the server knew
  at that instant. Each figure is shown at the revision current then, in the columns
  `revision`, `revision_basis`, `published_at_utc` and `known_from_utc`. A figure the server
  first received later is left out. Without `as_of` you get the current figures, and those
  columns are empty in the observation and FX files.
- **Text encoding.** The file is UTF-8 with a byte-order mark. Times are ISO 8601. Decimals use
  a full stop. A nested value (`metadata_json`) is written as JSON text.

## What you need

- The server's address, for example `https://nexus.example.internal`. Ask your administrator.
- The **deployment token** of that server, which your administrator gives you.
- Your own **identity key** (`nexus_<key_id>_<secret>`). Create it yourself in
  Settings > Your API keys. Give it only the data scopes the workbook needs. With the key,
  the workbook reads as you: you see only the source families you are entitled to, and
  licensed reads are counted against your name. See [Authentication](AUTHENTICATION.md).

The two credentials go in two request headers, `X-Eurogas-Api-Key` and `X-Eurogas-Identity`.
Never put either in the address.

**The keys live in the workbook.** Power Query keeps parameter values inside the file. Anyone
you send the workbook to can read them and act as you. Keep such workbooks to yourself. If one
leaves your hands, revoke the key in Settings > Your API keys, which takes effect at once, and
create a new one.

## Build the query

1. In Excel, open Data > Get Data > From Other Sources > Blank Query, then Advanced Editor.
2. Create two text parameters (Home > Manage Parameters): `NexusDeploymentToken` and
   `NexusIdentityKey`. Paste the values there, not into the query.
3. Paste the query below and change the address and the parameters of the read.

```powerquery-m
let
    // The server's address, without /api.
    Server = "https://nexus.example.internal",
    // Leave AsOf empty ("") for the current figures, or give an ISO UTC instant.
    AsOf = "",
    Parameters = [
        hub = "TTF,NBP",
        start = "2027-01",
        months = "12",
        format = "csv"
    ],
    Query = if AsOf = "" then Parameters else Record.AddField(Parameters, "as_of", AsOf),
    Response = Web.Contents(
        Server,
        [
            RelativePath = "api/market/prices",
            Query = Query,
            Headers = [
                #"X-Eurogas-Api-Key" = NexusDeploymentToken,
                #"X-Eurogas-Identity" = NexusIdentityKey
            ]
        ]
    ),
    Csv = Csv.Document(Response, [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Csv, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"value", type number},
            {"value_mwh", type number},
            {"revision", Int64.Type},
            {"simulated", type logical}
        },
        "en-US"
    )
in
    Typed
```

Keep the server address in `Server` and the path in `RelativePath`, and pass the parameters
as `Query`. Excel can then refresh the query without asking about a new data source each time
a parameter changes. The `"en-US"` culture reads the decimal point correctly whatever your
Windows regional settings.

For settlements or FX, set `RelativePath` to `api/market/observations` or `api/market/fx`,
keep `format = "csv"` (and `as_of` if you want it), and type the `price` or `rate` column as a
number instead.

These two reads are paged (newest first, at most `limit` rows a page, default 1,000, up to
10,000). Ask for the range the sheet needs with `from_utc` and `to_utc` (ISO 8601 with an
offset, e.g. `2026-11-01T00:00:00Z`), and `product` for one hub or product (`TTF`). The
response headers say whether the range was complete: `X-Eurogas-Has-More: false`. When it is
`true`, narrow the range or raise `limit`; a sheet never receives part of a range without the
header saying so.

4. When Excel asks how to connect to the server, choose **Anonymous** in the credentials
   dialog. The query's own headers carry your credentials. Excel's Windows, Basic and
   organisational sign-ins are not used.
5. Close & Load. Refresh with Data > Refresh All. To refresh on a timer, open Query
   Properties and set "Refresh every N minutes". Pick an interval that fits how often the
   source changes: settlements change once a day, FX fixings once a day, and the strip moves
   with live ticks while the market is open.

## Licensed data in a workbook

A CSV is a file, so the server applies the export decision of every licensed source family
the rows came from:

- **Allowed.** The data is public (ECB, ENTSOG, GIE and the like), or the firm's licence
  allows redistribution.
- **Restricted.** The file is delivered for internal use only. It must not leave the firm.
  The response says so in the `X-Eurogas-Export-Decision` and `X-Eurogas-Export-Restrictions`
  headers, which Excel does not show. Treat any workbook that reads a licensed family
  (EEX, ICE, Platts, Argus and so on) as internal unless you know the licence allows more.
- **Denied.** The family's export terms are not registered. The server refuses the file with
  403 `export_denied`, which Excel shows as an access error. Ask your administrator to
  register the licence. Reading the same figures on screen is unaffected.

Each refresh of a licensed read is counted, by family and day, as a read and as a CSV export
against your identity. That is how the firm's licence reporting works. It is not a charge.

## When a refresh fails

| Excel shows | Likely cause | What to do |
|---|---|---|
| 401 `public_api_token_missing` or 403 `public_api_token_invalid` | Deployment token missing or wrong, or the identity key put in its place | Check `NexusDeploymentToken` and the header names |
| 401 `identity_bearer_missing`, 403 `identity_key_invalid`, `identity_key_revoked` or `identity_key_expired` | Identity key mistyped, revoked or expired | Create a new key in Settings > Your API keys |
| 403 `export_denied` | Licensed family without registered export terms | Ask your administrator to register the licence |
| 422 `as_of_invalid` or `as_of_in_future` | `AsOf` is not an ISO instant, or is later than now | Use the form `2026-11-20T17:30:00Z` |
| 422 `hub_unknown`, `start_invalid`, `months_out_of_range` | A strip parameter is wrong | Check the hub code, `YYYY-MM` and 1 to 36 months |
| Columns are empty | You are not entitled to the family, or no figure is held | Ask for the data scope, or check the source's freshness |

See [Authentication](AUTHENTICATION.md) for every identity refusal, [Troubleshooting](TROUBLESHOOTING.md) for the server's error envelope, and
[Data revisions](../operations/DATA_REVISIONS.md) for how revisions are kept.
