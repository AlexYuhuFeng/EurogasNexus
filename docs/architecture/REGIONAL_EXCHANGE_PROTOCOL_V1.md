# Regional exchange protocol v1

This is a contract foundation for independent installations in Europe (`EU`),
China (`CN`), Canada (`CA`) and Singapore (`SG`). It does not deploy peers,
replicate databases or enable an import/export endpoint. These are logical region
labels: `EU` denotes the European deployment domain in this protocol, not proof of
European Union membership or a legally sufficient residency boundary. Operators
must define the actual country, cloud region and permitted processing locations.

## Implemented contract

- [Exchange envelope JSON Schema](schemas/exchange-envelope-v1.schema.json), version
  `eurogas.exchange/1`, describes untrusted metadata independently of the transport.
- `domain/federation/contracts.py` validates metadata and offers the offline
  `verify_delivery_integrity` function for exact-byte integrity, binding and expiry.
- No HTTP route, network call, worker, peer trust store or database table is created.
  The existing application and its export routes do not automatically use this
  protocol. A valid envelope is **not** authorization to send or receive data.

The Python validator includes semantic checks beyond JSON Schema: sender/actor and
origin/owner namespace consistency, distinct deployment identifiers, ordered UTC
expiry bounded to seven days, and unique provenance references. Other-language
implementations must implement these rules too; JSON Schema alone is insufficient.

| Field | Meaning and authority |
| --- | --- |
| `contract_version` | Exactly `eurogas.exchange/1`; reject unknown versions without fallback. |
| `transfer_id` | UUID for this immutable transfer attempt, scoped by source deployment in storage. |
| `idempotency_key` | Caller-generated request key scoped by source deployment; retries reuse the same key and immutable metadata/payload. |
| `source`, `destination` | Deployment IDs plus region labels. A receiver matches them against configured, authenticated peer identities and its own deployment record. Submitted labels cannot select authority. |
| `actor` | Source-qualified principal requesting the transfer. A local principal ID alone is never globally unique. |
| `owner` | Origin-qualified owner of the resource. A sender cannot replace the owner when forwarding an imported resource. |
| `resource` | Origin deployment, kind (`strategy` or `dataset`), stable ID and immutable revision. It is a reference, not a definition of the payload schema. |
| `purpose`, `classification` | Declared intended processing and sensitivity. Receiver policy can increase restrictions, never trust a downgrade supplied by a sender. |
| `source_visibility` | `PRIVATE`, `PUBLIC` or `GROUPS` in the originating installation. Public means local sharing, not anonymous/global availability. Group IDs are not imported or mapped by name. |
| `provenance_refs` | Bounded references to source evidence/version lineage; a receiver must resolve trusted evidence before use. No credentials or secret URLs belong here. |
| `policy_ref`, `owner_approval_ref`, `entitlement_ref` | References to independently verifiable decisions. Strings supplied in an envelope do not prove that those decisions exist or remain valid. Required even for public resources. |
| `created_at`, `expires_at` | Timezone-aware UTC; positive lifetime no longer than seven days. Offline verification rejects expired envelopes and creation more than five minutes ahead of the receiver clock. This is transfer validity, not a data retention period. |
| `payload` | Registered resource schema ID, supported media type, exact byte count and lowercase SHA-256. Hash the transmitted plaintext artifact bytes before transport encryption; do not silently reserialize JSON or normalize CSV. |

Identifiers and references are bounded, extra metadata fields are rejected, and the
local integrity helper defaults to a 16 MiB payload ceiling. A future transport must
enforce request-body limits **while reading**, before materializing a payload in
memory; the offline helper only sees already-supplied bytes. Compression is not part
of v1. Do not add decompression without separate decoded-size/resource limits.

`schema_id` is matched to a receiver-configured allowlist, not dereferenced as a URL.
Payload decoding and resource-schema validation remain separate mandatory checks.
No strategy/dataset export payload format or content sanitization is introduced by
this envelope. Register concrete, versioned payload schemas before enabling exchange.

## Ownership and sharing boundary

A trader's strategy is private by default. The owner controls local publication and
group sharing through the strategy authorization layer. Neither `PUBLIC` nor a group
share implies cross-region transfer consent, permission to export licensed inputs,
or permission for a receiver to edit the owner's strategy.

Before sending any strategy revision, the sender must resolve a current owner
approval bound to the exact resource revision, destination deployment, purpose and
payload digest, plus the applicable license/entitlement and regional transfer policy.
A delegated sender still needs this owner's decision. The receiver must verify the
decision through a trusted issuer/record and apply its own policy. `owner_approval_ref`
is only a correlation pointer; this module cannot verify it.

A received strategy must initially be an immutable, quarantined external snapshot.
Preserve its origin and owner; do not upsert into a local strategy with a matching ID,
automatically publish it, recreate source groups, grant editing rights, or execute it.
An authorized local fork is a different resource with explicit lineage. Revocation
of local sharing and withdrawal of cross-region consent are distinct lifecycle events.
Neither can erase an already exported copy without a separately implemented remote
revocation/retention process.

