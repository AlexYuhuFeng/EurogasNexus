import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SUPPORTED_HUB_IDS } from "@/app/context";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { formatGasDay } from "@/app/time/timeFormat";
import { Sheet, PeriodPicker } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The gas day, delivery product and hub a trading page reads, set on that page.
 *
 * These used to sit in the top bar on every page; they only change what the trading pages
 * show, so they now live in those pages' context line. The selection is still one shared
 * context: changing it on Market carries to Portfolio and Decision Center.
 *
 * One structure in every language: gas day, product, hub, in that order, each a label above or
 * beside its control. At phone width the three collapse into one summary button
 * ("16 Nov · All products · All hubs") that opens a sheet with the same three controls, so the
 * page's context line stays one row (UX_REFERENCE "Phone rules").
 */
const PRODUCT_LABEL_KEYS: Record<string, string> = {
  all: "context.all_products",
  "day-ahead": "context.day_ahead",
  "within-day": "context.within_day",
  "month-ahead": "context.month_ahead",
};

export function TradingContextControls({
  gasDay,
  deliveryProduct,
  hubId,
  t,
  onGasDayChange,
  onDeliveryProductChange,
  onHubChange,
  showProduct = true,
  summaryOnly = false,
}: {
  /**
   * One quiet summary ("19 Nov · All products · All hubs") that opens the fields in a sheet, on
   * every width: for pages where the context only refines what is shown (Book, Deals), so the page
   * reads as one line like Today's.
   */
  summaryOnly?: boolean;
  /** False where the page has its own product selector (Prices' board tenors). */
  showProduct?: boolean;
  gasDay: string;
  deliveryProduct: string;
  hubId: string | null;
  t: Translate;
  onGasDayChange: (value: string) => void;
  onDeliveryProductChange: (value: string) => void;
  onHubChange: (value: string | null) => void;
}) {
  const compact = useCompactWidth() || summaryOnly;
  const [sheetOpen, setSheetOpen] = useState(false);
  const { i18n } = useTranslation();
  const language = i18n.language;
  const summary = [
    formatGasDay(gasDay, language),
    ...(showProduct ? [t(PRODUCT_LABEL_KEYS[deliveryProduct] ?? "context.all_products")] : []),
    hubId ?? t("context.no_hub_focus"),
  ].join(" · ");
  const fields = (
    <>
      <label>
        <span>{t("context.gas_day")}</span>
        <PeriodPicker label={t("context.gas_day")} value={gasDay} onChange={onGasDayChange} />
      </label>
      {showProduct && <label>
        <span>{t("context.product")}</span>
        <select value={deliveryProduct} onChange={(event) => onDeliveryProductChange(event.target.value)}>
          <option value="all">{t("context.all_products")}</option>
          <option value="day-ahead">{t("context.day_ahead")}</option>
          <option value="within-day">{t("context.within_day")}</option>
          <option value="month-ahead">{t("context.month_ahead")}</option>
        </select>
      </label>}
      <label>
        <span>{t("context.hub")}</span>
        <select
          aria-label={t("context.hub")}
          value={hubId ?? ""}
          onChange={(event) => onHubChange(event.target.value || null)}
        >
          <option value="">{t("context.no_hub_focus")}</option>
          {SUPPORTED_HUB_IDS.map((hub) => (
            <option key={hub} value={hub}>{hub}</option>
          ))}
        </select>
      </label>
    </>
  );
  return (
    <div
      className={compact ? "trading-context-controls is-compact" : "trading-context-controls"}
      role="group"
      aria-label={t("context.title")}
      // The Active Context in machine-readable form, for the acceptance sweep's reads.
      data-context-gas-day={gasDay}
      data-context-product={deliveryProduct}
      data-context-hub={hubId ?? ""}
    >
      {compact ? (
        <>
          <button
            type="button"
            className="trading-context-summary"
            aria-haspopup="dialog"
            aria-expanded={sheetOpen}
            title={`${t("context.title")}: ${summary}`}
            onClick={() => setSheetOpen(true)}
          >
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16"><path d="M2 4h12M4 8h8M6 12h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            <span className="trading-context-summary-text">{summary}</span>
          </button>
          <Sheet
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            side="bottom"
            title={t("context.title")}
            closeLabel={t("context.done")}
            className="trading-context-sheet"
            id="trading-context"
          >
            <div className="trading-context-sheet-fields">{fields}</div>
          </Sheet>
        </>
      ) : (
        fields
      )}
    </div>
  );
}

/** The controls for a page, from the controller's shared trading context. */
export function tradingContextControlsFor(
  traderContext: {
    gasDay: string;
    deliveryProduct: string;
    hubId: string | null;
    setGasDay: (value: string) => void;
    setDeliveryProduct: (value: string) => void;
    setHubId: (value: string | null) => void;
  },
  t: Translate,
  { product = true, summary = false }: { product?: boolean; summary?: boolean } = {},
) {
  return (
    <TradingContextControls
      showProduct={product}
      summaryOnly={summary}
      gasDay={traderContext.gasDay}
      deliveryProduct={traderContext.deliveryProduct}
      hubId={traderContext.hubId}
      t={t}
      onGasDayChange={traderContext.setGasDay}
      onDeliveryProductChange={traderContext.setDeliveryProduct}
      onHubChange={traderContext.setHubId}
    />
  );
}
