/**
 * Read-only presentation of a stored contract's declared payment terms.
 *
 * The component renders what the typed read established and nothing more: it resolves no
 * anchor, computes no date or amount and offers no edit or clear control. The persisted
 * declaration is evidence for the operator, while the settlement-frequency/lag controls above
 * remain the existing cash-timing estimate inputs (unchanged).
 */

import type { PaymentScheduleItemDTO } from "@/api/client";
import type { PaymentTermsReadState } from "@/app/model/contractPaymentTerms";
import { paymentTermVocabularyLabel } from "@/app/model/paymentTermsPresentation";

type Translate = (key: string) => string;

interface ContractPaymentTermsProps {
  /** The declaration read with this draft, or null when the draft is not a stored load. */
  read: PaymentTermsReadState | null;
  t: Translate;
}

function directionLabel(direction: "INFLOW" | "OUTFLOW", t: Translate): string {
  return direction === "INFLOW"
    ? t("contracts.payment_terms.direction.inflow")
    : t("contracts.payment_terms.direction.outflow");
}

/** One labelled fact row of the read-only list. */
function PaymentTermFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/**
 * One declared schedule item with its category, explicit flow direction, evidence and the
 * exactly-one date specification: a stated final payable date, or an unresolved anchored rule.
 */
function PaymentScheduleItem({ item, t }: { item: PaymentScheduleItemDTO; t: Translate }) {
  const specification = item.date_specification;
  return (
    <li className="contract-payment-item">
      {/*
        The header states the item's flow direction once; the fact list below does not repeat
        it. The translated label itself carries the meaning (money received / money paid out),
        so the direction stays readable and accessible without a duplicate row.
      */}
      <div className="contract-payment-item-head">
        <strong>{item.item_id}</strong>
        <span className="contract-payment-direction">
          {directionLabel(item.flow_direction, t)}
        </span>
      </div>
      <dl className="contract-payment-facts">
        <PaymentTermFact
          label={t("contracts.payment_terms.category")}
          value={paymentTermVocabularyLabel("cash_flow_category", item.cash_flow_category, t)}
        />
        <PaymentTermFact
          label={t("contracts.payment_terms.item_evidence")}
          value={item.source_reference}
        />
        {specification.kind === "EXPLICIT_DATE" ? (
          <>
            <PaymentTermFact
              label={t("contracts.payment_terms.date_kind")}
              value={t("contracts.payment_terms.date_kind.explicit")}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.final_payable_date")}
              value={specification.final_payable_date}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.specification_evidence")}
              value={specification.source_reference}
            />
          </>
        ) : (
          <>
            <PaymentTermFact
              label={t("contracts.payment_terms.date_kind")}
              value={t("contracts.payment_terms.date_kind.anchored")}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.anchor_event")}
              value={paymentTermVocabularyLabel("anchor_event", specification.anchor_event, t)}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.anchor_offset")}
              value={String(specification.anchor_offset_days)}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.offset_day_kind")}
              value={paymentTermVocabularyLabel("offset_day_kind", specification.offset_day_kind, t)}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.business_day_convention")}
              value={paymentTermVocabularyLabel(
                "business_day_convention",
                specification.business_day_convention,
                t,
              )}
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.calendar_reference")}
              value={
                specification.calendar_reference ??
                t("contracts.payment_terms.calendar_not_used")
              }
            />
            <PaymentTermFact
              label={t("contracts.payment_terms.specification_evidence")}
              value={specification.source_reference}
            />
          </>
        )}
      </dl>
    </li>
  );
}

export function ContractPaymentTerms({ read, t }: ContractPaymentTermsProps) {
  const hasAnchoredRule =
    read?.state === "declared" &&
    read.terms.items.some((item) => item.date_specification.kind === "ANCHORED_RULE");
  return (
    <section
      className="contract-payment-terms"
      aria-label={t("contracts.payment_terms.title")}
      data-payment-terms-state={read?.state ?? "draft"}
    >
      <div className="section-heading">
        <span className="eyebrow">{t("contracts.payment_terms.title")}</span>
        <strong>
          {read?.state === "declared"
            ? t("contracts.payment_terms.declared")
            : t("contracts.payment_terms.read_only")}
        </strong>
      </div>

      {read === null && (
        <p className="contract-support-note">{t("contracts.payment_terms.draft")}</p>
      )}
      {read?.state === "not_declared" && (
        <p className="contract-support-note">{t("contracts.payment_terms.not_declared")}</p>
      )}
      {read?.state === "unavailable" && (
        <p className="contract-support-note">{t("contracts.payment_terms.unavailable")}</p>
      )}
      {read?.state === "malformed" && (
        <div
          className="runtime-blocker-list compact"
          role="status"
          data-payment-terms-malformed={read.reason}
        >
          <strong>{t("contracts.payment_terms.malformed_title")}</strong>
          <span>{t("contracts.payment_terms.malformed")}</span>
        </div>
      )}

      {read?.state === "declared" && (
        <>
          <div className="contract-definition-list compact">
            <div>
              <span>{t("contracts.payment_terms.quantity_basis")}</span>
              <strong>{read.terms.quantity_basis_reference}</strong>
            </div>
            <div>
              <span>{t("contracts.payment_terms.items")}</span>
              <strong>{String(read.terms.items.length)}</strong>
            </div>
            <div>
              <span>{t("contracts.payment_terms.schema_version")}</span>
              <strong>{read.terms.schema_version}</strong>
            </div>
          </div>
          <ul className="contract-payment-schedule">
            {read.terms.items.map((item) => (
              <PaymentScheduleItem key={item.item_id} item={item} t={t} />
            ))}
          </ul>
          {hasAnchoredRule && (
            <p className="contract-model-boundary">
              {t("contracts.payment_terms.unresolved_warning")}
            </p>
          )}
        </>
      )}

      <p className="contract-support-note">{t("contracts.payment_terms.estimate_distinction")}</p>
    </section>
  );
}
