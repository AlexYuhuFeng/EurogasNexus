/**
 * The desk's spread board, what Research → Spreads opens on (owner, 2026-11-19): locational
 * spreads against TTF (front month and day-ahead, gross and net of the cheapest route, where
 * today sits in its year, the last 30 closes), time spreads per focus hub (DA − MA, the next two
 * months, Win − Sum against the storage carry, Cal against Cal) and cross-commodity spreads
 * (Henry Hub against TTF delivered; the clean spark where power and carbon are held). Every
 * figure is the server's; a row opens the full workbench with its spec filled.
 */
import { useTranslation } from "react-i18next";

import type { BoardTenorDTO, SpreadBoardDTO, StrategySpecDTO } from "@/api/spreads";
import { cargoSearch, fullSpec, rangePosition, routeGap } from "@/app/model/spreadsBoard";
import { unitLabel } from "@/app/model/instrumentPicker";
import { useSimulatedPills } from "@/components/ui/SimulatedScope";
import { PercentileStrip, Sparkline } from "@/components/ui/charts";
import { followLink } from "./NextSteps";

const fixed = (value: number | null | undefined, decimals = 2): string =>
  value === null || value === undefined || !Number.isFinite(value) ? "–" : value.toFixed(decimals).replace("-", "−");
const signed = (value: number | null | undefined, decimals = 2): string =>
  value === null || value === undefined || !Number.isFinite(value) ? "–" : `${value > 0 ? "+" : ""}${fixed(value, decimals)}`;

function Sim({ on }: { on: boolean | undefined }) {
  const { t } = useTranslation();
  const pills = useSimulatedPills();
  return on && pills ? <span className="spreads-sim">{t("instrument_picker.sim")}</span> : null;
}

function TenorCells({ tenor, unit }: { tenor: BoardTenorDTO; unit: string }) {
  const { t } = useTranslation();
  if (!tenor.available) {
    return (
      <>
        <td className="num board-muted" colSpan={tenor.tenor === "MA" ? 4 : 2}>{t("spreads.board.not_held")}</td>
      </>
    );
  }
  const gap = routeGap(tenor);
  const via = tenor.route && tenor.route.through.length > 0 ? ` ${t("spreads.route.via", { hubs: tenor.route.through.join(", ") })}` : "";
  const legs = (tenor.legs ?? []).map((leg) => `${leg.hub} ${fixed(leg.native_value, 3)} ${unitLabel(leg.native_unit)}`).join(" · ");
  const range = rangePosition(tenor);
  return (
    <>
      <td className="num" data-figure="gross" title={legs}>
        <strong>{signed(tenor.gross, 3)}</strong> <Sim on={tenor.simulated} />
      </td>
      <td className="num" data-figure="net" title={tenor.direction ? `${tenor.direction}${via}` : undefined}>
        {tenor.net != null ? (
          <>
            {signed(tenor.net, 3)}
            <span className="board-muted"> {tenor.direction}{via}</span>
          </>
        ) : (
          <span className="board-gap" title={gap ?? undefined}>{t("spreads.board.route_not_priced")}</span>
        )}
      </td>
      {tenor.tenor === "MA" && (
        <>
          <td className="board-range">
            {range ? (
              <PercentileStrip
                position={range.position}
                caption={t("spreads.board.percentile", { value: Math.round(range.position) })}
                window={t("spreads.board.window", { days: range.days })}
                lowLabel={fixed(range.low, 1)}
                highLabel={fixed(range.high, 1)}
                t={t}
              />
            ) : (
              <span className="board-muted">{t("spreads.board.short_history")}</span>
            )}
          </td>
          <td className="board-spark">
            {tenor.spark && tenor.spark.values.length > 1 && (
              <Sparkline
                values={tenor.spark.values}
                days={tenor.spark.days}
                label={t("spreads.board.spark")}
                unit={unit}
                decimals={2}
                simulated={tenor.simulated}
                t={t}
              />
            )}
          </td>
        </>
      )}
    </>
  );
}

