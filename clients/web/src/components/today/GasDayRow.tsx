/**
 * Today row 6, "My gas day" (owner, 2026-11-19): per hub, today and tomorrow, what comes in,
 * what goes out, the net to clear in the hub's unit, what has been done today, how long until
 * the next cut-off and what leaving it open would cost. One server read
 * (`GET /api/desk/today`, `rows[5]`, `application/gas_day.py`); nothing is recomputed here but
 * the minutes until a cut-off. Nothing here nominates or trades (AGENTS.md rule 8): each line
 * opens where it is acted on or evidenced.
 */
import { useState } from "react";

import type { GasDayHubDTO, GasDayLineDTO, GasDayTargetDTO, TodayGasDayRowDTO } from "@/api/client";
import {
  basisKey,
  formatQuantity,
  kindKey,
  mwText,
  cutoffUrgency,
  nextCutoff,
  sides,
  timeLeft,
} from "@/app/model/gasDayModel";
import { formatGasDay } from "@/app/time/timeFormat";
import { useConvertedQuantity } from "@/app/time/useConversion";
import { useInstantFormatter } from "@/app/time/useInstant";
import { EmptyState, KeyFigure, Segmented, StatusBadge } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface GasDayRowProps {
  row: TodayGasDayRowDTO;
  t: Translate;
  language: string;
  nowMs: number;
  onOpen?: (target: GasDayTargetDTO) => void;
}

const STATE_TONE = { long: "info", short: "watch", balanced: "ok" } as const;

function cutoffName(cut: { key: string; name: string | null }, t: Translate): string {
  return cut.key === "window" && cut.name ? cut.name : t(`today.gas_day.cutoff.${cut.key}`);
}

function LineItem({ line, t, onOpen }: { line: GasDayLineDTO; t: Translate; onOpen?: (target: GasDayTargetDTO) => void }) {
  const name = line.prompt_trade
    ? t(line.direction === "in" ? "today.gas_day.prompt_bought" : "today.gas_day.prompt_sold", { count: Number(line.label) || 0 })
    : line.label;
  const kind = t(kindKey(line.kind));
  return (
    <li className="gasday-line" data-gasday-line={line.kind} data-direction={line.direction}>
      <span className="gasday-line-name">
        {onOpen ? (
          <button type="button" className="gasday-link" onClick={() => onOpen(line.target)} title={kind}>
            {name}
          </button>
        ) : (
          <span title={kind}>{name}</span>
        )}
        <span className="gasday-line-meta muted">
          {[line.point, t(basisKey(line.basis))].filter(Boolean).join(" · ")}
        </span>
        {(line.adjustments ?? []).map((item) => (
          <span key={item.id} className="gasday-line-meta muted" data-outage={item.id}>
            {t("today.gas_day.outage", { asset: item.asset, share: item.share_out_pct, source: item.source, id: item.id, quantity: formatQuantity(item.quantity) })}
          </span>
        ))}
      </span>
      <span className="gasday-line-qty">{formatQuantity(line.quantity)}</span>
    </li>
  );
}

