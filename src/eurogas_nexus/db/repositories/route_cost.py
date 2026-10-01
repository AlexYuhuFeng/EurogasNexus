"""Repository helpers for DB-first route-cost decision support."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.route_cost import (
    CapacityProfileRecord,
    LiveMarketMarkRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.domain.route_cost.contract_revision import (
    CAPTURE_ORIGIN_LEGACY_CAPTURE,
    ContractDisplayMetadata,
    ContractRevisionPayloadError,
    UpstreamContractEconomicSnapshot,
    map_legacy_contract_payload,
)
from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.live_markets import LiveMarketMark
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff

#: Persisted capture outcomes. ``rejected`` writes nothing at all: an invalid
#: or ambiguous legacy mapping is never stored as validated economics.
CONTRACT_REVISION_CAPTURED = "captured"
CONTRACT_REVISION_ALREADY_CAPTURED = "already_captured"
CONTRACT_REVISION_REJECTED = "rejected"

#: Stable refusal code for a legacy mapping that recorded ambiguity (the S1a
#: mapper's ``mapping_issues``), such as non-empty notes that are not a JSON
#: object. The specific recorded codes are repeated in the refusal detail.
CONTRACT_REVISION_MAPPING_AMBIGUOUS = "contract_revision_mapping_ambiguous"

#: Governed-upsert outcomes (``upsert_upstream_contract_governed``).
#: ``created`` and ``economics_updated`` inserted a captured revision;
#: ``metadata_updated`` changed stored display evidence while the captured
#: economics stayed identical; ``unchanged`` is a true replay that wrote
#: nothing at all; ``refused`` failed closed and wrote nothing.
GOVERNED_CONTRACT_CREATED = "created"
GOVERNED_CONTRACT_ECONOMICS_UPDATED = "economics_updated"
GOVERNED_CONTRACT_METADATA_UPDATED = "metadata_updated"
GOVERNED_CONTRACT_UNCHANGED = "unchanged"
GOVERNED_CONTRACT_REFUSED = "refused"

#: Stored fields that are deliberately *outside* the captured economic
#: evidence: the display name and the raw operator notes. A write that changes
#: only these has no new economics to capture, but it is still an auditable
#: mutation of the stored contract.
_DISPLAY_ONLY_CONTRACT_FIELDS = frozenset({"contract_name", "notes"})

#: Capture origins a stored revision may carry and still be served by a read.
_VERIFIED_CAPTURE_ORIGINS = (CAPTURE_ORIGIN_LEGACY_CAPTURE,)


class ContractRevisionPersistenceError(ValueError):
    """A stored contract revision could not be captured or verified.

    Attributes:
        code: Stable machine-readable refusal code.
        detail: Human-readable explanation of the refused value.
    """

    def __init__(self, code: str, detail: str) -> None:
        """Build the refusal from a stable code and a human-readable detail."""

        self.code = code
        self.detail = detail
        super().__init__(f"{code} ({detail})")


@dataclass(frozen=True, slots=True)
class ContractRevisionCaptureResult:
    """Outcome of one explicit legacy-capture attempt.

    Attributes:
        outcome: :data:`CONTRACT_REVISION_CAPTURED` when this call inserted a
            revision, :data:`CONTRACT_REVISION_ALREADY_CAPTURED` when the
            identical economic content was already the contract's latest
            revision (the original actor and timestamp are retained), or
            :data:`CONTRACT_REVISION_REJECTED` when nothing was written (no
            such contract row, an unmappable row or an ambiguous mapping).
        revision: The persisted revision row, or ``None`` when rejected.
        refusal_code: Stable code explaining a rejection, else ``None``.
        refusal_detail: Human-readable rejection detail, else ``None``.
    """

    outcome: str
    revision: UpstreamContractRevisionRecord | None
    refusal_code: str | None = None
    refusal_detail: str | None = None

    @property
    def created(self) -> bool:
        """Whether this call inserted a new revision row."""

        return self.outcome == CONTRACT_REVISION_CAPTURED


@dataclass(frozen=True, slots=True)
class GovernedContractUpsertResult:
    """Outcome of one governed insert/update of an upstream contract.

    Attributes:
        outcome: One of :data:`GOVERNED_CONTRACT_CREATED`,
            :data:`GOVERNED_CONTRACT_ECONOMICS_UPDATED`,
            :data:`GOVERNED_CONTRACT_METADATA_UPDATED`,
            :data:`GOVERNED_CONTRACT_UNCHANGED` or
            :data:`GOVERNED_CONTRACT_REFUSED`.
        contract: The persisted contract payload, or ``None`` when refused.
        latest_revision: Additive revision-identity metadata (plain values
            only, safe to return across a commit) for the newest captured
            revision after this call, or ``None`` when refused.
        previous_revision: The contract's latest captured revision before this
            call (``None`` when the contract had none, or when refused).
        captured_revision: The newest captured revision after this call, or
            ``None`` when refused.
        refusal_code: Stable code explaining a refusal, else ``None``.
        refusal_detail: Human-readable rejection detail, else ``None``.
    """

    outcome: str
    contract: dict | None
    latest_revision: dict | None
    previous_revision: UpstreamContractRevisionRecord | None
    captured_revision: UpstreamContractRevisionRecord | None
    refusal_code: str | None = None
    refusal_detail: str | None = None

    @property
    def refused(self) -> bool:
        """Whether the write failed closed and nothing was written."""

        return self.outcome == GOVERNED_CONTRACT_REFUSED


def list_tso_tariffs(session: Session) -> list[CapacityTariff]:
    """List all stored TSO tariffs as domain CapacityTariff rows.

    列出全部 TSO 费率（按国家/点位/方向/气体年排序）并映射为领域模型。

    Args:
        session: DB session.

    Returns:
        List of CapacityTariff domain rows.
    """

    rows = session.query(TsoTariffRecord).order_by(
        TsoTariffRecord.country,
        TsoTariffRecord.source_point_name,
        TsoTariffRecord.direction,
        TsoTariffRecord.gas_year,
    )
    return [_tariff_from_record(row) for row in rows.all()]


def list_upstream_contracts(session: Session) -> list[dict]:
    """List upstream resource contracts, newest update first.

    Args:
        session: DB session.

    Returns:
        List of contract payload dicts.
    """

    rows = session.query(UpstreamResourceContractRecord).order_by(
        UpstreamResourceContractRecord.updated_at_utc.desc()
    )
    return [_contract_payload(row) for row in rows.all()]


def upstream_contract_exists(session: Session, contract_id: str) -> bool:
    """Whether a mutable upstream contract row exists for this id.

    The captured-revision read uses this to tell "this contract has no
    revisions captured yet" apart from "no such contract", which a revision
    query alone cannot distinguish.

    Args:
        session: DB session.
        contract_id: Stable contract id.

    Returns:
        ``True`` when the contract identity itself is stored.
    """

    return (
        session.query(UpstreamResourceContractRecord.contract_id)
        .filter(UpstreamResourceContractRecord.contract_id == contract_id)
        .first()
        is not None
    )


def upsert_upstream_contract(session: Session, data: Mapping[str, object]) -> dict:
    """Insert or update one upstream resource contract (no commit).

    Args:
        session: DB session.
        data: Contract fields (see UpstreamContractUpsertRequest).

    Returns:
        The persisted contract payload.

    Raises:
        KeyError/ValueError: When required fields are missing/malformed.
    """

    now = datetime.now(UTC)
    contract_id = str(data["contract_id"])
    values = _normalized_contract_values(data)
    row = session.get(UpstreamResourceContractRecord, contract_id)
    if row is None:
        row = UpstreamResourceContractRecord(contract_id=contract_id, created_at_utc=now)
        session.add(row)
    _apply_contract_values(row, values)
    row.updated_at_utc = now

    session.flush()
    return _contract_payload(row)


def _normalized_contract_values(data: Mapping[str, object]) -> dict[str, object]:
    """The stored column values one upsert writes, coerced exactly once.

    Both the plain upsert and the governed upsert compare and apply these
    values, so the field list and its coercions have one home.

    Raises:
        KeyError/ValueError: When required fields are missing/malformed.
    """

    return {
        "contract_name": str(data["contract_name"]),
        "resource_type": str(data["resource_type"]),
        "delivery_point_name": str(data["delivery_point_name"]),
        "gas_year": str(data["gas_year"]),
        "delivery_quantity_mwh_per_day": float(data["delivery_quantity_mwh_per_day"]),
        "contract_price_gbp_mwh": float(data["contract_price_gbp_mwh"]),
        "settlement_frequency": str(data["settlement_frequency"]),
        "upstream_payment_lag_days": int(data["upstream_payment_lag_days"]),
        "screen_sale_cash_lag_days": int(data["screen_sale_cash_lag_days"]),
        "delivery_tolerance_pct": float(data["delivery_tolerance_pct"]),
        "nomination_tolerance_pct": float(data["nomination_tolerance_pct"]),
        "tolerance_risk_allowance_gbp_mwh": _optional_float(
            data.get("tolerance_risk_allowance_gbp_mwh")
        ),
        "annual_financing_rate_pct": float(data["annual_financing_rate_pct"]),
        "owned_entry_capacity_mwh_per_day": _optional_float(
            data.get("owned_entry_capacity_mwh_per_day")
        ),
        "owned_exit_capacity_mwh_per_day": _optional_float(
            data.get("owned_exit_capacity_mwh_per_day")
        ),
        "allowed_exit_points": _string_list(data.get("allowed_exit_points")),
        "eligible_sale_modes": _string_list(data.get("eligible_sale_modes")),
        "notes": _merged_contract_notes(data),
    }


def _apply_contract_values(
    row: UpstreamResourceContractRecord, values: Mapping[str, object]
) -> None:
    """Assign one normalized value set to a contract row (never commits)."""

    for field, value in values.items():
        setattr(row, field, value)


def _insert_contract_row_if_absent(
    session: Session,
    contract_id: str,
    values: Mapping[str, object],
    now: datetime,
) -> bool:
    """Insert one contract row, doing nothing when the identity already exists.

    ``INSERT ... ON CONFLICT (contract_id) DO NOTHING`` is the established
    ingestion pattern (``db/repositories/public_ingestion_upsert.py``): a
    concurrent create of the same identity is serialized by the primary key,
    and the loser's statement simply inserts nothing. Unlike a failed ORM
    flush, it leaves the session usable, so the same call can continue against
    the committed row instead of leaking a constraint exception.

    Returns:
        Whether this call inserted the row (``False`` when the identity already
        existed).

    Raises:
        ContractRevisionPersistenceError: When the runtime dialect has no
            reviewed conflict-tolerant insert. PostgreSQL is the runtime store
            and SQLite the focused-test fixture; nothing else is accepted.
    """

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        raise ContractRevisionPersistenceError(
            "contract_create_dialect_unsupported",
            f"{dialect!r} has no reviewed conflict-tolerant contract insert",
        )
    statement = (
        dialect_insert(UpstreamResourceContractRecord)
        .values(
            contract_id=contract_id,
            created_at_utc=now,
            updated_at_utc=now,
            **dict(values),
        )
        .on_conflict_do_nothing(index_elements=["contract_id"])
    )
    return session.execute(statement).rowcount == 1


def capture_upstream_contract_revision(
    session: Session,
    contract_id: str,
    *,
    recorded_by: str,
    recorded_at_utc: datetime,
) -> ContractRevisionCaptureResult:
    """Capture the current legacy contract row as one immutable revision.

    把当前 legacy 契约行显式捕获为不可变经济修订；失败/歧义映射绝不写库。

    The capture is explicit and caller-driven: nothing on startup, no route and
    no backfill invokes it. It reads the supplied current
    ``upstream_resource_contracts`` row, maps it with the strict S1a legacy
    mapper and persists the canonical snapshot JSON plus its content hash. The
    revision is evidence of the economics *at capture time*: the mutable legacy
    upsert keeps overwriting the source row, and later row edits never change a
    stored revision. No lifecycle status, current pointer or effective date is
    written, because none is known.

    Concurrency: the existing contract row is selected ``FOR UPDATE`` first, so
    PostgreSQL serializes captures per contract and per-contract revision
    numbers cannot collide. The select also asks the ORM to populate existing
    instances, so a contract instance already loaded in the session's identity
    map is re-read: a capture can never persist a stale row another committed
    transaction has since updated. SQLite fixtures ignore ``FOR UPDATE``; the
    PostgreSQL test covers the real lock.

    Ambiguity: when the S1a mapper records any ``mapping_issues`` (for example
    non-empty notes that are not a JSON object), the capture is refused with
    :data:`CONTRACT_REVISION_MAPPING_AMBIGUOUS` and its detail before anything
    is inserted or audited. The domain mapper is unchanged and still records
    the issues; persisting them as validated economics is what is refused.

    Idempotency: when the mapped content hash equals the contract's latest
    captured revision, the stored revision is returned unchanged
    (``already_captured``) - the original ``recorded_at_utc``/``recorded_by``
    are retained, no new number is allocated and no second audit row is
    written.

    Audit: an accepted capture appends its audit row through ``record_audit_event``
    in the caller's transaction, so the revision and its attribution commit or
    roll back together. A rejected mapping writes neither the revision nor an
    audit row; the caller inspects ``outcome``/``refusal_code``.

    Args:
        session: DB session; the caller owns the transaction boundary.
        contract_id: Stable upstream contract identity whose current row is
            captured.
        recorded_by: Authenticated principal the capture is attributed to.
        recorded_at_utc: Capture time; must be timezone-aware with a concrete
            UTC offset, and is stored as UTC.

    Returns:
        The capture result; see :class:`ContractRevisionCaptureResult`.

    Raises:
        ContractRevisionPersistenceError: When a capture field is blank or
            exceeds its column bound, when ``recorded_at_utc`` is naive or has
            no concrete UTC offset, or when the idempotent repeat's stored
            revision fails integrity verification.
    """

    identity = _capture_text(contract_id, "contract_id", 128)
    actor = _capture_text(recorded_by, "recorded_by", 64)
    recorded_at = _capture_instant(recorded_at_utc)

    # 契约行锁与强制刷新：PG 上 FOR UPDATE 串行化同一契约的并存捕获，保证编号
    # 不冲突；populate_existing 保证 identity map 中已加载的旧行被重新读取，
    # 不会把别的已提交事务写入前读取的旧值捕获成修订。SQLite 方言忽略
    # FOR UPDATE（仅用于测试夹具）。
    row = _locked_contract_row(session, identity)
    if row is None:
        return ContractRevisionCaptureResult(
            outcome=CONTRACT_REVISION_REJECTED,
            revision=None,
            refusal_code="contract_row_not_found",
            refusal_detail=f"no upstream contract row exists for {identity!r}",
        )

    try:
        mapped = map_legacy_contract_payload(_contract_payload(row))
    except ContractRevisionPayloadError as exc:
        # 不可映射的 legacy 行不得伪装成已验证经济内容：不写修订、不写审计。
        return ContractRevisionCaptureResult(
            outcome=CONTRACT_REVISION_REJECTED,
            revision=None,
            refusal_code=exc.code,
            refusal_detail=exc.detail,
        )

    snapshot = mapped.economic_snapshot
    if snapshot.mapping_issues:
        # 歧义映射不得被捕获为已验证经济内容：在插入/审计之前拒绝，不写任何行。
        return ContractRevisionCaptureResult(
            outcome=CONTRACT_REVISION_REJECTED,
            revision=None,
            refusal_code=CONTRACT_REVISION_MAPPING_AMBIGUOUS,
            refusal_detail=(
                f"legacy contract {identity!r} mapped with issues"
                f" [{', '.join(snapshot.mapping_issues)}]; an ambiguous mapping"
                " is never stored as validated economic evidence"
            ),
        )
    content_hash = snapshot.content_hash()
    latest = _latest_contract_revision(session, identity)
    if latest is not None and latest.content_hash == content_hash:
        _verified_contract_revision_snapshot(latest)
        return ContractRevisionCaptureResult(
            outcome=CONTRACT_REVISION_ALREADY_CAPTURED,
            revision=latest,
        )

    revision = UpstreamContractRevisionRecord(
        contract_revision_id=f"contract-revision-{uuid4().hex[:20]}",
        contract_id=identity,
        revision_number=1 if latest is None else latest.revision_number + 1,
        schema_version=snapshot.schema_version,
        capture_origin=CAPTURE_ORIGIN_LEGACY_CAPTURE,
        snapshot_json=snapshot.canonical_json(),
        display_metadata_json=_display_metadata_json(mapped.display_metadata),
        content_hash=content_hash,
        recorded_at_utc=recorded_at,
        recorded_by=actor,
    )
    session.add(revision)
    session.flush()
    _record_capture_audit(
        session,
        revision=revision,
        previous_revision=latest,
        recorded_by=actor,
        recorded_at_utc=recorded_at,
    )
    return ContractRevisionCaptureResult(
        outcome=CONTRACT_REVISION_CAPTURED,
        revision=revision,
    )


def upsert_upstream_contract_governed(
    session: Session,
    data: Mapping[str, object],
    *,
    recorded_by: str,
    recorded_at_utc: datetime,
    correlation_id: str | None = None,
) -> GovernedContractUpsertResult:
    """Insert or update one upstream contract under captured economic revisions.

    治理写入：覆盖前先捕获旧经济状态，覆盖后捕获新经济状态，审计与写入同一事务。

    This is the write path behind ``POST /api/route-cost/upstream-contracts``.
    It inserts or overwrites the mutable ``upstream_resource_contracts`` row
    exactly like :func:`upsert_upstream_contract`, but the economic terms a
    caller is about to replace are captured as an immutable revision first, and
    the new terms are captured afterwards, so both sides of the overwrite are
    evidence rather than a claim. The write itself grows no history: revisions
    exist only because this path (or an explicit capture) recorded the row
    states it observed.

    Ordering: the contract row is locked (``SELECT ... FOR UPDATE`` plus
    identity-map refresh) *before* the pre-capture and the edit, so the state
    captured as "previous" is the state this transaction is about to replace,
    never a stale read another committed writer has already superseded.

    Fail-closed pre-capture: when the stored row does not map to a validated
    economic snapshot (an unmappable value, or ambiguous notes recorded as
    mapping issues), the call returns a ``refused`` result carrying the stable
    ``refusal_code``/``refusal_detail`` and writes nothing at all. The stored
    malformed terms are preserved for a separate remediation step instead of
    being silently overwritten; the caller must roll the session back and
    report the refusal.

    Outcomes:

    * a new identity is inserted, then captured once - there is no previous
      state to capture;
    * a changed row is captured first (if its stored state was not already the
      latest revision) and captured again after the edit, which allocates the
      next revision number under the row lock;
    * a repeated request whose economics already equal the stored row adds no
      revision and preserves the original recorder and timestamp of that
      revision (the capture helper's idempotency);
    * a request that changes only display evidence (contract name, raw operator
      notes) adds no revision but is still audited, because otherwise the
      mutation would leave no trace at all;
    * a true replay leaves the source row unchanged and appends no mutation
      audit; an uncaptured legacy row still receives its first capture and
      capture audit. Already-captured replays write nothing.

    Concurrency: the row lock serializes updates per contract, so revision
    numbers cannot collide. Two concurrent creates of the same new identity
    cannot both insert: the insert is conflict-tolerant (``ON CONFLICT DO
    NOTHING``), so the loser's statement inserts nothing, the session stays
    usable and the same call continues as an overwrite of the winner's
    committed row instead of leaking a constraint exception.

    Audit: every outcome except ``unchanged``/``refused`` appends one
    ``route_cost.contract.upsert`` row (principal, correlation id, changed
    fields and the newest revision identity) through the caller's session, and
    every newly captured revision appends its own capture row. Both commit or
    roll back with the contract write.

    Args:
        session: DB session; the caller owns the transaction boundary.
        data: Contract fields in the upsert request shape.
        recorded_by: Authenticated principal the write and captures are
            attributed to; never a request-body value.
        recorded_at_utc: Time of the write; must be timezone-aware with a
            concrete UTC offset, and is stored as UTC.
        correlation_id: Optional request correlation id for the write audit.

    Returns:
        The write result; see :class:`GovernedContractUpsertResult`.

    Raises:
        ContractRevisionPersistenceError: When the contract id or actor is
            blank or exceeds its column bound, or when ``recorded_at_utc`` is
            naive or has no concrete UTC offset - raised before any write - or
            when the runtime dialect has no reviewed conflict-tolerant insert.
        KeyError/ValueError: When required contract fields are missing or
            malformed.
    """

    identity = _capture_text(data.get("contract_id"), "contract_id", 128)
    actor = _capture_text(recorded_by, "recorded_by", 64)
    recorded_at = _capture_instant(recorded_at_utc)
    values = _normalized_contract_values(data)

    row = _locked_contract_row(session, identity)
    created = False
    if row is None:
        created = _insert_contract_row_if_absent(session, identity, values, recorded_at)
        # Either this call inserted the row, or a concurrent create committed
        # the same identity first: both cases read the stored row under the
        # lock and continue, the second as an overwrite of the winner's row.
        row = _locked_contract_row(session, identity)
        if row is None:
            raise ContractRevisionPersistenceError(
                "contract_row_not_visible_after_insert",
                f"contract {identity!r} could not be read back after its insert",
            )

    if created:
        post = capture_upstream_contract_revision(
            session,
            identity,
            recorded_by=actor,
            recorded_at_utc=recorded_at,
        )
        if post.outcome == CONTRACT_REVISION_REJECTED:
            return GovernedContractUpsertResult(
                outcome=GOVERNED_CONTRACT_REFUSED,
                contract=None,
                latest_revision=None,
                previous_revision=None,
                captured_revision=None,
                refusal_code=post.refusal_code,
                refusal_detail=post.refusal_detail,
            )
        _record_governed_upsert_audit(
            session,
            contract_id=identity,
            principal=actor,
            outcome=GOVERNED_CONTRACT_CREATED,
            previous_revision=None,
            captured_revision=post.revision,
            changed_fields=(),
            recorded_at_utc=recorded_at,
            correlation_id=correlation_id,
        )
        return GovernedContractUpsertResult(
            outcome=GOVERNED_CONTRACT_CREATED,
            contract=_contract_payload(row),
            latest_revision=_revision_identity(post.revision),
            previous_revision=None,
            captured_revision=post.revision,
        )

    previous = capture_upstream_contract_revision(
        session,
        identity,
        recorded_by=actor,
        recorded_at_utc=recorded_at,
    )
    if previous.outcome == CONTRACT_REVISION_REJECTED:
        # 旧经济状态不可映射时绝不覆盖：本调用不写任何行，调用方回滚并报告
        # 稳定拒绝码，malformed 旧条款保留在原行中。
        return GovernedContractUpsertResult(
            outcome=GOVERNED_CONTRACT_REFUSED,
            contract=None,
            latest_revision=None,
            previous_revision=None,
            captured_revision=None,
            refusal_code=previous.refusal_code,
            refusal_detail=previous.refusal_detail,
        )

    changed_fields = tuple(
        field
        for field, value in values.items()
        if getattr(row, field) != value
    )
    if not changed_fields:
        # 真实重放：经济与展示证据均未变化，不写行、不写审计、保留原归属。
        return GovernedContractUpsertResult(
            outcome=GOVERNED_CONTRACT_UNCHANGED,
            contract=_contract_payload(row),
            latest_revision=_revision_identity(previous.revision),
            previous_revision=previous.revision,
            captured_revision=previous.revision,
        )

    _apply_contract_values(row, values)
    row.updated_at_utc = recorded_at
    session.flush()
    post = capture_upstream_contract_revision(
        session,
        identity,
        recorded_by=actor,
        recorded_at_utc=recorded_at,
    )
    if post.outcome == CONTRACT_REVISION_REJECTED:
        return GovernedContractUpsertResult(
            outcome=GOVERNED_CONTRACT_REFUSED,
            contract=None,
            latest_revision=None,
            previous_revision=previous.revision,
            captured_revision=None,
            refusal_code=post.refusal_code,
            refusal_detail=post.refusal_detail,
        )
    # 分类以捕获结果为准：只有真的写入了新修订才是经济变更；捕获幂等说明
    # 变化只落在未参与哈希的展示证据上。
    outcome = (
        GOVERNED_CONTRACT_ECONOMICS_UPDATED
        if post.created
        else GOVERNED_CONTRACT_METADATA_UPDATED
    )
    _record_governed_upsert_audit(
        session,
        contract_id=identity,
        principal=actor,
        outcome=outcome,
        previous_revision=previous.revision,
        captured_revision=post.revision,
        changed_fields=changed_fields,
        recorded_at_utc=recorded_at,
        correlation_id=correlation_id,
    )
    return GovernedContractUpsertResult(
        outcome=outcome,
        contract=_contract_payload(row),
        latest_revision=_revision_identity(post.revision),
        previous_revision=previous.revision,
        captured_revision=post.revision,
    )


def list_upstream_contract_revisions(
    session: Session,
    contract_id: str,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """List one contract's captured revisions, oldest number first, verified.

    Every returned row is verified before it is served (schema, content hash
    and matching contract id), so a tampered snapshot is reported rather than
    served as evidence. ``limit``/``offset`` are pushed into the query, so a
    contract with a long capture record materializes at most one bounded page
    of snapshot evidence instead of its whole history.

    Args:
        session: DB session.
        contract_id: Contract id filter.
        limit: Maximum revisions to return, or ``None`` for the previous
            unbounded repository behaviour. The read route always passes a
            bounded page size.
        offset: Revisions to skip, in revision-number order.

    Returns:
        Verified revision payload dicts ordered by ``revision_number``
        ascending, with ``contract_revision_id`` as the deterministic
        tie-break.

    Raises:
        ValueError: When ``limit`` is not positive or ``offset`` is negative.
        ContractRevisionPersistenceError: When a stored row fails verification.
    """

    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive number of revisions")
    if offset < 0:
        raise ValueError("offset must not be negative")
    query = (
        session.query(UpstreamContractRevisionRecord)
        .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
        .order_by(
            UpstreamContractRevisionRecord.revision_number,
            UpstreamContractRevisionRecord.contract_revision_id,
        )
    )
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return [_verified_contract_revision_payload(row) for row in query.all()]


def count_upstream_contract_revisions(session: Session, contract_id: str) -> int:
    """Count one contract's captured revisions without materializing snapshots.

    Args:
        session: DB session.
        contract_id: Contract id filter.

    Returns:
        Number of stored revisions for the contract.
    """

    return int(
        session.query(func.count())
        .select_from(UpstreamContractRevisionRecord)
        .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
        .scalar()
        or 0
    )


def get_upstream_contract_revision(
    session: Session,
    contract_revision_id: str,
    *,
    contract_id: str | None = None,
) -> dict:
    """Read one captured revision with immutable-evidence verification.

    When ``contract_id`` is supplied the read is explicitly scoped to it: a
    revision id that belongs to a different contract is refused with the same
    ``contract_revision_not_found`` code as an unknown id, so the surface never
    confirms that a revision exists under a contract the caller did not name.

    Args:
        session: DB session.
        contract_revision_id: Revision id to read.
        contract_id: Contract id the revision must belong to, or ``None`` for
            the unscoped repository read.

    Returns:
        The verified revision payload: revision identity, capture origin,
        original recorder, display evidence and the canonical economic
        snapshot.

    Raises:
        ContractRevisionPersistenceError: When no revision has that id or the
            stored row fails verification or is not scoped to ``contract_id``.
    """

    row = session.get(UpstreamContractRevisionRecord, contract_revision_id)
    if row is None or (contract_id is not None and row.contract_id != contract_id):
        raise ContractRevisionPersistenceError(
            "contract_revision_not_found",
            f"no captured contract revision {contract_revision_id!r} exists"
            + (f" for contract {contract_id!r}" if contract_id is not None else ""),
        )
    return _verified_contract_revision_payload(row)


def latest_market_marks(session: Session) -> list[LiveMarketMark]:
    """List latest market marks as domain LiveMarketMark rows.

    Args:
        session: DB session.

    Returns:
        List of LiveMarketMark domain rows, newest mark time first.
    """

    rows = session.query(LiveMarketMarkRecord).order_by(
        LiveMarketMarkRecord.mark_time_utc.desc()
    )
    return [_mark_from_record(row) for row in rows.all()]


def list_route_candidates(session: Session) -> list[dict]:
    """List active route candidates.

    Args:
        session: DB session.

    Returns:
        List of route candidate payload dicts.
    """

    rows = session.query(RouteCandidateRecord).filter(
        RouteCandidateRecord.active.is_(True)
    ).order_by(RouteCandidateRecord.route_name)
    return [_route_candidate_payload(row) for row in rows.all()]


def list_capacity_profiles(session: Session, contract_id: str) -> list[dict]:
    """List capacity profiles of one contract.

    Args:
        session: DB session.
        contract_id: Contract id filter.

    Returns:
        List of capacity profile payload dicts.
    """

    rows = session.query(CapacityProfileRecord).filter(
        CapacityProfileRecord.contract_id == contract_id
    )
    return [
        {
            "capacity_profile_id": row.capacity_profile_id,
            "contract_id": row.contract_id,
            "point_name": row.point_name,
            "direction": row.direction,
            "capacity_mwh_per_day": row.capacity_mwh_per_day,
            "firmness": row.firmness,
            "valid_from_utc": row.valid_from_utc.isoformat(),
            "valid_to_utc": row.valid_to_utc.isoformat(),
            "source_reference": row.source_reference,
        }
        for row in rows.all()
    ]


def _tariff_from_record(row: TsoTariffRecord) -> CapacityTariff:
    return CapacityTariff(
        tariff_id=row.tariff_id,
        document_id=row.document_id,
        country=row.country,
        tso=row.tso,
        market_area=row.market_area,
        gas_year=row.gas_year,
        point_id=row.point_id,
        source_point_name=row.source_point_name,
        direction=TariffDirection(row.direction),
        capacity_product=CapacityProduct(row.capacity_product),
        firmness=Firmness(row.firmness),
        tariff_value=row.tariff_value,
        currency=row.currency,
        unit=row.unit,
        effective_from=row.effective_from.date(),
        effective_to=row.effective_to.date() if row.effective_to else None,
        tariff_status=TariffStatus(row.tariff_status),
        source_table=row.source_table,
        source_page=row.source_page,
        source_refs=row.source_refs,
        manual_review_required=row.manual_review_required,
    )


def _mark_from_record(row: LiveMarketMarkRecord) -> LiveMarketMark:
    return LiveMarketMark(
        venue=row.venue,
        hub=row.hub,
        product=row.product,
        bid_gbp_mwh=row.bid_gbp_mwh,
        ask_gbp_mwh=row.ask_gbp_mwh,
        last_gbp_mwh=row.last_gbp_mwh,
        mark_time_utc=row.mark_time_utc.isoformat(),
        source_system=row.source_system,
    )


def _contract_payload(row: UpstreamResourceContractRecord) -> dict:
    notes = _contract_notes(row.notes)
    return {
        "contract_id": row.contract_id,
        "contract_name": row.contract_name,
        "resource_type": row.resource_type,
        "delivery_point_name": row.delivery_point_name,
        "gas_year": row.gas_year,
        "delivery_quantity_mwh_per_day": row.delivery_quantity_mwh_per_day,
        "contract_price_gbp_mwh": row.contract_price_gbp_mwh,
        "settlement_frequency": row.settlement_frequency,
        "upstream_payment_lag_days": row.upstream_payment_lag_days,
        "screen_sale_cash_lag_days": row.screen_sale_cash_lag_days,
        "delivery_tolerance_pct": row.delivery_tolerance_pct,
        "nomination_tolerance_pct": row.nomination_tolerance_pct,
        "tolerance_risk_allowance_gbp_mwh": row.tolerance_risk_allowance_gbp_mwh,
        "annual_financing_rate_pct": row.annual_financing_rate_pct,
        "owned_entry_capacity_mwh_per_day": row.owned_entry_capacity_mwh_per_day,
        "owned_exit_capacity_mwh_per_day": row.owned_exit_capacity_mwh_per_day,
        "allowed_exit_points": row.allowed_exit_points,
        "eligible_sale_modes": row.eligible_sale_modes,
        "notes": row.notes,
        **{
            field: notes[field]
            for field in _STRUCTURED_NOTE_FIELDS
            if field in notes
        },
        "updated_at_utc": row.updated_at_utc.isoformat(),
    }


_STRUCTURED_NOTE_FIELDS = (
    "variable_cost_gbp_mwh",
    "regas_fee_gbp_mwh",
    "fuel_loss_allowance_pct",
)


def _contract_notes(value: object) -> dict:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merged_contract_notes(data: Mapping[str, object]) -> str | None:
    raw_notes = _optional_string(data.get("notes"))
    notes = _contract_notes(raw_notes)
    if raw_notes and not notes:
        notes["operator_notes"] = raw_notes
    for field in _STRUCTURED_NOTE_FIELDS:
        if field in data and data[field] is not None:
            notes[field] = data[field]
    return json.dumps(notes, sort_keys=True) if notes else None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _route_candidate_payload(row: RouteCandidateRecord) -> dict:
    return {
        "route_id": row.route_id,
        "route_name": row.route_name,
        "start_point_name": row.start_point_name,
        "target_point_name": row.target_point_name,
        "business_model": row.business_model,
        "route_legs": row.route_legs,
        "required_entry_point_name": row.required_entry_point_name,
        "required_exit_point_name": row.required_exit_point_name,
        "required_tso_access": row.required_tso_access,
        "source_systems": row.source_systems,
    }


def _capture_text(value: object, name: str, max_length: int) -> str:
    """Return one required capture field within its column bound.

    Raises:
        ContractRevisionPersistenceError: When the value is blank or longer
            than the column it will be stored in (truncation would silently
            rewrite the recorded actor or identity).
    """

    text = "" if value is None else str(value).strip()
    if not text:
        raise ContractRevisionPersistenceError(
            f"{name}_blank", f"{name} is required and must not be blank"
        )
    if len(text) > max_length:
        raise ContractRevisionPersistenceError(
            f"{name}_too_long", f"{name} exceeds {max_length} characters"
        )
    return text


def _capture_instant(value: object) -> datetime:
    """Return one capture instant as UTC.

    Raises:
        ContractRevisionPersistenceError: When the value is not a date-time,
            is naive, or carries no concrete UTC offset (an aware ``tzinfo``
            whose ``utcoffset`` is ``None`` is not an instant).
    """

    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ContractRevisionPersistenceError(
            "recorded_at_not_utc",
            "recorded_at_utc must be a timezone-aware datetime with a concrete"
            " UTC offset",
        )
    return value.astimezone(UTC)


def _locked_contract_row(
    session: Session, contract_id: str
) -> UpstreamResourceContractRecord | None:
    """Read one contract row under ``FOR UPDATE`` with an identity-map refresh.

    PostgreSQL serializes concurrent captures and governed writes per contract,
    and ``populate_existing`` re-reads a row already loaded in the session, so
    a stale in-memory instance another committed writer has replaced is never
    captured or overwritten. SQLite fixtures ignore the lock clause.
    """

    return (
        session.query(UpstreamResourceContractRecord)
        .filter(UpstreamResourceContractRecord.contract_id == contract_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def _revision_identity(
    revision: UpstreamContractRevisionRecord | None,
) -> dict | None:
    """Additive revision-identity metadata for a write response.

    Plain values only, so the caller can build its response before committing:
    this names the newest captured revision (identity, number, hash, recorder)
    and is never a substitute for reading the verified snapshot payload.
    """

    if revision is None:
        return None
    return {
        "contract_revision_id": revision.contract_revision_id,
        "contract_id": revision.contract_id,
        "revision_number": revision.revision_number,
        "capture_origin": revision.capture_origin,
        "content_hash": revision.content_hash,
        "recorded_at_utc": revision.recorded_at_utc.isoformat(),
        "recorded_by": revision.recorded_by,
    }


def _record_governed_upsert_audit(
    session: Session,
    *,
    contract_id: str,
    principal: str,
    outcome: str,
    previous_revision: UpstreamContractRevisionRecord | None,
    captured_revision: UpstreamContractRevisionRecord | None,
    changed_fields: tuple[str, ...],
    recorded_at_utc: datetime,
    correlation_id: str | None,
) -> None:
    """Append the governed-write audit row into the caller's transaction.

    The capture audit names a revision; this row names the request: which
    principal ran the governed upsert, under which correlation id, which stored
    fields changed and which revision is newest afterwards. It carries field
    *names*, never contract values. A failure to write it must fail the write:
    the caller rolls back, so a stored mutation always has its audit row.
    """

    record_audit_event(
        session,
        event_type="governance.contracts",
        principal=principal,
        action="route_cost.contract.upsert",
        resource=f"upstream_contract:{contract_id}"[:128],
        outcome=outcome,
        severity="info",
        detail=(
            f"outcome={outcome}; changed_fields={','.join(changed_fields) or 'none'};"
            f" latest_revision_id="
            f"{captured_revision.contract_revision_id if captured_revision else 'none'};"
            f" latest_revision_number="
            f"{captured_revision.revision_number if captured_revision else 'none'};"
            f" latest_content_hash="
            f"{captured_revision.content_hash if captured_revision else 'none'}"
        ),
        source_system="route-cost",
        now_utc=recorded_at_utc,
        correlation_id=correlation_id[:64] if correlation_id else None,
        before_summary=(
            {
                "latest_revision_number": previous_revision.revision_number,
                "latest_content_hash": previous_revision.content_hash,
            }
            if previous_revision is not None
            else None
        ),
        after_summary=(
            {
                "latest_revision_id": captured_revision.contract_revision_id,
                "latest_revision_number": captured_revision.revision_number,
                "latest_content_hash": captured_revision.content_hash,
                "changed_fields": list(changed_fields),
            }
            if captured_revision is not None
            else None
        ),
    )


def _latest_contract_revision(
    session: Session, contract_id: str
) -> UpstreamContractRevisionRecord | None:
    """Return the highest-numbered captured revision of one contract, if any."""

    return (
        session.query(UpstreamContractRevisionRecord)
        .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
        .order_by(UpstreamContractRevisionRecord.revision_number.desc())
        .first()
    )


def _display_metadata_json(display: ContractDisplayMetadata) -> str:
    """Serialize display evidence exactly as captured; never part of the hash."""

    return json.dumps(
        {
            "contract_name": display.contract_name,
            "operator_notes": display.operator_notes,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _record_capture_audit(
    session: Session,
    *,
    revision: UpstreamContractRevisionRecord,
    previous_revision: UpstreamContractRevisionRecord | None,
    recorded_by: str,
    recorded_at_utc: datetime,
) -> None:
    """Append the capture audit row into the caller's transaction.

    A failure to write it must fail the capture: the caller propagates, the
    session rolls back, and no revision persists without attribution.
    """

    record_audit_event(
        session,
        event_type="governance.contracts",
        principal=recorded_by,
        action="route_cost.contract.capture_revision",
        resource=f"upstream_contract:{revision.contract_id}"[:128],
        outcome="captured",
        severity="info",
        detail=(
            f"contract_revision_id={revision.contract_revision_id};"
            f" revision_number={revision.revision_number};"
            f" capture_origin={revision.capture_origin};"
            f" content_hash={revision.content_hash}"
        ),
        source_system="route-cost",
        now_utc=recorded_at_utc,
        before_summary=(
            {
                "latest_revision_number": previous_revision.revision_number,
                "latest_content_hash": previous_revision.content_hash,
            }
            if previous_revision is not None
            else None
        ),
        after_summary={
            "contract_revision_id": revision.contract_revision_id,
            "revision_number": revision.revision_number,
            "content_hash": revision.content_hash,
            "capture_origin": revision.capture_origin,
        },
    )


def _snapshot_hash(snapshot_json: str) -> str:
    """Return ``sha256:<hex>`` over the stored canonical snapshot text."""

    digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _verified_contract_revision_snapshot(
    row: UpstreamContractRevisionRecord,
) -> UpstreamContractEconomicSnapshot:
    """Decode and verify one stored revision's immutable economic evidence.

    Verification is: reviewed capture origin, hash over the stored canonical
    text, strict canonical/schema decode, matching contract id and schema
    version, and a canonical round-trip hash. It is an integrity check on
    stored evidence, never a signature.

    Raises:
        ContractRevisionPersistenceError: When the stored row fails any check.
    """

    if row.capture_origin not in _VERIFIED_CAPTURE_ORIGINS:
        raise ContractRevisionPersistenceError(
            "contract_revision_origin_unknown",
            f"capture_origin {row.capture_origin!r} is not a reviewed origin",
        )
    stored_json = row.snapshot_json
    if not isinstance(stored_json, str) or not stored_json:
        raise ContractRevisionPersistenceError(
            "contract_revision_snapshot_missing",
            f"{row.contract_revision_id} has no stored snapshot JSON",
        )
    if _snapshot_hash(stored_json) != row.content_hash:
        raise ContractRevisionPersistenceError(
            "contract_revision_hash_mismatch",
            f"{row.contract_revision_id} stored snapshot does not match its content hash",
        )
    try:
        document = json.loads(stored_json)
    except ValueError as exc:
        raise ContractRevisionPersistenceError(
            "contract_revision_snapshot_not_json",
            f"{row.contract_revision_id} stored snapshot is not JSON",
        ) from exc
    try:
        snapshot = UpstreamContractEconomicSnapshot.from_canonical_document(document)
    except ContractRevisionPayloadError as exc:
        raise ContractRevisionPersistenceError(
            "contract_revision_snapshot_invalid",
            f"{row.contract_revision_id} snapshot refused: {exc.code} ({exc.detail})",
        ) from exc
    if snapshot.contract_id != row.contract_id:
        raise ContractRevisionPersistenceError(
            "contract_revision_contract_id_mismatch",
            f"{row.contract_revision_id} snapshot is for {snapshot.contract_id!r},"
            f" not {row.contract_id!r}",
        )
    if snapshot.schema_version != row.schema_version:
        raise ContractRevisionPersistenceError(
            "contract_revision_schema_version_mismatch",
            f"{row.contract_revision_id} snapshot schema {snapshot.schema_version!r}"
            f" does not match stored {row.schema_version!r}",
        )
    if snapshot.content_hash() != row.content_hash:
        raise ContractRevisionPersistenceError(
            "contract_revision_hash_mismatch",
            f"{row.contract_revision_id} snapshot does not round-trip to its content hash",
        )
    return snapshot


def _verified_display_metadata(row: UpstreamContractRevisionRecord) -> dict:
    """Decode the unhashed display evidence with shape checks only.

    Display metadata is deliberately outside the economic hash (a rename must
    not create a revision), so this is a shape check, not an integrity proof.
    """

    try:
        display = json.loads(row.display_metadata_json)
    except (TypeError, ValueError) as exc:
        raise ContractRevisionPersistenceError(
            "contract_revision_display_invalid",
            f"{row.contract_revision_id} display evidence is not JSON",
        ) from exc
    if not isinstance(display, Mapping):
        raise ContractRevisionPersistenceError(
            "contract_revision_display_invalid",
            f"{row.contract_revision_id} display evidence is not a JSON object",
        )
    contract_name = display.get("contract_name")
    operator_notes = display.get("operator_notes")
    if not isinstance(contract_name, str) or not contract_name.strip():
        raise ContractRevisionPersistenceError(
            "contract_revision_display_invalid",
            f"{row.contract_revision_id} display evidence has no contract_name",
        )
    if operator_notes is not None and not isinstance(operator_notes, str):
        raise ContractRevisionPersistenceError(
            "contract_revision_display_invalid",
            f"{row.contract_revision_id} display evidence has a non-text operator_notes",
        )
    return {"contract_name": contract_name, "operator_notes": operator_notes}


def _verified_contract_revision_payload(row: UpstreamContractRevisionRecord) -> dict:
    """Serialize one verified stored revision for a caller citing evidence."""

    snapshot = _verified_contract_revision_snapshot(row)
    return {
        "contract_revision_id": row.contract_revision_id,
        "contract_id": row.contract_id,
        "revision_number": row.revision_number,
        "schema_version": row.schema_version,
        "capture_origin": row.capture_origin,
        "content_hash": row.content_hash,
        "recorded_at_utc": row.recorded_at_utc.isoformat(),
        "recorded_by": row.recorded_by,
        "display_metadata": _verified_display_metadata(row),
        "snapshot": snapshot.canonical_document(),
    }
