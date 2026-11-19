/**
 * Reviewed public transmission tariffs on Admin → Connectors → Access.
 *
 * ENTSOG leaves some legs a route needs unpublished (National Gas at Bacton and Moffat, GTS's
 * exit to BBL, LNG and Norwegian landing entries). The operators publish them on their own
 * sites, so a person reads the published charge and enters it here:
 * - **Legs that block routes** come first: each names the crossings it blocks and whether it
 *   can be entered (the reference network names its operator). "Enter" fills the form.
 * - **The form** picks point, operator and direction from the reference network (RecordPicker,
 *   UX_REFERENCE rule 25), then the value in the unit and currency the operator published, its
 *   validity, the operator's status and where it was read (URL, publication date, page).
 * - **Entries**: a candidate prices its leg as indicative until a second person reviews it
 *   (four eyes, enforced by the server); a published ENTSOG row for the same leg retires it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type TariffEntriesViewDTO,
  type TariffEntryDTO,
  type TariffEntryRequestDTO,
  type TariffMissingLegDTO,
} from "@/api/client";
import {
  Button,
  DataGrid,
  Field,
  PeriodPicker,
  PanelHeader,
  RecordPicker,
  Segmented,
  Select,
  StatusBadge,
  type DataGridColumn,
  type RecordOption,
} from "@/components/ui";
import { ENTRY_UNITS, draftMissing, emptyDraft, type Draft } from "@/app/model/tariffEntryModel";
import { useApiStore } from "@/stores/api";
import "./lng-tariff-register.css";
import "./tariff-entry.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function TariffEntryPanel({ t }: { t: Translate }) {
  const currentUser = useApiStore((state) => state.currentUser);
  const roles = currentUser?.roles ?? (currentUser?.role ? [currentUser.role] : []);
  const canWrite = roles.includes("ADMIN") || roles.includes("OPERATOR");
  const [view, setView] = useState<TariffEntriesViewDTO | null>(null);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.tariffEntries();
      setView(response.data);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const operatorName = useMemo(() => {
    const names = new Map<string, string>();
    for (const operator of view?.choices.operators ?? []) names.set(operator.operator_key, operator.name);
    return names;
  }, [view]);

  const pointOptions = useMemo<RecordOption[] | null>(
    () =>
      view
        ? view.choices.points.map((point) => ({
            id: point.point_key,
            label: point.name,
            detail: [point.country, t(`tariff_entry.kind.${point.kind}`)].filter(Boolean).join(" · "),
            keywords: [point.point_key],
          }))
        : null,
    [t, view],
  );

  const point = view?.choices.points.find((item) => item.point_key === draft?.point_key) ?? null;
  const operatorOptions = useMemo<RecordOption[] | null>(
    () =>
      point
        ? point.operators.map((item) => ({
            id: item.operator_key,
            label: operatorName.get(item.operator_key) ?? item.operator_key,
            keywords: [item.operator_key],
          }))
        : view
          ? []
          : null,
    [operatorName, point, view],
  );

  const startFrom = (leg: TariffMissingLegDTO | null) => {
    const next = emptyDraft();
    if (leg) {
      next.point_key = leg.point_key;
      next.direction = leg.direction;
      const at = view?.choices.points.find((item) => item.point_key === leg.point_key);
      const named = at?.operators.find((item) => (operatorName.get(item.operator_key) ?? "") === leg.tso);
      next.operator_key = named?.operator_key ?? (at?.operators.length === 1 ? at.operators[0].operator_key : null);
      if (next.operator_key?.startsWith("UK-")) {
        next.currency = "GBP";
        next.unit = "p/kWh/d";
      }
    }
    setDraft(next);
    setTried(false);
    setMessage(null);
  };

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => (current ? { ...current, [key]: value } : current));

  const submit = async () => {
    if (!draft) return;
    setTried(true);
    if (draftMissing(draft).length) return;
    setBusy(true);
    setMessage(null);
    const body: TariffEntryRequestDTO = {
      operator_key: draft.operator_key as string,
      point_key: draft.point_key as string,
      direction: draft.direction,
      capacity_product: draft.capacity_product,
      firmness: draft.firmness,
      tariff_value: Number(draft.tariff_value),
      unit: draft.unit,
      currency: draft.currency,
      valid_from: draft.valid_from,
      valid_to: draft.valid_to,
      published_status: draft.published_status,
      source_url: draft.source_url.trim(),
      published_on: draft.published_on,
      source_location: draft.source_location.trim(),
      note: draft.note.trim() || null,
    };
    try {
      await api.recordTariffEntry(body);
      setDraft(null);
      setMessage(t("tariff_entry.recorded"));
      await load();
    } catch (error) {
      const detail = error instanceof ApiError ? (error.detail as { code?: string; message?: string } | null) : null;
      setMessage(detail?.code ? t(`tariff_entry.error.${detail.code}`, { defaultValue: detail.message ?? detail.code }) : t("tariff_entry.save_failed"));
    } finally {
      setBusy(false);
    }
  };

  const act = useCallback(
    async (entry: TariffEntryDTO, action: "review" | "withdraw") => {
      setBusy(true);
      setMessage(null);
      try {
        if (action === "review") await api.reviewTariffEntry(entry.entry_id);
        else await api.withdrawTariffEntry(entry.entry_id, t("tariff_entry.withdraw_reason"));
        await load();
      } catch (error) {
        const detail = error instanceof ApiError ? (error.detail as { code?: string } | null) : null;
        setMessage(t(detail?.code === "four_eyes" ? "tariff_entry.four_eyes" : "tariff_entry.save_failed"));
      } finally {
        setBusy(false);
      }
    },
    [load, t],
  );

  const missingColumns = useMemo<DataGridColumn<TariffMissingLegDTO>[]>(
    () => [
      { id: "point", header: t("tariff_entry.col.point"), value: (row) => row.point_name, rowHeader: true, priority: "primary" },
      { id: "operator", header: t("tariff_entry.col.operator"), value: (row) => row.tso ?? "", render: (row) => row.tso ?? "—", priority: "primary" },
      { id: "direction", header: t("tariff_entry.col.direction"), value: (row) => row.direction, render: (row) => t(`tariff_entry.direction.${row.direction}`) },
      {
        id: "blocks",
        header: t("tariff_entry.col.blocks"),
        value: (row) => row.blocks.length,
        render: (row) => (
          <span title={row.blocks.join(", ")}>
            {row.kind !== "crossing" && row.into
              ? t(`tariff_entry.supply_blocks.${row.kind}`, { into: row.into.join(", ") })
              : row.blocks.slice(0, 3).join(", ")}
            {row.kind === "crossing" && row.blocks.length > 3 ? ` +${row.blocks.length - 3}` : ""}
            {row.drawn ? <StatusBadge tone="watch">{t("tariff_entry.drawn")}</StatusBadge> : null}
          </span>
        ),
      },
      {
        id: "enter",
        header: t("tariff_entry.col.action"),
        value: (row) => (row.can_be_entered ? 1 : 0),
        priority: "primary",
        render: (row) =>
          row.can_be_entered ? (
            canWrite ? (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => startFrom(row)}>
                {t("tariff_entry.enter")}
              </Button>
            ) : (
              <span className="muted">{t("tariff_entry.ask_operator")}</span>
            )
          ) : (
            <span className="muted">{t(`tariff_entry.why_not.${row.why_not === "no operator named" ? "operator" : "point"}`)}</span>
          ),
      },
    ],
    // startFrom reads the view it was made with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [busy, canWrite, t, view],
  );

  const entryColumns = useMemo<DataGridColumn<TariffEntryDTO>[]>(
    () => [
      { id: "point", header: t("tariff_entry.col.point"), value: (row) => row.point_name, rowHeader: true, priority: "primary" },
      {
        id: "leg",
        header: t("tariff_entry.col.leg"),
        value: (row) => row.tso,
        render: (row) => `${row.tso} · ${t(`tariff_entry.direction.${row.direction}`)} · ${t(`tariff_entry.product.${row.capacity_product}`)}`,
      },
      {
        id: "charge",
        header: t("tariff_entry.col.charge"),
        value: (row) => row.tariff_value,
        render: (row) => `${row.tariff_value} ${row.unit}`,
        align: "end",
        priority: "primary",
      },
      { id: "valid", header: t("tariff_entry.col.valid"), value: (row) => row.valid_from, render: (row) => row.gas_year },
      {
        id: "source",
        header: t("tariff_entry.col.source"),
        value: (row) => row.source_url,
        render: (row) => (
          <a href={row.source_url} target="_blank" rel="noreferrer" title={`${row.published_on} · ${row.source_location}`}>
            {t("tariff_entry.source_link", { date: row.published_on })}
          </a>
        ),
      },
      {
        id: "state",
        header: t("tariff_entry.col.state"),
        value: (row) => row.state,
        priority: "primary",
        render: (row) =>
          row.state === "CANDIDATE" && canWrite ? (
            <span className="tariff-entry-actions">
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => void act(row, "review")}>
                {t("tariff_entry.review")}
              </Button>
              <Button size="sm" variant="quiet" disabled={busy} onClick={() => void act(row, "withdraw")}>
                {t("tariff_entry.withdraw")}
              </Button>
            </span>
          ) : (
            <StatusBadge
              tone={row.state === "REVIEWED" ? "ok" : row.state === "CANDIDATE" ? "watch" : "neutral"}
              title={row.reviewed_by ? t("tariff_entry.reviewed_by", { name: row.reviewed_by }) : (row.closed_reason ?? undefined)}
            >
              {t(`tariff_entry.state.${row.state}`)}
            </StatusBadge>
          ),
      },
    ],
    [act, busy, canWrite, t],
  );

  if (failed && !view) {
    return (
      <section className="workspace-panel span-3 lng-tariff-register" data-record="tariff-entries">
        <PanelHeader title={t("tariff_entry.title")} />
        <p className="muted">{t("tariff_entry.read_failed")}</p>
      </section>
    );
  }

  const missing = draft ? draftMissing(draft) : [];
  // Legs on a drawn route and supply entries first; legs at points the market books through a
  // virtual point (Bocholtz, Zevenaar ...) are one click away.
  const primary = (view?.missing ?? []).filter((leg) => leg.drawn || leg.kind !== "crossing");
  const secondary = (view?.missing ?? []).filter((leg) => !leg.drawn && leg.kind === "crossing");
  const enterable = (view?.missing ?? []).filter((leg) => leg.can_be_entered).length;
  return (
    <section className="workspace-panel span-3 lng-tariff-register tariff-entry" aria-labelledby="tariff-entry-title" data-record="tariff-entries">
      <PanelHeader
        headingId="tariff-entry-title"
        title={t("tariff_entry.title")}
        meta={t("tariff_entry.meta", { missing: view?.missing.length ?? 0, enterable, ...(view?.counts ?? { candidate: 0, reviewed: 0, retired: 0 }) })}
      />
      <p className="muted tariff-entry-intro">{t("tariff_entry.intro")}</p>
      <h3 className="lng-tariff-subhead">{t("tariff_entry.missing")}</h3>
      <DataGrid
        id="tariff-entry-missing"
        label={t("tariff_entry.missing")}
        density="compact"
        columns={missingColumns}
        rows={primary}
        rowKey={(row) => `${row.point_key}:${row.tso ?? ""}:${row.direction}`}
        rowAttributes={(row) => ({ "data-record": "tariff-missing-leg", "data-can-be-entered": String(row.can_be_entered) })}
        loading={!view}
        loadingLabel={t("tariff_entry.loading")}
        empty={<span data-empty-state="tariff-missing">{t("tariff_entry.none_missing")}</span>}
      />
      {secondary.length > 0 && (
        <details className="tariff-entry-more" data-record="tariff-missing-more">
          <summary>{t("tariff_entry.more_missing", { count: secondary.length })}</summary>
          <DataGrid
            id="tariff-entry-missing-more"
            label={t("tariff_entry.more_missing", { count: secondary.length })}
            density="compact"
            columns={missingColumns}
            rows={secondary}
            rowKey={(row) => `${row.point_key}:${row.tso ?? ""}:${row.direction}`}
            rowAttributes={(row) => ({ "data-record": "tariff-missing-leg", "data-can-be-entered": String(row.can_be_entered) })}
            loading={false}
            loadingLabel={t("tariff_entry.loading")}
            empty={<span data-empty-state="tariff-missing">{t("tariff_entry.none_missing")}</span>}
          />
        </details>
      )}
      {canWrite && !draft && (
        <div className="lng-tariff-actions">
          <Button size="sm" variant="secondary" onClick={() => startFrom(null)}>
            {t("tariff_entry.new")}
          </Button>
        </div>
      )}
      {draft && (
        <form
          className="tariff-entry-form ds-form-grid"
          data-record="tariff-entry-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <h3 className="lng-tariff-subhead">{t("tariff_entry.form_title")}</h3>
          <RecordPicker
            id="tariff-entry-point"
            label={t("tariff_entry.field.point")}
            options={pointOptions}
            value={draft.point_key}
            recentKey="tariff-entry-point"
            emptyText={t("tariff_entry.no_points")}
            onChange={(choice) => setDraft((current) => (current ? { ...current, point_key: choice?.id ?? null, operator_key: null } : current))}
          />
          <RecordPicker
            id="tariff-entry-operator"
            label={t("tariff_entry.field.operator")}
            options={operatorOptions}
            value={draft.operator_key}
            recentKey="tariff-entry-operator"
            disabled={!draft.point_key}
            emptyText={t("tariff_entry.choose_point_first")}
            onChange={(choice) => set("operator_key", choice?.id ?? null)}
          />
          <div className="ds-field">
            <span className="ds-field-label">{t("tariff_entry.field.direction")}</span>
            <Segmented
              label={t("tariff_entry.field.direction")}
              value={draft.direction}
              options={[
                { value: "EXIT", label: t("tariff_entry.direction.EXIT") },
                { value: "ENTRY", label: t("tariff_entry.direction.ENTRY") },
              ]}
              onChange={(value) => set("direction", value as "ENTRY" | "EXIT")}
            />
          </div>
          <Field label={t("tariff_entry.field.product")}>
            <Select
              value={draft.capacity_product}
              options={(view?.choices.products ?? ["ANNUAL"]).map((value) => ({ value, label: t(`tariff_entry.product.${value}`) }))}
              onChange={(value) => set("capacity_product", value)}
            />
          </Field>
          <Field label={t("tariff_entry.field.firmness")}>
            <Select
              value={draft.firmness}
              options={(view?.choices.firmness ?? ["FIRM"]).map((value) => ({ value, label: t(`tariff_entry.firmness.${value}`) }))}
              onChange={(value) => set("firmness", value)}
            />
          </Field>
          <Field label={t("tariff_entry.field.value")} error={tried && missing.includes("value") ? t("tariff_entry.need.value") : undefined}>
            <input inputMode="decimal" value={draft.tariff_value} onChange={(event) => set("tariff_value", event.target.value)} />
          </Field>
          <Field label={t("tariff_entry.field.currency")}>
            <Select
              value={draft.currency}
              options={Object.keys(ENTRY_UNITS).map((value) => ({ value, label: value }))}
              onChange={(value) => setDraft((current) => (current ? { ...current, currency: value, unit: ENTRY_UNITS[value][0] } : current))}
            />
          </Field>
          <Field label={t("tariff_entry.field.unit")} hint={t("tariff_entry.unit_hint")}>
            <Select value={draft.unit} options={(ENTRY_UNITS[draft.currency] ?? []).map((value) => ({ value, label: value }))} onChange={(value) => set("unit", value)} />
          </Field>
          <Field label={t("tariff_entry.field.valid_from")} error={tried && missing.includes("validity") ? t("tariff_entry.need.validity") : undefined}>
            <PeriodPicker label={t("tariff_entry.field.valid_from")} value={draft.valid_from} onChange={(value) => set("valid_from", value)} />
          </Field>
          <Field label={t("tariff_entry.field.valid_to")}>
            <PeriodPicker label={t("tariff_entry.field.valid_to")} value={draft.valid_to} clearable onChange={(value) => set("valid_to", value)} />
          </Field>
          <div className="ds-field">
            <span className="ds-field-label">{t("tariff_entry.field.status")}</span>
            <Segmented
              label={t("tariff_entry.field.status")}
              value={draft.published_status}
              options={[
                { value: "FINAL", label: t("tariff_entry.published.FINAL") },
                { value: "INDICATIVE", label: t("tariff_entry.published.INDICATIVE") },
              ]}
              onChange={(value) => set("published_status", value as "FINAL" | "INDICATIVE")}
            />
          </div>
          <Field label={t("tariff_entry.field.source_url")} error={tried && missing.includes("source_url") ? t("tariff_entry.need.source_url") : undefined}>
            <input type="url" placeholder="https://" value={draft.source_url} onChange={(event) => set("source_url", event.target.value)} />
          </Field>
          <Field label={t("tariff_entry.field.published_on")} error={tried && missing.includes("published_on") ? t("tariff_entry.need.published_on") : undefined}>
            <PeriodPicker label={t("tariff_entry.field.published_on")} value={draft.published_on} onChange={(value) => set("published_on", value)} />
          </Field>
          <Field label={t("tariff_entry.field.location")} hint={t("tariff_entry.location_hint")} error={tried && missing.includes("source_location") ? t("tariff_entry.need.location") : undefined}>
            <input value={draft.source_location} maxLength={256} onChange={(event) => set("source_location", event.target.value)} />
          </Field>
          <Field label={t("tariff_entry.field.note")}>
            <input value={draft.note} maxLength={1000} onChange={(event) => set("note", event.target.value)} />
          </Field>
          <p className="muted tariff-entry-four-eyes">{t("tariff_entry.four_eyes_note")}</p>
          <div className="lng-tariff-actions">
            <Button type="submit" disabled={busy}>
              {t("tariff_entry.save")}
            </Button>
            <Button variant="quiet" onClick={() => setDraft(null)} disabled={busy}>
              {t("tariff_entry.cancel")}
            </Button>
          </div>
        </form>
      )}
      <h3 className="lng-tariff-subhead">{t("tariff_entry.entries")}</h3>
      <DataGrid
        id="tariff-entry-rows"
        label={t("tariff_entry.entries")}
        density="compact"
        columns={entryColumns}
        rows={view?.entries ?? []}
        rowKey={(row) => row.entry_id}
        rowAttributes={(row) => ({ "data-record": "tariff-entry", "data-entry-state": row.state })}
        loading={!view}
        loadingLabel={t("tariff_entry.loading")}
        empty={<span data-empty-state="tariff-entries">{t("tariff_entry.empty")}</span>}
      />
      {message && (
        <p className="lng-tariff-message" role="status">
          {message}
        </p>
      )}
    </section>
  );
}
