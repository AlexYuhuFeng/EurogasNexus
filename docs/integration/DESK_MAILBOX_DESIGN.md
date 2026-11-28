# A desk-owned mailbox the product could read (design note, not built)

Status: proposal, 2026-11-28. Depends on the office's IT policy, which is being surveyed.
Nothing here is implemented; the product reads no mailbox today.

## Why

Some announcements the desk needs reach it only by e-mail, or reach it by e-mail first
(`docs/legal/DATA_SOURCE_TERMS.md`, "Watched publications, checked 2026-11-28"):

- Grain LNG: released berthing slots are on its public bulletin board, but bids and the
  operator's replies go by e-mail on a Short Term Access Confirmation Notice;
- PRISMA's newsletter (platform and market notices);
- operators' notices to their registered shippers (Gate, Fluxys LNG, DET/Gasfin, the storage
  operators) that do not appear on a public page;
- confirmations and auction results the desk's own platform accounts send.

The owner's principle is that the desk does not watch websites; the same holds for an inbox
two people share with everything else.

## Shape

1. **One mailbox owned by the desk**, created by the office's IT (for example
   `publications@<firm domain>`), used only for subscriptions to publishers' notices. The desk
   subscribes it to each newsletter itself; the product never subscribes, registers or accepts
   terms on anyone's behalf.
2. **Read-only access for the product**: IMAP over TLS with an application password, or
   Microsoft Graph with an application registration limited to that one mailbox
   (`Mail.Read` with an application access policy), whichever the office's IT allows. The
   credential is stored as the other provider secrets are (Admin → Data sources, server side,
   never in the repository).
3. **The same mechanism as the web watch.** Each sender becomes a watched publication with
   `delivery = "email"`: its terms entry in the legal register (a newsletter's own terms decide
   whether its content may be kept), its parser into the same typed record (capacity notice,
   LNG slot window), and the same three outcomes: parsed with confidence (record updated,
   previous kept, a line in the events list), changed but not parseable (held, "needs a person
   to confirm" with a link to the message), unreachable (stated).
4. **Allow-list by sender**, not by content: only messages from a registered sender's verified
   address (SPF/DKIM pass) are read; everything else is left untouched. Messages are marked read
   by the product only in a folder it owns, so a person still sees the original.
5. **What is kept**: the message's date, sender, subject and the parsed record; the body only
   where the sender's terms allow it, otherwise a digest and the message id so a person can find
   it in the mailbox.

## Open questions for the IT survey

- Is a shared, non-personal mailbox allowed, and on which system (Exchange Online, on-premises,
  another provider)?
- Is IMAP allowed, or only Graph? Is an application registration possible?
- Retention and journaling rules for that mailbox.
- Whether the server PC may reach the mail system (the trading office's network rules).
