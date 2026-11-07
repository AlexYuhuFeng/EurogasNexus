import { SUPPORTED_HUB_IDS } from "@/app/context";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The gas day, delivery product and hub a trading page reads, set on that page.
 *
 * These used to sit in the top bar on every page; they only change what the trading pages
 * show, so they now live in those pages' context line. The selection is still one shared
 * context: changing it on Market carries to Portfolio and Decision Center.
 */
export function TradingContextControls({
  gasDay,
  deliveryProduct,
  hubId,
  t,
  onGasDayChange,
  onDeliveryProductChange,
  onHubChange,
}: {
  gasDay: string;
  deliveryProduct: string;
  hubId: string | null;
  t: Translate;
  onGasDayChange: (value: string) => void;
  onDeliveryProductChange: (value: string) => void;
  onHubChange: (value: string | null) => void;
}) {
  return (
    <div
      className="trading-context-controls"
      role="group"
      aria-label={t("context.title")}
      // The Active Context in machine-readable form, for the acceptance sweep's reads.
      data-context-gas-day={gasDay}
      data-context-product={deliveryProduct}
      data-context-hub={hubId ?? ""}
    >
      <label>
        <span>{t("context.gas_day")}</span>
        <input type="date" value={gasDay} onChange={(event) => onGasDayChange(event.target.value)} />
      </label>
      <label>
        <span>{t("context.product")}</span>
        <select value={deliveryProduct} onChange={(event) => onDeliveryProductChange(event.target.value)}>
          <option value="all">{t("context.all_products")}</option>
          <option value="day-ahead">{t("context.day_ahead")}</option>
          <option value="within-day">{t("context.within_day")}</option>
          <option value="month-ahead">{t("context.month_ahead")}</option>
        </select>
      </label>
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
) {
  return (
    <TradingContextControls
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
