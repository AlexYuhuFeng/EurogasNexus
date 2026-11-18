"""The valuation snapshot: every input an evaluation read, recorded so it can be replayed.

Commercial product design basis 2, section J.1(3): every evaluator reads prices, FX, rates,
tariffs, capacity, outages, assumptions and the book through one reader, so two screens
never value a month differently and a case's evidence can be replayed.

A reader is asked for one input at a time by a stable key (``price:TTF:2027-01:mid``,
``tariff:ITP-00063:EXIT:FIRM_MONTH:2026/27``). The first answer for a key is recorded with
its class, source, reference and as-of; later reads of the same key return the recorded
answer, so one evaluation can never see two values for one input. A key that has no data
is recorded too, as ``missing``, so a replay reproduces the refusal as well as the figures.

:class:`RecordingReader` is the shared machinery. The live reader over the runtime store
subclasses it (``application/valuation_snapshot.py``); :class:`ReplayReader` answers only
from a stored manifest and reports any key the original evaluation did not read.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass, weakest


class InputKind(StrEnum):
    """What kind of input a snapshot row is."""

    PRICE = "price"
    FX = "fx"
    RATE = "rate"
    TARIFF = "tariff"
    CAPACITY = "capacity"
    OUTAGE = "outage"
    ASSUMPTION = "assumption"
    BOOK = "book"


#: FX conversion method labels. ``spot`` is the adapter used until forward FX by interest
#: parity is available; a forward delivery period converted at spot is labelled so.
FX_METHOD_SPOT = "spot"
FX_METHOD_FORWARD = "forward"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class SnapshotInput:
    """One input as an evaluation saw it."""

    key: str
    kind: InputKind
    input_class: InputClass
    value: Decimal | None = None
    unit: str = ""
    currency: str | None = None
    as_of_utc: datetime | None = None
    #: Entitlement family of the source (``ECB``, ``ENTSOG``, a licensed vendor, ``FIRM``).
    source_family: str | None = None
    #: The stored row or document the value came from.
    source_ref: str = ""
    label: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def held(self) -> bool:
        """Whether the input has a value (it is not ``missing``)."""

        return self.input_class is not InputClass.MISSING

    def to_json(self) -> dict[str, Any]:
        """Canonical JSON form (Decimals as strings, instants as ISO text)."""

        return {
            "key": self.key,
            "kind": self.kind.value,
            "input_class": self.input_class.value,
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
            "currency": self.currency,
            "as_of_utc": None if self.as_of_utc is None else self.as_of_utc.isoformat(),
            "source_family": self.source_family,
            "source_ref": self.source_ref,
            "label": self.label,
            "detail": _jsonable(dict(self.detail)),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SnapshotInput:
        """Rebuild an input from :meth:`to_json` output."""

        raw_as_of = data.get("as_of_utc")
        return cls(
            key=str(data["key"]),
            kind=InputKind(data["kind"]),
            input_class=InputClass(data["input_class"]),
            value=None if data.get("value") is None else Decimal(str(data["value"])),
            unit=str(data.get("unit") or ""),
            currency=data.get("currency"),
            as_of_utc=None if raw_as_of is None else datetime.fromisoformat(str(raw_as_of)),
            source_family=data.get("source_family"),
            source_ref=str(data.get("source_ref") or ""),
            label=str(data.get("label") or ""),
            detail=dict(data.get("detail") or {}),
        )


def missing(key: str, kind: InputKind, label: str, **detail: Any) -> SnapshotInput:
    """A recorded refusal: the input is not held."""

    return SnapshotInput(
        key=key, kind=kind, input_class=InputClass.MISSING, label=label, detail=detail
    )


# ----------------------------------------------------------------------------- input keys


def price_key(hub: str, period: DeliveryPeriod, side: str = "mid") -> str:
    """``price:<hub>:<period>:<bid|ask|mid>``."""

    return f"price:{hub.upper()}:{period.label}:{side}"


def fx_key(base: str, quote: str, value_date: str) -> str:
    """``fx:<base><quote>:<value date>``."""

    return f"fx:{base.upper()}{quote.upper()}:{value_date}"


def rate_key(currency: str) -> str:
    """``rate:<currency>`` (the currency's overnight benchmark)."""

    return f"rate:{currency.upper()}"


def gas_year_of(period: DeliveryPeriod) -> str:
    """The gas year (October to September) a period starts in, as ``2026/27``."""

    year = period.start.year if period.start.month >= 10 else period.start.year - 1
    return f"{year}/{(year + 1) % 100:02d}"


def tariff_key(point_id: str, direction: str, product: str, period: DeliveryPeriod) -> str:
    """``tariff:<point>:<ENTRY|EXIT>:<capacity product>:<gas year>``."""

    return f"tariff:{point_id}:{direction.upper()}:{product.upper()}:{gas_year_of(period)}"


def capacity_key(point_id: str, direction: str, period: DeliveryPeriod) -> str:
    """``capacity:<point>:<direction>:<period>``."""

    return f"capacity:{point_id}:{direction.upper()}:{period.label}"


def outages_key(zone: str, period: DeliveryPeriod) -> str:
    """``outages:<balancing zone>:<period>`` (a collection)."""

    return f"outages:{zone.upper()}:{period.label}"


def assumption_key(key: str) -> str:
    """``assumption:<catalogue key>``."""

    return f"assumption:{key}"


HEDGE_COVER_KEY = "book:hedge-cover"

#: The named collections an evaluator may read through :meth:`SnapshotReader.collection`:
#: ``positions`` (net MWh per book, hub and month), ``contracts`` (active supply contracts),
#: ``mandates`` (trader mandates), ``held_capacity`` (capacity the firm holds on a route),
#: ``residuals`` (tomorrow's balance per hub), ``outage_feed`` (whether a REMIT feed is held),
#: ``storage`` (storage the firm holds), ``resource_pool`` (the composed pool: resources and
#: sale options, as the resource-pool optimiser takes them).
COLLECTIONS = frozenset(
    {
        "positions",
        "contracts",
        "mandates",
        "held_capacity",
        "residuals",
        "outage_feed",
        "storage",
        "resource_pool",
    }
)


def collection_key(name: str) -> str:
    """``collection:<name>``."""

    return f"collection:{name}"


def dependency_key(item: SnapshotInput) -> str | None:
    """The invalidation key an opportunity stores for one input (design J.2).

    ``hub:TTF:2027-01``, ``tariff:ITP-00063:EXIT:FIRM_MONTH:2026/27``, ``outage:<message>``,
    ``contract:<id>``, ``assumption:<key>``, ``fx:EURGBP``, ``rate:GBP``. An event carrying
    one of these keys re-evaluates only the opportunities that stored it.
    """

    parts = item.key.split(":")
    if item.kind is InputKind.PRICE and len(parts) >= 3:
        return f"hub:{parts[1]}:{parts[2]}"
    if item.kind is InputKind.FX and len(parts) >= 2:
        return f"fx:{parts[1]}"
    if item.kind is InputKind.BOOK:
        contract = item.detail.get("contract_id")
        return f"contract:{contract}" if contract else None
    if item.kind is InputKind.OUTAGE:
        message = item.detail.get("message_id")
        return f"outage:{message}" if message else None
    return item.key


# ----------------------------------------------------------------------------- readers


class SnapshotReader(Protocol):
    """What an evaluator may read. Nothing else reaches an evaluator."""

    as_of_utc: datetime
    demo_desk: bool
    fx_method: str

    def price(self, hub: str, period: DeliveryPeriod, side: str = "mid") -> SnapshotInput:
        """A price for a hub and delivery period, in the hub's currency per MWh."""

    def fx(self, base: str, quote: str, period: DeliveryPeriod) -> SnapshotInput:
        """Units of ``quote`` per one ``base`` for cash flows of ``period``."""

    def rate(self, currency: str) -> SnapshotInput:
        """The currency's latest overnight benchmark fixing, percent per year."""

    def tariff(
        self, point_id: str, direction: str, product: str, period: DeliveryPeriod
    ) -> SnapshotInput:
        """A published capacity tariff in force for the period."""

    def capacity(self, point_id: str, direction: str, period: DeliveryPeriod) -> SnapshotInput:
        """Firm technical capacity offered at a point for the period."""

    def outages(self, zone: str, period: DeliveryPeriod) -> tuple[SnapshotInput, ...]:
        """Unavailability events in a balancing zone overlapping the period."""

    def assumption(self, key: str) -> SnapshotInput:
        """A value of the firm's approved assumption set in force."""

    def hedge_cover(self) -> tuple[SnapshotInput, ...]:
        """Approved hedge bands and the cover held, per contract and month."""

    def collection(self, name: str) -> tuple[SnapshotInput, ...]:
        """A named set of book or feed rows (:data:`COLLECTIONS`), one input per row."""

    def inputs(self) -> tuple[SnapshotInput, ...]:
        """Every input read so far, in reading order."""


class RecordingReader:
    """Shared recording and caching; subclasses supply the ``_load_*`` methods."""

    def __init__(
        self,
        *,
        as_of_utc: datetime,
        demo_desk: bool = False,
        fx_method: str = FX_METHOD_SPOT,
        assumption_version: str | None = None,
    ) -> None:
        self.as_of_utc = as_of_utc
        self.demo_desk = demo_desk
        self.fx_method = fx_method
        self.assumption_version = assumption_version
        self._recorded: dict[str, SnapshotInput] = {}

    # ---- recording
    def _record(self, item: SnapshotInput) -> SnapshotInput:
        self._recorded.setdefault(item.key, item)
        return self._recorded[item.key]

    def _get(self, key: str, loader: Callable[[], SnapshotInput]) -> SnapshotInput:
        held = self._recorded.get(key)
        if held is not None:
            return held
        item = loader()
        if item.key != key:
            raise ValueError(f"loader answered {item.key!r} for {key!r}")
        return self._record(item)

    def _get_collection(
        self, key: str, kind: InputKind, loader: Callable[[], Iterable[SnapshotInput]]
    ) -> tuple[SnapshotInput, ...]:
        held = self._recorded.get(key)
        if held is None:
            members = [self._record(item) for item in loader()]
            held = self._record(
                SnapshotInput(
                    key=key,
                    kind=kind,
                    input_class=weakest(item.input_class for item in members)
                    if members
                    else InputClass.SOURCED,
                    label=f"{len(members)} item(s)",
                    detail={"members": [item.key for item in members]},
                )
            )
        return tuple(self._recorded[member] for member in held.detail.get("members", ()))

    # ---- the reader protocol
    def price(self, hub: str, period: DeliveryPeriod, side: str = "mid") -> SnapshotInput:
        key = price_key(hub, period, side)
        return self._get(key, lambda: self._load_price(key, hub.upper(), period, side))

    def fx(self, base: str, quote: str, period: DeliveryPeriod) -> SnapshotInput:
        key = fx_key(base, quote, period.label)
        return self._get(key, lambda: self._load_fx(key, base.upper(), quote.upper(), period))

    def rate(self, currency: str) -> SnapshotInput:
        key = rate_key(currency)
        return self._get(key, lambda: self._load_rate(key, currency.upper()))

    def tariff(
        self, point_id: str, direction: str, product: str, period: DeliveryPeriod
    ) -> SnapshotInput:
        key = tariff_key(point_id, direction, product, period)
        return self._get(
            key, lambda: self._load_tariff(key, point_id, direction.upper(), product, period)
        )

    def capacity(self, point_id: str, direction: str, period: DeliveryPeriod) -> SnapshotInput:
        key = capacity_key(point_id, direction, period)
        return self._get(key, lambda: self._load_capacity(key, point_id, direction.upper(), period))

    def outages(self, zone: str, period: DeliveryPeriod) -> tuple[SnapshotInput, ...]:
        key = outages_key(zone, period)
        return self._get_collection(
            key, InputKind.OUTAGE, lambda: self._load_outages(zone.upper(), period)
        )

    def assumption(self, key: str) -> SnapshotInput:
        full = assumption_key(key)
        return self._get(full, lambda: self._load_assumption(full, key))

    def hedge_cover(self) -> tuple[SnapshotInput, ...]:
        return self._get_collection(HEDGE_COVER_KEY, InputKind.BOOK, self._load_hedge_cover)

    def collection(self, name: str) -> tuple[SnapshotInput, ...]:
        if name not in COLLECTIONS:
            raise ValueError(f"unknown collection {name!r}")
        return self._get_collection(
            collection_key(name), InputKind.BOOK, lambda: self._load_collection(name)
        )

    def inputs(self) -> tuple[SnapshotInput, ...]:
        return tuple(self._recorded.values())

    # ---- loaders (a reader with no store holds nothing)
    def _load_price(self, key, hub, period, side) -> SnapshotInput:
        return missing(key, InputKind.PRICE, f"{hub} {period.label} {side}")

    def _load_fx(self, key, base, quote, period) -> SnapshotInput:
        return missing(key, InputKind.FX, f"{base}/{quote}")

    def _load_rate(self, key, currency) -> SnapshotInput:
        return missing(key, InputKind.RATE, f"{currency} overnight rate")

    def _load_tariff(self, key, point_id, direction, product, period) -> SnapshotInput:
        return missing(
            key,
            InputKind.TARIFF,
            f"{point_id} {direction} {product}",
            reason="tariff not held",
            point_id=point_id,
        )
        return missing(key, InputKind.TARIFF, f"{point_id} {direction} {product}")

    def _load_capacity(self, key, point_id, direction, period) -> SnapshotInput:
        return missing(key, InputKind.CAPACITY, f"{point_id} {direction}")

    def _load_outages(self, zone, period) -> list[SnapshotInput]:
        return []

    def _load_assumption(self, key, catalogue_key) -> SnapshotInput:
        return missing(key, InputKind.ASSUMPTION, catalogue_key)

    def _load_hedge_cover(self) -> list[SnapshotInput]:
        return []

    def _load_collection(self, name: str) -> list[SnapshotInput]:
        return []

    # ---- freezing
    def manifest(self, snapshot_id: str) -> SnapshotManifest:
        """The record of everything read, ready to persist."""

        return SnapshotManifest(
            snapshot_id=snapshot_id,
            as_of_utc=self.as_of_utc,
            demo_desk=self.demo_desk,
            fx_method=self.fx_method,
            assumption_version=self.assumption_version,
            inputs=self.inputs(),
        )


@dataclass(frozen=True)
class SnapshotManifest:
    """What one evaluation read: the evidence a case points at and a replay serves."""

    snapshot_id: str
    as_of_utc: datetime
    demo_desk: bool
    fx_method: str
    assumption_version: str | None
    inputs: tuple[SnapshotInput, ...]

    @property
    def quality(self) -> InputClass:
        """Weakest class over every held input (missing inputs are refusals, not values)."""

        held = [item.input_class for item in self.inputs if item.held]
        return weakest(held) if held else InputClass.MISSING

    @property
    def simulated(self) -> bool:
        """Whether any input read was simulated."""

        return any(item.input_class is InputClass.SIMULATED for item in self.inputs)

    def digest(self) -> str:
        """SHA-256 of the canonical inputs: two snapshots with one digest read the same."""

        payload = json.dumps(
            {
                "as_of_utc": self.as_of_utc.isoformat(),
                "demo_desk": self.demo_desk,
                "fx_method": self.fx_method,
                "assumption_version": self.assumption_version,
                "inputs": [item.to_json() for item in self.inputs],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        """The version line of each input set (design J.3 ``valuation_snapshot``)."""

        def latest(kind: InputKind) -> str | None:
            moments = [
                item.as_of_utc for item in self.inputs if item.kind is kind and item.as_of_utc
            ]
            return max(moments).isoformat() if moments else None

        tariff_documents = sorted(
            {
                str(item.detail.get("document_id"))
                for item in self.inputs
                if item.kind is InputKind.TARIFF and item.detail.get("document_id")
            }
        )
        return {
            "curve_as_of_utc": latest(InputKind.PRICE),
            "fx_as_of_utc": latest(InputKind.FX),
            "rates_as_of_utc": latest(InputKind.RATE),
            "tariff_documents": tariff_documents,
            "assumption_version": self.assumption_version,
            "book_as_of_utc": latest(InputKind.BOOK),
            "fx_method": self.fx_method,
        }


class ReplayReader(RecordingReader):
    """Answers only from a manifest; a key the original did not read is reported."""

    def __init__(self, manifest: SnapshotManifest) -> None:
        super().__init__(
            as_of_utc=manifest.as_of_utc,
            demo_desk=manifest.demo_desk,
            fx_method=manifest.fx_method,
            assumption_version=manifest.assumption_version,
        )
        self._source = {item.key: item for item in manifest.inputs}
        self.replay_misses: list[str] = []

    def _get(self, key: str, loader: Callable[[], SnapshotInput]) -> SnapshotInput:
        held = self._recorded.get(key)
        if held is not None:
            return held
        item = self._source.get(key)
        if item is None:
            self.replay_misses.append(key)
            item = loader()  # the base loaders answer "missing"
        return self._record(item)

    def _get_collection(
        self, key: str, kind: InputKind, loader: Callable[[], Iterable[SnapshotInput]]
    ) -> tuple[SnapshotInput, ...]:
        collection = self._source.get(key)
        if collection is None:
            self.replay_misses.append(key)
            return ()
        self._record(collection)
        return tuple(
            self._record(self._source[member]) for member in collection.detail.get("members", ())
        )


class FixtureReader(RecordingReader):
    """A reader over a fixed list of inputs, for evaluator tests and golden cases.

    Inputs are given already keyed (use the key builders above); a read of any other key is
    recorded as missing, exactly as the live reader would record a gap.
    """

    def __init__(
        self,
        inputs: Iterable[SnapshotInput],
        *,
        as_of_utc: datetime,
        demo_desk: bool = False,
        fx_method: str = FX_METHOD_SPOT,
        collections: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        super().__init__(as_of_utc=as_of_utc, demo_desk=demo_desk, fx_method=fx_method)
        self._fixture = {item.key: item for item in inputs}
        self._collections = {key: list(members) for key, members in (collections or {}).items()}

    def _get(self, key: str, loader: Callable[[], SnapshotInput]) -> SnapshotInput:
        held = self._recorded.get(key)
        if held is not None:
            return held
        return self._record(self._fixture.get(key) or loader())

    def _load_outages(self, zone, period) -> list[SnapshotInput]:
        members = self._collections.get(outages_key(zone, period), [])
        return [self._fixture[key] for key in members]

    def _load_collection(self, name: str) -> list[SnapshotInput]:
        members = self._collections.get(collection_key(name))
        if members is None:
            members = [key for key in self._fixture if key.startswith(f"{name}:")]
        return [self._fixture[key] for key in members]

    def _load_hedge_cover(self) -> list[SnapshotInput]:
        members = self._collections.get(HEDGE_COVER_KEY)
        if members is None:
            members = [key for key in self._fixture if key.startswith("book:hedge:")]
        return [self._fixture[key] for key in members]
