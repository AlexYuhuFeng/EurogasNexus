/**
 * TAR-2: the sources of one figure in the order in force, numbered, the one used marked and
 * each one skipped with the reason (not held, stale, not covering, not configured...).
 */
import type { SourceTierDTO } from "@/api/client";
import { orderOrigin, sourceSteps } from "@/app/model/capacityCostModel";
import { StatusBadge } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function labelOr(t: Translate, key: string, raw: string): string {
  const label = t(key);
  return label === key ? raw : label;
}

export function originText(orderSource: string, t: Translate): string {
  const origin = orderOrigin(orderSource);
  return t(`sourceOrder.origin.${origin.key}`, { setting: origin.setting ?? "" });
}

export function SourceSteps({
  sources,
  orderSource,
  t,
}: {
  sources: readonly SourceTierDTO[] | undefined;
  orderSource?: string;
  t: Translate;
}) {
  const steps = sourceSteps(sources);
  if (steps.length === 0) return null;
  return (
    <section className="source-steps" aria-label={t("sourceOrder.title")}>
      <h4>
        {t("sourceOrder.title")}
        {orderSource ? (
          <span className="source-steps-origin">
            {originText(orderSource, t)}
          </span>
        ) : null}
      </h4>
      <ol>
        {steps.map((step) => (
          <li key={step.tier} data-used={step.used ? "true" : undefined}>
            <span className="source-steps-position">{step.position}</span>
            <span className="source-steps-label">{labelOr(t, `sourceOrder.tier.${step.tier}`, step.label)}</span>
            <StatusBadge tone={step.used ? "ok" : "neutral"} title={step.note ?? undefined}>
              {labelOr(t, `sourceOrder.reason.${step.reason}`, step.reason)}
            </StatusBadge>
          </li>
        ))}
      </ol>
    </section>
  );
}
