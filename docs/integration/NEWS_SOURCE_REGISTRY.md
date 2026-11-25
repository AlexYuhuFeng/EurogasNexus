# News source registry (NEWS-1)

Chinese summary: 新闻来源登记册。只有条款允许商业再利用、订阅地址登记在发布方自有域名、
无需凭据且 robots.txt 允许的来源才会被轮询；授权来源与禁止再利用的来源列明原因且从不轮询。

The product reads news, policy and geopolitical events only from sources whose published
terms permit reuse in a commercial product. This page is the engineering record of each
source: what it is, where it is read, its terms as they were read (quotation, address, day)
and what is kept of an item. The machine-readable registry is
`src/eurogas_nexus/domain/news/sources.py` (`NEWS_SOURCES`, `EXCLUDED_SOURCES`), served in
`meta.sources` of `GET /api/news`. Legal confirms the current terms before a production
deployment, as for every row of [DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md).

## Rules the poller enforces

- A source is polled only when its reuse is `permitted`, its terms were read (day recorded) and
  its feed address is recorded, `https`, without credentials, on the publisher's own host or a
  subdomain of that host (`feed_url_refusal`); an operator override on another host is refused.
- No source needs a credential, an account or a sign-up.
- The host's `robots.txt` is read first, under this product's User-Agent
  `EurogasNexus-NewsPoller/1.0`; a missing file allows, an unreadable one does not.
- Each source has its own poll interval; requests are conditional (ETag, Last-Modified).
- What is kept follows the terms: `summary` keeps the title, link, times and the feed's own
  summary (plain text, at most 1,200 characters); `title_only` keeps the title, link and times.
- Every item records its source, URL, publisher, published and retrieved times, content hash
  (SHA-256 of title, kept text, link and publication time), language and licence note with
  the attribution line.
- Feeds are parsed with the standard library after refusing any DOCTYPE or entity
  declaration, bounded at 2 MB and 200 entries; markup and scripts are removed and only
  `http(s)` links are kept.

## Sources read

| Source id | Publisher | Read from | Interval | Keeps | Licence and terms (quoted) | Terms page, read on | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `remit-umm` | Market participants via inside-information platforms | The REMIT messages the platform already holds (latest version per message); nothing is fetched | 5 min | Figures as the message states them | Held under the REMIT row of [DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md): the import records the platform and refuses one without published reuse terms unless the firm confirmed them | DATA_SOURCE_TERMS.md, 2026-11-14 | In use |
| `govuk-desnz` | UK Department for Energy Security and Net Zero | `https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero.atom` | 60 min | Summary | Open Government Licence v3.0: "Most content on GOV.UK is subject to Crown copyright protection and is published under the Open Government Licence"; "We make most of the content on GOV.UK available through feeds for other websites and applications to use." Attribution: "Contains public sector information licensed under the Open Government Licence v3.0" | https://www.gov.uk/help/terms-conditions, 2026-11-24 | Polled; the address follows GOV.UK's organisation feed pattern and is confirmed by the first successful poll |
| `ec-energy-news` | European Commission, DG Energy | Feed address not yet recorded | 60 min | Summary | CC BY 4.0 (Commission Decision 2011/833/EU): "content owned by the EU on this website is licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0) licence ... reuse is allowed, provided appropriate credit is given and changes are indicated"; logos and third-party content excluded. Attribution: "© European Union, CC BY 4.0; summary shortened" | https://commission.europa.eu/legal-notice_en, 2026-11-24 | Terms permit; not polled until an operator records the feed address on the Commission's host |
| `eurlex-oj-energy` | Publications Office of the EU (EUR-Lex) | Feed address not yet recorded | 6 h | Summary | "You can reuse EUR-Lex data, free of charge, subject to copyright conditions." Attribution: "© European Union, https://eur-lex.europa.eu" | https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html, 2026-11-24 | Terms permit; EUR-Lex offers predefined RSS feeds, the address for energy acts is to be recorded |
| `acer-news` | ACER | Feed address not yet recorded | 6 h | Title only | Information may be reproduced "for non-commercial and commercial purposes" "provided that the Agency is always acknowledged as the source of the material"; the same notice restricts "Licensed Material" without saying which, so titles and links only. Attribution: "Source: ACER" | https://www.acer.europa.eu/legal-notice, 2026-11-24 | Terms permit; not polled until the address is recorded |

The build environment had no outbound network, so no feed address could be confirmed and no
feed was recorded live. The test fixtures under `tests/fixtures/news/` are constructed in the
published formats (each says so in its header, with the feed address and the date) and are
not copies of publisher content.

Recording a feed address: `python scripts/ops/poll_news_sources.py --source ec-energy-news
--feed-url https://<the publisher's own host>/<feed path> --commit` reads it once on that host
(refused on any other); to keep it, set `feed_url` in the registry in a reviewed change.

## Sources considered and left out

| Source | Reuse | Why it is not read |
| --- | --- | --- |
| Reuters, Bloomberg, Argus, ICIS, S&P Global Platts, Montel | Licensed | Per-subscriber licences ([DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md), licensed families). A paid news feed would be a licensed family under GOV-1, read with the customer's own credentials; none is shipped or polled |
| EEX website news | Forbidden | "... may be copied, reprinted, published, transmitted ... without the prior written approval of EEX AG" except "a single copy for exclusive personal, non-commercial use" (https://www.eex.com/en/disclaimer, read 2026-11-18) |
| LNG terminal operators' websites (Fluxys LNG, Elengy) | Forbidden | Fluxys: "No reproduction ... without the prior written consent of Fluxys"; Elengy: reproduction "without the express permission of Elengy is strictly forbidden" (DATA_SOURCE_TERMS.md, read 2026-11-18). Their outages reach the product as REMIT messages, which they must publish |
| National regulators (Bundesnetzagentur, CRE, ARERA, Ofgem and others) | Unknown | Terms not read in this build; each is added with its quoted terms once read |

## What happens to an item

1. Tags are deterministic (`domain/news/tagging.py`): hub codes as written, countries, a
   gazetteer of terminals, pipelines, TSOs and fields with the hubs they serve, the vessels of
   the firm's open cargoes; event types outage, sanction, policy or regulation, weather, strike,
   geopolitical; a capacity change.
2. An outage item that names the asset (terminal, pipeline or field) of a held, open REMIT
   message is linked to it; its `news.published` event carries that outage's dependency key, so
   opportunities depending on it are re-evaluated.
3. Items touching a contract's hub, an open cargo's vessel or terminal, or a hub the firm
   nominates at reach the trader, the LNG desk or the scheduler through M7 routing, with dedupe
   and a 30-minute cooldown.
4. The reader sees the item with its source link and terms, what it touches in the books they
   may see, and the note "what this means for my book": the rule note, each sentence citing its
   evidence; on request the AI note (AI use `news_note`), shown only when every sentence passes
   the grounding check, labelled "AI-generated".
