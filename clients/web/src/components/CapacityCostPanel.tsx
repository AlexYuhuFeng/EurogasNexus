/**
 * TAR-2 capacity cost on Sources → Infrastructure: the capacity the firm holds, and a
 * requirement priced contracted first, then the public tariff for how the rest would be bought
 * (final where held at the instant asked, else indicative), else not held — never zero.
 *
 * Every layer names its booking or tariff version, status, tariff year, publication date and
 * source; the sources are listed in the order in force with the one used marked. The FX check
 * shows the same resolver for a currency pair. Read only: nothing is booked or nominated.
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  api,
  type CapacityBookingDTO,
  type CapacityCostDTO,
  type CapacityCostLayerDTO,
  type ResolvedRateDTO,
  type SourcePrecedenceDTO,
} from "@/api/client";
import {
  costHeadline,
  costText,
  fxText,
  layerReference,
  layerStatus,
  layerTone,
  quantityText,
  unitCostText,
} from "@/app/model/capacityCostModel";
import { originText, SourceSteps } from "@/components/SourceSteps";
import { Button, DataGrid, EmptyState, Field, Instant, Panel, PeriodPicker, Select, StatusBadge, type DataGridColumn } from "@/components/ui";
import { PanelHelp } from "@/components/ui/PanelHelp";

type Translate = (key: string, options?: Record<string, unknown>) => string;

type Kind = "pipeline" | "terminal";

interface Inputs {
  kind: Kind;
  facility: string;
  direction: string;
  first: string;
  last: string;
  mwhPerDay: string;
  product: string;
  premium: string;
  arrival: string;
  cargoMwh: string;
}

const START: Inputs = {
  kind: "pipeline",
  facility: "",
  direction: "EXIT",
  first: "",
  last: "",
  mwhPerDay: "",
  product: "DAILY",
  premium: "0",
  arrival: "",
  cargoMwh: "",
};

function numberOrUndefined(text: string): number | undefined {
  const value = Number(text);
  return text.trim() !== "" && Number.isFinite(value) ? value : undefined;
}

export function CapacityCostPanel({ t }: { t: Translate }) {
  const [bookings, setBookings] = useState<CapacityBookingDTO[] | null>(null);
  const [order, setOrder] = useState<SourcePrecedenceDTO | null>(null);
  const [inputs, setInputs] = useState<Inputs>(START);
  const [cost, setCost] = useState<CapacityCostDTO | null>(null);
  const [costError, setCostError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pair, setPair] = useState({ from: "USD", to: "EUR" });
  const [fx, setFx] = useState<ResolvedRateDTO | null>(null);

  useEffect(() => {
    api
      .capacityBookings()
      .then((response) => setBookings(response.data.rows))
      .catch(() => setBookings([]));
    api
      .sourcePrecedence()
      .then((response) => setOrder(response.data))
      .catch(() => setOrder(null));
  }, []);

  const set = (key: keyof Inputs) => (value: string) => setInputs((current) => ({ ...current, [key]: value }));

  const price = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setCostError(false);
    const query =
      inputs.kind === "pipeline"
        ? {
            kind: inputs.kind,
            facility: inputs.facility,
            direction: inputs.direction,
            first: inputs.first,
            last: inputs.last,
            mwh_per_day: numberOrUndefined(inputs.mwhPerDay),
            product: inputs.product,
            premium: numberOrUndefined(inputs.premium),
          }
        : {
            kind: inputs.kind,
            facility: inputs.facility,
            arrival: inputs.arrival,
            cargo_mwh: numberOrUndefined(inputs.cargoMwh),
          };
    api
      .capacityCost(query)
      .then((response) => setCost(response.data))
      .catch(() => {
        setCost(null);
        setCostError(true);
      })
      .finally(() => setBusy(false));
  };

  const checkFx = (event: FormEvent) => {
    event.preventDefault();
    api
      .fxRate(pair)
      .then((response) => setFx(response.data))
      .catch(() => setFx(null));
  };

  const bookingColumns = useMemo<DataGridColumn<CapacityBookingDTO>[]>(
    () => [
      { id: "id", header: t("capacityCost.booking.id"), value: (row) => row.booking_id, rowHeader: true },
      { id: "facility", header: t("tariffBook.col.facility"), value: (row) => row.facility_name ?? row.facility_id },
      { id: "kind", header: t("capacityCost.booking.kind"), value: (row) => [row.kind, row.direction].filter(Boolean).join(" ") },
      { id: "via", header: t("capacityCost.booking.via"), value: (row) => row.acquired_via },
      { id: "period", header: t("tariffBook.col.period"), value: (row) => `${row.first_gas_day} → ${row.last_gas_day}` },
      { id: "quantity", header: t("capacityCost.col.quantity"), align: "end", value: (row) => row.quantity, render: (row) => quantityText(row.quantity, row.quantity_unit) },
      {
        id: "price",
        header: t("capacityCost.booking.price"),
        value: (row) => row.price ?? "",
        render: (row) =>
          row.price_recorded ? `${row.price} ${row.price_unit ?? ""}` : <StatusBadge tone="watch">{t("capacityCost.booking.no_price")}</StatusBadge>,
      },
    ],
    [t],
  );

  const layerColumns = useMemo<DataGridColumn<CapacityCostLayerDTO>[]>(
    () => [
      {
        id: "layer",
        header: t("capacityCost.col.layer"),
        value: (row) => row.layer,
        rowHeader: true,
        render: (row) => (
          <StatusBadge tone={layerTone(row)} title={row.status_basis ? t(`tariffBook.basis.${row.status_basis}`) : undefined}>
            {t(`capacityCost.status.${layerStatus(row)}`)}
          </StatusBadge>
        ),
      },
      { id: "basis", header: t("capacityCost.col.basis"), value: (row) => layerReference(row) },
      { id: "quantity", header: t("capacityCost.col.quantity"), align: "end", value: (row) => row.quantity, render: (row) => quantityText(row.quantity, row.unit) },
      { id: "unit_cost", header: t("capacityCost.col.unit_cost"), align: "end", value: (row) => row.unit_cost ?? "", render: (row) => unitCostText(row) ?? t("capacityCost.not_given") },
      { id: "cost", header: t("capacityCost.col.cost"), align: "end", value: (row) => row.cost ?? "", render: (row) => costText(row.cost, row.currency) ?? t("capacityCost.not_given") },
      {
        id: "published",
        header: t("capacityCost.col.published"),
        value: (row) => row.published_at ?? row.recorded_at ?? "",
        render: (row) =>
          row.layer !== "public" ? (
            "—"
          ) : row.published_at ? (
            <Instant value={row.published_at} />
          ) : (
            <Instant value={row.recorded_at ?? null} prefix={t("capacityCost.recorded_only")} fallback="—" />
          ),
        priority: "secondary",
      },
      { id: "source", header: t("tariffBook.col.source"), value: (row) => row.source ?? "", priority: "secondary" },
    ],
    [t],
  );

  const headline = cost ? costHeadline(cost) : null;

  return (
    <Panel title={t("capacityCost.title")} className="span-3 capacity-cost">
      <PanelHelp text={t("capacityCost.copy")} label={t("panel.how_to_read")} />
      <h3 className="tariff-book-subhead">{t("capacityCost.bookings")}</h3>
      {bookings && bookings.length === 0 && <p className="tariff-book-muted">{t("capacityCost.bookings_empty")}</p>}
      {bookings && bookings.length > 0 && (
        <DataGrid
          label={t("capacityCost.bookings")}
          columns={bookingColumns}
          rows={bookings}
          rowKey={(row) => row.booking_id}
          density="compact"
          maxHeight="16rem"
        />
      )}
      <form className="capacity-cost-form" onSubmit={price}>
        <Field label={t("capacityCost.input.kind")}>
          <Select<Kind>
            value={inputs.kind}
            onChange={(value) => setInputs((current) => ({ ...current, kind: value, product: value === "pipeline" ? "DAILY" : "spot" }))}
            options={[
              { value: "pipeline", label: t("capacityCost.kind.pipeline") },
              { value: "terminal", label: t("capacityCost.kind.terminal") },
            ]}
          />
        </Field>
        <Field label={t("capacityCost.input.facility")}>
          <input className="ds-input" required maxLength={128} value={inputs.facility} onChange={(event) => set("facility")(event.target.value)} />
        </Field>
        {inputs.kind === "pipeline" ? (
          <>
            <Field label={t("capacityCost.input.direction")}>
              <Select value={inputs.direction} onChange={set("direction")} options={[{ value: "ENTRY", label: "ENTRY" }, { value: "EXIT", label: "EXIT" }]} />
            </Field>
            <Field label={t("capacityCost.input.first")}>
              <PeriodPicker label={t("capacityCost.input.first")} value={inputs.first} onChange={set("first")} />
            </Field>
            <Field label={t("capacityCost.input.last")}>
              <PeriodPicker label={t("capacityCost.input.last")} value={inputs.last} onChange={set("last")} />
            </Field>
            <Field label={t("capacityCost.input.mwh_per_day")}>
              <input className="ds-input" type="number" min={0} step="any" required value={inputs.mwhPerDay} onChange={(event) => set("mwhPerDay")(event.target.value)} />
            </Field>
            <Field label={t("capacityCost.input.product")} hint={t("capacityCost.input.product_hint")}>
              <Select
                value={inputs.product}
                onChange={set("product")}
                options={["DAILY", "WITHIN_DAY", "MONTHLY", "QUARTERLY", "ANNUAL"].map((value) => ({
                  value,
                  label: t(`capacityCost.product.${value}`),
                }))}
              />
            </Field>
            <Field label={t("capacityCost.input.premium")}>
              <input className="ds-input" type="number" min={0} step="any" value={inputs.premium} onChange={(event) => set("premium")(event.target.value)} />
            </Field>
          </>
        ) : (
          <>
            <Field label={t("capacityCost.input.arrival")}>
              <PeriodPicker label={t("capacityCost.input.arrival")} value={inputs.arrival} onChange={set("arrival")} />
            </Field>
            <Field label={t("capacityCost.input.cargo_mwh")}>
              <input className="ds-input" type="number" min={0} step="any" required value={inputs.cargoMwh} onChange={(event) => set("cargoMwh")(event.target.value)} />
            </Field>
          </>
        )}
        <Button type="submit" variant="primary" loading={busy}>
          {t("capacityCost.price")}
        </Button>
      </form>
      {costError && <EmptyState reason={t("capacityCost.unavailable")} compact />}
      {cost && (
        <section className="capacity-cost-result" aria-label={t("capacityCost.result")}>
          <p className="capacity-cost-total" data-state={headline ?? undefined}>
            <strong>{costText(cost.total_cost, cost.currency) ?? t("capacityCost.not_given")}</strong>
            <span>{t(`capacityCost.headline.${headline}`)}</span>
          </p>
          {cost.layers.length > 0 && (
            <DataGrid
              label={t("capacityCost.result")}
              columns={layerColumns}
              rows={cost.layers}
              rowKey={(row) => `${row.layer}:${row.reference ?? ""}:${row.first_gas_day ?? ""}`}
              density="compact"
            />
          )}
          {(cost.issues ?? []).map((issue) => (
            <p key={issue} className="tariff-book-muted">
              {issue}
            </p>
          ))}
          <SourceSteps sources={cost.sources} orderSource={cost.order_source} t={t} />
        </section>
      )}
      <details className="tariff-book-publishers">
        <summary>{t("sourceOrder.in_force")}</summary>
        {order && (
          <ul className="source-order-list">
            {order.kinds.map((kind) => (
              <li key={kind.kind}>
                <strong>{t(`sourceOrder.kind.${kind.kind}`)}</strong>
                <span>{kind.order.map((tier) => t(`sourceOrder.tier.${tier}`)).join(" → ")}</span>
                <span className="source-steps-origin">{originText(kind.order_source, t)}</span>
              </li>
            ))}
          </ul>
        )}
        {order && order.institutions.length === 0 && <p className="tariff-book-muted">{t("sourceOrder.no_bank")}</p>}
        {order && order.institutions.length > 0 && (
          <ul className="source-order-list">
            {order.institutions.map((bank) => (
              <li key={bank.key}>
                <strong>{bank.name}</strong>
                <span>{bank.provides.join(", ")}</span>
                <span className="source-steps-origin">{t(`sourceOrder.access.${bank.access}`)}</span>
              </li>
            ))}
          </ul>
        )}
        <form className="capacity-cost-form" onSubmit={checkFx}>
          <Field label={t("sourceOrder.fx_from")}>
            <input className="ds-input" required pattern="[A-Za-z]{3}" maxLength={3} value={pair.from} onChange={(event) => setPair((current) => ({ ...current, from: event.target.value.toUpperCase() }))} />
          </Field>
          <Field label={t("sourceOrder.fx_to")}>
            <input className="ds-input" required pattern="[A-Za-z]{3}" maxLength={3} value={pair.to} onChange={(event) => setPair((current) => ({ ...current, to: event.target.value.toUpperCase() }))} />
          </Field>
          <Button type="submit">{t("sourceOrder.fx_check")}</Button>
        </form>
        {fx && (
          <>
            <p className="capacity-cost-total">
              <strong>{fxText(fx) ?? t("capacityCost.not_given")}</strong>
            </p>
            <SourceSteps sources={fx.sources} orderSource={fx.order_source} t={t} />
          </>
        )}
      </details>
    </Panel>
  );
}