## Future HTTP binding (reserved, not mounted)

When a real transport is justified, reserve `/api/federation/v1/transfers` for an
explicit opt-in receiver. Until then, the application exposes no receiving endpoint
and no exchange may be inferred from this specification.

The initial binding should accept an envelope plus a single bounded artifact, require
HTTPS and authenticated deployment peers (mutual TLS or a tightly scoped audience-bound
service credential), and map the authenticated peer to one configured deployment ID.
Existing user sessions, legacy deployment API tokens, claimed region headers and work
modes must not become cross-installation authority. Do not forward client bearer
credentials, provider secrets, local session cookies or database credentials.

A receiver must, in order:

1. Apply transport/body limits and authenticate the peer before disclosing metadata.
2. Validate the envelope version and schema, configured source/destination bindings,
   expiry, payload schema identifier and exact-byte integrity.
3. Resolve current policy, owner approval and license/entitlement evidence; validate
   payload content and apply the destination's regional/organizational restrictions.
4. In one transaction, reserve a durable idempotency receipt and quarantine the artifact.
   Never report acceptance before this commit. Quarantine is not a business import.
5. Record an immutable audit outcome, then perform any explicitly authorized import in
   a separate governed step. Reads and local publication remain destination-authorized.

Reserve response semantics: `401` unauthenticated peer, `403` policy refusal,
`409` idempotency conflict, `413` body limit, `422` unsupported/malformed contract,
`202` durably quarantined. An exact completed retry returns the stored receipt without
reimporting. Reusing an idempotency key or transfer ID with a different bound envelope
or payload must fail `409`. Do not include inaccessible resource details in errors.
These status semantics are a future binding, not implemented API behavior.

## Storage contract (future migration, not applied)

Keep regional application databases independent. A federation ledger must be added
only when the authenticated receiver and operational lifecycle exist. Minimum logical
records are:

| Record | Required key and data |
| --- | --- |
| Deployment trust | Unique deployment ID; region plus actual residency configuration; authenticated issuer/key fingerprints; allowed audiences/schema IDs; enabled state. Trust changes audited and operator-controlled. |
| Transfer receipt | Primary key `(source_deployment_id, transfer_id)`; unique `(source_deployment_id, idempotency_key)`; destination; exact bound-envelope digest and payload digest/size; resource origin/ID/revision; state; created/expiry/received timestamps; approval/policy/entitlement references; denial code. |
| Quarantined artifact | Receipt foreign key, local opaque storage reference, encryption-key reference, integrity digest, retention deadline, quarantine/import state. Never store caller-supplied filesystem paths as storage targets. |
| Revocation/retention event | Immutable origin-qualified resource/revision/approval reference, issuer, effective time, reason, acknowledged recipient and resulting state. Delivery/retry is explicit. |

Use transactions and database uniqueness for replay protection across restarts and
multiple workers; an in-memory cache is insufficient. Owner IDs must remain qualified
by origin deployment. Never use display names, email strings or role names as global
join keys. Hashes provide integrity, not signatures or issuer trust. Keep audit and
quarantine stores, backups, encryption keys and deletion jobs in the approved domain.

A receipt should transition monotonically through `QUARANTINED` to `IMPORTED` or
`REJECTED`, and later `REVOKED`/`EXPIRED` where applicable. Imported copies require
explicit handling for subsequent revocation; simply changing the ledger state does
not remove downstream exports. Detailed retention/conflict semantics must be agreed
before deploying this ledger; no background synchronization is introduced here.

## Validation and rollout

The offline tests cover version rejection, unknown fields, owner/actor namespace
mismatches, expiry, peer binding, allowlisted payload schema, size/hash mismatches,
four-region roundtrips and reproducible JSON Schema generation. They do not prove
network authentication, signatures, deployment residency, durable replay handling,
owner consent, provider licensing or receiver import safety.

Start with isolated EU/CN/CA/SG installations and explicit approved one-way exchange
only after those controls are implemented and accepted. Active-active replication,
global queries and automatic failover remain outside this low-cost foundation. See
[global deployment assessment](GLOBAL_DATA_DEPLOYMENT_ASSESSMENT.md) for current
storage/egress paths and indicative architecture cost.

## Deferred legal and implementation review

The owner prioritizes functional delivery acceptance before regional exchange.
Canada (`CA`) replaces the earlier provisional `NA` label; no released transfer
service or persisted exchange ledger requires migration. Do not enable transport
from this contract alone. Confirm the actual countries, data categories, controllers,
processors, destinations, contractual licences and applicable legal requirements
before selecting a transfer mechanism. Prefer established identity, encrypted
transport, key-management, audit and policy systems over custom security protocols.
This draft is not a legal determination or a substitute for a jurisdiction-specific
review; it establishes neither a lawful transfer basis nor compliant residency.
