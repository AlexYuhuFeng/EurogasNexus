/**
 * Synthetic LNG economics-only fixtures.
 *
 * The values are the documented synthetic golden, not market data and not a physical scenario:
 * purchased 100 MWh at EUR20/MWh, delivered 90 MWh sold at EUR30/MWh, one invoiced EUR150 cost,
 * and two explicit stages (100 -> 96 with consumed 3/loss 1, then 96 -> 90 with consumed 4/loss 2).
 * Margin 550.0000, NPV 482.5000, consumed 7, physical loss 3, total reduction 10.
 */

import type {
  LngEconomicsOnlyMetaDTO,
  LngEconomicsOnlyResultDTO,
} from "../../src/api/client.ts";
import type { LngEconomicsDraft } from "../../src/app/model/lngEconomicsModel.ts";

export const GOLDEN_VALUATION_DATE = "2026-09-29";
export const GOLDEN_SALE_DATE = "2026-11-30";
export const GOLDEN_PURCHASE_SOURCE = "synthetic-test-input:purchase-price-1";
export const GOLDEN_SALE_SOURCE = "synthetic-test-input:sale-price-1";
export const GOLDEN_COST_SOURCE = "synthetic-test-input:invoiced-cost-1";
export const GOLDEN_DF_SOURCE = "synthetic-test-input:df-1";
export const GOLDEN_DF_CURVE = "synthetic-test-curve:eur-flat";
export const GOLDEN_STAGE_1_SOURCE = "synthetic-test-input:stage-shipping-1";
export const GOLDEN_STAGE_2_SOURCE = "synthetic-test-input:stage-regas-1";
export const GOLDEN_SCOPE =
  "Synthetic scope: the DES purchase price covers the cargo only; regas is invoiced separately below.";

export function goldenDraft(): LngEconomicsDraft {
  return {
    contractId: "contract-synthetic-lng-1",
    cargoId: "cargo-synthetic-1",
    terminalId: "terminal-synthetic-regas-1",
    resourceId: "resource-synthetic-supply-1",
    valuationDate: GOLDEN_VALUATION_DATE,
    reportingCurrency: "EUR",
    energyBasisReference: "synthetic-basis:gcV-energy-mwh",
    energyUnit: "MWh",
    purchasedEnergyMwh: "100",
    deliveredEnergyMwh: "90",
    purchaseUnitPriceEurPerMwh: "20",
    saleUnitPriceEurPerMwh: "30",
    purchasePriceSourceReference: GOLDEN_PURCHASE_SOURCE,
    salePriceSourceReference: GOLDEN_SALE_SOURCE,
    purchaseBasis: "DES",
    purchaseIncludedCostItems: "",
    costScopeStatement: GOLDEN_SCOPE,
    purchasePaymentDate: GOLDEN_VALUATION_DATE,
    salePaymentDate: GOLDEN_SALE_DATE,
    downstreamCosts: [
      {
        costId: "regas-1",
        category: "regas",
        amountEur: "150",
        paymentDate: GOLDEN_VALUATION_DATE,
        sourceReference: GOLDEN_COST_SOURCE,
        chargeBasis: "invoiced_cash",
      },
    ],
    energyStages: [
      {
        stageId: "shipping-1",
        kind: "shipping",
        inputEnergyMwh: "100",
        outputEnergyMwh: "96",
        consumedEnergyMwh: "3",
        physicalLossEnergyMwh: "1",
        sourceReferences: GOLDEN_STAGE_1_SOURCE,
      },
      {
        stageId: "regas-1",
        kind: "regasification",
        inputEnergyMwh: "96",
        outputEnergyMwh: "90",
        consumedEnergyMwh: "4",
        physicalLossEnergyMwh: "2",
        sourceReferences: GOLDEN_STAGE_2_SOURCE,
      },
    ],
    discountFactors: [
      {
        paymentDate: GOLDEN_VALUATION_DATE,
        factor: "1",
        curveReference: GOLDEN_DF_CURVE,
        sourceReference: GOLDEN_DF_SOURCE,
        asOf: GOLDEN_VALUATION_DATE,
      },
      {
        paymentDate: GOLDEN_SALE_DATE,
        factor: "0.975",
        curveReference: GOLDEN_DF_CURVE,
        sourceReference: GOLDEN_DF_SOURCE,
        asOf: GOLDEN_VALUATION_DATE,
      },
    ],
  };
}