function HubCard({ hub, t, nowMs, onOpen }: { hub: GasDayHubDTO; t: Translate; nowMs: number; onOpen?: (target: GasDayTargetDTO) => void }) {
  const formatInstant = useInstantFormatter();
  const converted = useConvertedQuantity({ value: hub.net.value, unit: hub.net.unit, simulated: hub.simulated });
  const { in: ins, out: outs } = sides(hub);
  const next = nextCutoff(hub.cutoffs, nowMs);
  const left = next ? timeLeft(next.at_utc, nowMs) : null;
  const at = next ? formatInstant(next.at_utc, { nowMs }) : null;
  const cost = hub.cost_of_nothing;
  const urgency = next ? cutoffUrgency(next.at_utc, nowMs) : "none";
  const band = hub.band;
  const mw = mwText(hub.net, true);
  const unit = hub.net.unit;
  const done = hub.done_today;
  return (
    <article className="gasday-hub" data-gasday-hub={hub.hub} data-gasday-state={hub.state} aria-label={t("today.gas_day.hub_label", { hub: hub.hub })}>
      <header className="gasday-hub-head">
        <h3 className="gasday-hub-name">{hub.hub}</h3>
        <StatusBadge tone={STATE_TONE[hub.state]}>{t(`today.gas_day.state.${hub.state}`)}</StatusBadge>
      </header>
      <KeyFigure
        label={t("today.gas_day.net")}
        value={formatQuantity(hub.net, true)}
        unit={unit}
        size="lg"
        detail={[mw ? t("today.gas_day.mw", { value: mw }) : null,
          hub.state === "balanced" && band ? t(band.basis === "assumption" ? "today.gas_day.band_set" : "today.gas_day.band_default", { pct: band.pct, set: band.set ?? "" }) : null]
          .filter(Boolean).join(" · ") || undefined}
        converted={converted}
        convertedMode="hover"
      />
      <dl className="gasday-facts">
        <div className="gasday-fact" data-gasday-fact="time_left" data-urgency={urgency}>
          <dt>{t("today.gas_day.time_left")}</dt>
          <dd>
            {next && at && left ? (
              <span title={`${at.title} · ${t(`today.gas_day.basis_of.${next.basis}`, { source: next.source })}`}>
                {t("today.gas_day.until", { name: cutoffName(next, t), time: at.text })}
                {" · "}
                <strong>{t("today.gas_day.left", { hours: left.hours, minutes: left.minutes })}</strong>
                {next.basis === "assumption" && <span className="gasday-assumed"> {t("today.gas_day.assumed")}</span>}
              </span>
            ) : (
              t("today.gas_day.day_over")
            )}
          </dd>
        </div>
        <div className="gasday-fact" data-gasday-fact="cost">
          <dt>{t("today.gas_day.cost")}</dt>
          <dd>
            {cost.basis === "balanced" ? (
              t("today.gas_day.cost_none")
            ) : cost.value === null ? (
              <span className="muted" title={cost.reason}>
                {t("today.gas_day.cost_missing")}
                <span className="gasday-hint"> {t("today.gas_day.cost_where")}</span>
              </span>
            ) : cost.basis === "published" ? (
              // The TSO's own published cash-out (live by default), with its gas day and source.
              <span
                data-cost-basis="published"
                title={t(cost.side === "short_premium" ? "today.gas_day.cost_basis_published_short" : "today.gas_day.cost_basis_published_long", {
                  price: cost.published_price,
                  reference: cost.published_reference,
                  rate: cost.rate,
                  unit: cost.rate_unit,
                  publisher: cost.published_publisher ?? cost.published_source ?? "",
                  day: cost.published_gas_day,
                  status: t(`board.published.status.${cost.published_status === "preliminary" ? "preliminary" : "final"}`),
                })}
              >
                <strong>{Math.round(cost.value).toLocaleString("en-GB")} {cost.currency}</strong>
                <span className="gasday-assumed"> {t("today.gas_day.published", { day: cost.published_gas_day ?? "" })}</span>
              </span>
            ) : (
              <span
                title={t(cost.side === "short_premium" ? "today.gas_day.cost_basis_short" : "today.gas_day.cost_basis_long", {
                  rate: cost.rate,
                  unit: cost.rate_unit,
                  set: cost.assumption_set,
                  version: cost.assumption_version,
                })}
              >
                <strong>{Math.round(cost.value).toLocaleString("en-GB")} {cost.currency}</strong>
                <span className="gasday-assumed"> {t("today.gas_day.assumed")}</span>
              </span>
            )}
          </dd>
        </div>
        <div className="gasday-fact" data-gasday-fact="done">
          <dt>{t("today.gas_day.done")}</dt>
          <dd>
            {done.trades > 0 ? (
              <button type="button" className="gasday-link" onClick={() => onOpen?.(done.target)}>
                {t("today.gas_day.done_trades", {
                  count: done.trades,
                  bought: formatQuantity(done.bought),
                  sold: formatQuantity(done.sold),
                  unit,
                })}
              </button>
            ) : (
              <button type="button" className="gasday-link muted" onClick={() => onOpen?.(done.target)}>
                {t("today.gas_day.done_none")}
              </button>
            )}
          </dd>
        </div>
      </dl>
      <div className="gasday-sides">
        {(["in", "out"] as const).map((side) => {
          const lines = side === "in" ? ins : outs;
          const total = side === "in" ? hub.in : hub.out;
          return (
            <div key={side} role="group" className="gasday-side" data-gasday-side={side} aria-label={`${hub.hub} ${t(`today.gas_day.${side}`)}`}>
              <h4 className="gasday-side-head">
                <span>{t(`today.gas_day.${side}`)}</span>
                <span className="gasday-line-qty">{formatQuantity(total)} <small>{unit}</small></span>
              </h4>
              {lines.length > 0 ? (
                <ul className="gasday-lines">
                  {lines.map((line) => <LineItem key={line.ref} line={line} t={t} onOpen={onOpen} />)}
                </ul>
              ) : (
                <p className="gasday-none muted">{t("today.gas_day.none")}</p>
              )}
            </div>
          );
        })}
      </div>
      {hub.delegated.length > 0 && (
        <ul className="gasday-delegated" aria-label={t("today.gas_day.delegated")}>
          {hub.delegated.map((item) => (
            <li key={`${item.ref}-${item.trader}`} data-gasday-delegated={item.trader}>
              {t("today.gas_day.delegated_line", {
                quantity: formatQuantity(item.quantity),
                unit: item.quantity.unit,
                label: item.label,
                trader: item.trader_name,
              })}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function GasDayRow({ row, t, language, nowMs, onOpen }: GasDayRowProps) {
  const [which, setWhich] = useState<"today" | "tomorrow">("today");
  const day = row.days.find((item) => item.which === which) ?? row.days[0];
  const scope = row.scope;
  const scopeText = !scope
    ? null
    : scope.kind === "mandate"
      ? t("today.gas_day.scope_mandate", { names: scope.mandates.map((item) => item.name).join(", ") })
      : t("today.gas_day.scope_all");
  return (
    <section className="today-row today-row-gas_day" aria-labelledby="today-row-gas_day" data-today-row="gas_day">
      <header className="today-row-head">
        <h2 id="today-row-gas_day">{t("today.row.gas_day")}</h2>
        {scopeText && <span className="today-row-meta">{scopeText}{row.simulated ? ` · ${t("today.gas_day.simulated")}` : ""}</span>}
      </header>
      {row.days.length > 1 && (
        <Segmented
          label={t("today.gas_day.day_choice")}
          value={which}
          onChange={setWhich}
          options={row.days.map((item) => ({
            value: item.which,
            label: t(`today.gas_day.${item.which}`, { day: formatGasDay(item.gas_day, language) }),
          }))}
        />
      )}
      {!row.populated || !day ? (
        <EmptyState compact reason={row.empty?.reason ?? t("today.gas_day.empty")} next={row.empty?.action} />
      ) : day.hubs.length === 0 ? (
        <EmptyState compact reason={t("today.gas_day.empty_day")} />
      ) : (
        <div className="gasday-hubs" data-gasday-day={day.which}>
          {day.hubs.map((hub) => <HubCard key={hub.hub} hub={hub} t={t} nowMs={nowMs} onOpen={onOpen} />)}
        </div>
      )}
    </section>
  );
}