export function SpreadsBoard({ board, onOpen }: { board: SpreadBoardDTO; onOpen: (spec: StrategySpecDTO) => void }) {
  const { t } = useTranslation();
  const unit = board.unit;
  return (
    <section className="spreads-board" aria-label={t("spreads.board.title")} data-spread-board="true">
      <h2 className="spreads-section-title">{t("spreads.board.title")}</h2>

      <div className="spreads-table-wrap" data-board="locational">
        <table className="spreads-table board-table">
          <caption>{t("spreads.board.locational", { reference: board.reference, unit })}</caption>
          <thead>
            <tr>
              <th scope="col">{t("spreads.board.pair")}</th>
              <th scope="col" className="num">{t("spreads.board.ma_gross")}</th>
              <th scope="col" className="num">{t("spreads.board.net")}</th>
              <th scope="col">{t("spreads.board.year")}</th>
              <th scope="col">{t("spreads.board.days30")}</th>
              <th scope="col" className="num">{t("spreads.board.da_gross")}</th>
              <th scope="col" className="num">{t("spreads.board.da_net")}</th>
            </tr>
          </thead>
          <tbody>
            {board.locational.map((row) => (
              <tr key={row.pair} data-board-pair={row.hub}>
                <th scope="row">
                  <button type="button" className="board-open" onClick={() => onOpen(fullSpec(row.spec))}>
                    {row.hub} − {row.reference}
                  </button>
                </th>
                {row.tenors.map((tenor) => <TenorCells key={tenor.tenor} tenor={tenor} unit={unit} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="board-time" data-board="time">
        {board.time.map((hub) => (
          <div key={hub.hub} className="board-time-hub" id={`board-time-${hub.hub}`}>
            <h3>{t("spreads.board.time", { hub: hub.hub, unit: hub.unit })} <Sim on={hub.simulated} /></h3>
            <table className="spreads-table">
              <tbody>
                {hub.rows.map((row) => (
                  <tr key={row.key} data-board-time={row.key}>
                    <th scope="row">
                      {row.spec ? (
                        <button type="button" className="board-open" onClick={() => onOpen(fullSpec(row.spec!))}>{row.label}</button>
                      ) : row.label}
                    </th>
                    <td className="num">{row.available ? <strong>{signed(row.value, 3)}</strong> : "–"}</td>
                    <td className="board-muted">
                      {!row.available
                        ? t("spreads.board.not_held_reason", { reason: row.reason ?? "" })
                        : row.carry
                          ? row.carry.total != null
                            ? t("spreads.board.net_of_carry", { carry: fixed(row.carry.total, 3), net: signed(row.net_of_carry, 3) })
                            : t("spreads.board.carry_not_held")
                          : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <div className="board-cross" data-board="cross">
        <h3>{t("spreads.board.cross")}</h3>
        <ul>
          {board.cross.map((row) => (
            <li key={row.key} data-board-cross={row.key}>
              <strong>{t(`spreads.board.cross.${row.key}`, { defaultValue: row.label })}</strong>{" "}
              {row.available ? (
                <>
                  <span data-figure="cross">{signed(row.value, 2)} {unitLabel(`${row.currency ?? "EUR"}/MWh`)}</span> <Sim on={row.simulated} />
                  <span className="board-muted">
                    {" "}{t("spreads.board.hh_line", {
                      delivered: fixed(row.delivered, 2),
                      hub: row.hub,
                      price: fixed(row.hub_price, 2),
                      terminal: row.terminal,
                      hh: fixed(row.hh, 3),
                      count: row.assumptions ?? 0,
                    })}{" "}
                  </span>
                  <a
                    className="ds-inline-link"
                    href={cargoSearch(typeof window === "undefined" ? "" : window.location.search, row.hub ?? "TTF")}
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
                      event.preventDefault();
                      followLink(cargoSearch(window.location.search, row.hub ?? "TTF"));
                    }}
                  >
                    {t("spreads.board.open_cargo")}
                  </a>
                </>
              ) : (
                <span className="board-muted">{t("spreads.board.not_held_reason", { reason: row.reason ?? "" })}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