export function goldenResult(): LngEconomicsOnlyResultDTO {
  return {
    research_only: true,
    human_review_required: true,
    model_version: "lng-economics-only/v1",
    action: "compute_cash_flow",
    contract_id: "contract-synthetic-lng-1",
    cargo_id: "cargo-synthetic-1",
    terminal_id: "terminal-synthetic-regas-1",
    resource_id: "resource-synthetic-supply-1",
    valuation_date: GOLDEN_VALUATION_DATE,
    reporting_currency: "EUR",
    energy_basis_reference: "synthetic-basis:gcV-energy-mwh",
    energy_unit: "MWh",
    purchased_energy_mwh: "100",
    delivered_energy_mwh: "90",
    total_consumed_energy_mwh: "7",
    physical_loss_energy_mwh: "3",
    total_reduction_energy_mwh: "10",
    purchase_basis: "DES",
    purchase_included_cost_items: [],
    cost_scope_statement: GOLDEN_SCOPE,
    purchase_unit_price_eur_per_mwh: "20",
    sale_unit_price_eur_per_mwh: "30",
    unit_netback_eur_per_purchased_mwh: "25.5000",
    sale_basis_eur_per_delivered_mwh: "30.0000",
    purchase_outlay_eur: "2000.0000",
    sale_proceeds_eur: "2700.0000",
    total_downstream_costs_eur: "150.0000",
    cargo_margin_eur: "550.0000",
    margin_reconciliation_gap_eur: "0.0000",
    margin_reconciliation_tolerance_eur: "0.0052",
    net_present_value_eur: "482.5000",
    total_undiscounted_cash_eur: "550.0000",
    cash_valuation: {
      model_version: "lng-cargo-cash-valuation/v1",
      contract_id: "contract-synthetic-lng-1",
      cargo_id: "cargo-synthetic-1",
      terminal_id: "terminal-synthetic-regas-1",
      resource_id: "resource-synthetic-supply-1",
      valuation_date: GOLDEN_VALUATION_DATE,
      reporting_currency: "EUR",
      leg_valuations: [
        {
          leg_id: "cargo-purchase",
          category: "cargo_purchase",
          payment_date: GOLDEN_VALUATION_DATE,
          currency: "EUR",
          signed_amount: "-2000.0000",
          cash_amount_reporting_ccy: "-2000.0000",
          present_value_reporting_ccy: "-2000.0000",
          discount_factor: "1",
          discount_curve_reference: GOLDEN_DF_CURVE,
          discount_source_reference: GOLDEN_DF_SOURCE,
          discount_as_of: GOLDEN_VALUATION_DATE,
          source_reference: GOLDEN_PURCHASE_SOURCE,
          fx_rate_reporting_per_leg: "1",
          fx_source_reference: "",
          fx_as_of: null,
          description: "",
        },
        {
          leg_id: "cargo-sale",
          category: "cargo_sale",
          payment_date: GOLDEN_SALE_DATE,
          currency: "EUR",
          signed_amount: "2700.0000",
          cash_amount_reporting_ccy: "2700.0000",
          present_value_reporting_ccy: "2632.5000",
          discount_factor: "0.975",
          discount_curve_reference: GOLDEN_DF_CURVE,
          discount_source_reference: GOLDEN_DF_SOURCE,
          discount_as_of: GOLDEN_VALUATION_DATE,
          source_reference: GOLDEN_SALE_SOURCE,
          fx_rate_reporting_per_leg: "1",
          fx_source_reference: "",
          fx_as_of: null,
          description: "",
        },
        {
          leg_id: "downstream-cost:regas-1",
          category: "regas",
          payment_date: GOLDEN_VALUATION_DATE,
          currency: "EUR",
          signed_amount: "-150.0000",
          cash_amount_reporting_ccy: "-150.0000",
          present_value_reporting_ccy: "-150.0000",
          discount_factor: "1",
          discount_curve_reference: GOLDEN_DF_CURVE,
          discount_source_reference: GOLDEN_DF_SOURCE,
          discount_as_of: GOLDEN_VALUATION_DATE,
          source_reference: GOLDEN_COST_SOURCE,
          fx_rate_reporting_per_leg: "1",
          fx_source_reference: "",
          fx_as_of: null,
          description: "",
        },
      ],
      total_undiscounted_cash_reporting_ccy: "550.0000",
      net_present_value_reporting_ccy: "482.5000",
      assumptions: [
        "Signed legs: inflow positive, outflow negative; each leg is counted exactly once.",
      ],
      warnings: ["NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN"],
      source_references: [
        GOLDEN_COST_SOURCE,
        GOLDEN_DF_SOURCE,
        GOLDEN_PURCHASE_SOURCE,
        GOLDEN_SALE_SOURCE,
        GOLDEN_STAGE_1_SOURCE,
        GOLDEN_STAGE_2_SOURCE,
      ],
      lineage: ["lng-cargo-cash-valuation", "lng-cargo-cash-valuation/v1"],
      research_only: true,
      human_review_required: true,
    },
    energy_balance: {
      model_version: "lng-energy-balance/v1",
      purchased_energy_mwh: "100",
      delivered_energy_mwh: "90",
      energy_basis_reference: "synthetic-basis:gcV-energy-mwh",
      energy_unit: "MWh",
      total_consumed_energy_mwh: "7",
      physical_loss_energy_mwh: "3",
      total_reduction_energy_mwh: "10",
      stage_count: 2,
      stages: [
        {
          stage_id: "shipping-1",
          kind: "shipping",
          input_energy_mwh: "100",
          output_energy_mwh: "96",
          consumed_energy_mwh: "3",
          physical_loss_energy_mwh: "1",
          source_references: [GOLDEN_STAGE_1_SOURCE],
        },
        {
          stage_id: "regas-1",
          kind: "regasification",
          input_energy_mwh: "96",
          output_energy_mwh: "90",
          consumed_energy_mwh: "4",
          physical_loss_energy_mwh: "2",
          source_references: [GOLDEN_STAGE_2_SOURCE],
        },
      ],
      warnings: [
        "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
        "EXPLICIT_ENERGY_STAGES_ONLY_NO_VOLUME_OR_FX_CONVERSION",
        "CONSUMED_ENERGY_AND_PHYSICAL_LOSS_DISCLOSED_SEPARATELY_NOT_MONETIZED",
      ],
      source_references: [GOLDEN_STAGE_1_SOURCE, GOLDEN_STAGE_2_SOURCE],
      research_only: true,
      human_review_required: true,
    },
    physical_readiness: "NOT_ASSESSED",
    readiness_assessed: false,
    assumptions: [
      "purchase_outlay = purchased_energy_mwh x purchase_unit_price; sale_proceeds = delivered_energy_mwh x sale_unit_price.",
      "The energy chain is explicit and exact: every stage satisfies input = output + consumed + physical loss, adjacent stages match exactly.",
    ],
    warnings: [
      "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
      "NO_TRADE_EXECUTION_NOMINATION_OR_SETTLEMENT",
      "EUR_ONLY_NO_FX_CONVERSION_PERFORMED",
      "PHYSICAL_READINESS_NOT_ASSESSED",
      "PROFITABLE_ECONOMICS_IS_NOT_DELIVERY_FEASIBILITY_TERMINAL_SLOT_STORAGE_RIGHTS_OR_NOMINATION_AUTHORITY",
      "IN_KIND_ENERGY_CONSUMPTION_AND_PHYSICAL_LOSS_ARE_NOT_MONETIZED",
      "TOTAL_REDUCTION_DISCLOSED_AS_CONSUMED_PHYSICAL_LOSS_NOT_ADDITIONALLY_MONETIZED",
    ],
    source_references: [
      GOLDEN_COST_SOURCE,
      GOLDEN_DF_SOURCE,
      GOLDEN_PURCHASE_SOURCE,
      GOLDEN_SALE_SOURCE,
      GOLDEN_STAGE_1_SOURCE,
      GOLDEN_STAGE_2_SOURCE,
    ],
    lineage: [
      "lng-economics-only",
      "lng-economics-only/v1",
      "lng-energy-balance",
      "lng-energy-balance/v1",
      "lng-cargo-cash-valuation/v1",
    ],
  };
}

export function goldenMeta(): LngEconomicsOnlyMetaDTO {
  return {
    research_only: true,
    human_review_required: true,
    decision_context: "SANDBOX_SCENARIO",
    caller_supplied: true,
    references_verified: false,
    physical_readiness: "NOT_ASSESSED",
    readiness_assessed: false,
    customer_approval: false,
    source_references: goldenResult().source_references,
    warnings: goldenResult().warnings,
  };
}
