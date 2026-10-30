import { useMemo, type KeyboardEvent } from "react";

import type { MarketQuoteDTO } from "@/api/client";
import {
  buildMarketLadder,
  formatLadderPrice,
  formatLadderVolume,
  type LadderSide,
} from "@/app/model/marketLadderModel";

type Translate = (key: string) => string;

interface MarketLadderProps {
  quotes: readonly MarketQuoteDTO[];
  hubs: readonly string[];
  focusedHub: string | null;
  onHubChange: (hub: string | null) => void;
  t: Translate;
}

function sideTitle(side: LadderSide | null): string | undefined {
  if (!side) return undefined;
  return `${side.source}${side.simulated ? " (simulated)" : ""} · ${side.priceUnit} · ${side.volumeUnit} · ${side.observedAtUtc}`;
}

/** Arrow keys move between cells like a trading grid; Tab still leaves the grid. */
function moveFocus(event: KeyboardEvent<HTMLTableElement>) {
  const target = event.target as HTMLElement;
  if (target.tagName !== "TD" && target.tagName !== "TH") return;
  const cell = target as HTMLTableCellElement;
  const row = cell.parentElement as HTMLTableRowElement | null;
  if (!row) return;
  let next: HTMLElement | null = null;
  if (event.key === "ArrowRight") next = cell.nextElementSibling as HTMLElement | null;
  if (event.key === "ArrowLeft") next = cell.previousElementSibling as HTMLElement | null;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    const sibling = (event.key === "ArrowDown" ? row.nextElementSibling : row.previousElementSibling) as
      | HTMLTableRowElement
      | null;
    next = (sibling?.cells[cell.cellIndex] as HTMLElement | undefined) ?? null;
  }
  if (next) {
    event.preventDefault();
    next.focus();
  }
}

/**
 * Products down, hubs across, Bid Vol | Bid | Offer | Offer Vol per hub: the execution-screen
 * layout traders already read, over the desk's own entitled quotes.
 */
export function MarketLadder({ quotes, hubs, focusedHub, onHubChange, t }: MarketLadderProps) {
  const rows = useMemo(() => buildMarketLadder(quotes, hubs), [quotes, hubs]);

  if (rows.length === 0) {
    return <p className="market-terminal-note">{t("ladder.empty")}</p>;
  }

  return (
    <div className="market-ladder-scroll" tabIndex={0}>
      <table className="market-ladder" data-market-ladder="true" onKeyDown={moveFocus} aria-label={t("ladder.title")}>
        <thead>
          <tr>
            <th rowSpan={2} className="market-ladder-product">{t("ladder.product")}</th>
            {hubs.map((hub) => (
              <th
                key={`ladder-hub-${hub}`}
                colSpan={4}
                className={focusedHub === hub ? "market-ladder-hub focused" : "market-ladder-hub"}
              >
                <button
                  type="button"
                  aria-pressed={focusedHub === hub}
                  onClick={() => onHubChange(focusedHub === hub ? null : hub)}
                >
                  {hub}
                </button>
              </th>
            ))}
          </tr>
          <tr>
            {hubs.map((hub) => (
              <SubHeaders key={`ladder-sub-${hub}`} t={t} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`ladder-row-${row.key}`} data-ladder-product={row.label}>
              <th scope="row" className="market-ladder-product" tabIndex={rowIndex === 0 ? 0 : -1}>{row.label}</th>
              {hubs.map((hub) => {
                const cell = row.cells[hub];
                const crossed = cell?.crossed ? " crossed" : "";
                return [
                  <td key={`${row.key}-${hub}-bv`} className="vol" tabIndex={-1}>{formatLadderVolume(cell?.bid ?? null)}</td>,
                  <td
                    key={`${row.key}-${hub}-b`}
                    className={`bid${crossed}${cell?.bid?.simulated ? " simulated" : ""}`}
                    title={sideTitle(cell?.bid ?? null)}
                    tabIndex={-1}
                  >
                    {formatLadderPrice(cell?.bid ?? null)}
                  </td>,
                  <td
                    key={`${row.key}-${hub}-o`}
                    className={`offer${crossed}${cell?.offer?.simulated ? " simulated" : ""}`}
                    title={sideTitle(cell?.offer ?? null)}
                    tabIndex={-1}
                  >
                    {formatLadderPrice(cell?.offer ?? null)}
                  </td>,
                  <td key={`${row.key}-${hub}-ov`} className="vol" tabIndex={-1}>{formatLadderVolume(cell?.offer ?? null)}</td>,
                ];
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="market-terminal-note">{t("ladder.note")}</p>
    </div>
  );
}

function SubHeaders({ t }: { t: Translate }) {
  return (
    <>
      <th className="vol">{t("ladder.bid_vol")}</th>
      <th className="bid">{t("ladder.bid")}</th>
      <th className="offer">{t("ladder.offer")}</th>
      <th className="vol">{t("ladder.offer_vol")}</th>
    </>
  );
}
