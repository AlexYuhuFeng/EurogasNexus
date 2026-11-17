/**
 * The Connectors view of the source registry (#26, #33, docs/product/CONNECTORS.md C3).
 *
 * Every registered source falls in exactly one group with one status word and one action:
 * - `attention`: something that was set up is not working (a failure, a stale feed, a disabled
 *   or lost credential, a scheduled feed that produces nothing, or no runtime store);
 * - `connected`: delivering data, or a model service with its credential in place;
 * - a `manual_register` (TSO tariffs, DATA-05) is a register an operator keeps: shown as
 *   such, never stale and never in `attention`;
 * - `available`: offered but never set up. An optional provider nobody connected is not an
 *   alarm, so it never counts as needing attention.
 * Grouping is a view: it grants nothing, and the backend decides every read.
 */
export type ConnectorGroup = "attention" | "connected" | "available";
export type ConnectorAction = "fix" | "open" | "connect" | "import" | "configure" | "set_up" | "approve";

export interface ConnectorSourceFacts {
  readonly source_id: string;
  readonly connectivity_status: string;
  readonly operational_status: string;
  readonly integration?: "api" | "file_import" | "template" | "model_service" | "manual_register";
  readonly credential_state: string;
  readonly scheduler_enabled: boolean;
  readonly last_success_at_utc: string | null;
  readonly effective_last_success_at_utc: string | null;
  readonly consecutive_failures: number;
  /** Public-source approval (ENTSOG, GIE): the gate reads nothing until an administrator approves. */
  readonly approval?: { readonly required: boolean; readonly state: string };
}

export interface ConnectorCard {
  readonly sourceId: string;
  readonly group: ConnectorGroup;
  /** Translation key of the one status word. */
  readonly statusKey: string;
  readonly action: ConnectorAction;
}

export function connectorCard(source: ConnectorSourceFacts): ConnectorCard {
  const sourceId = source.source_id;
  const status = source.connectivity_status;
  const everWorked = Boolean(source.last_success_at_utc || source.effective_last_success_at_utc);
  const setUp = everWorked || source.scheduler_enabled;
  const attention = (statusKey: string): ConnectorCard => ({ sourceId, group: "attention", statusKey, action: "fix" });

  if (status === "runtime_unconfigured") return attention("connectors.status.no_store");
  // A public source the ingestion gate holds back until an administrator approves it for the firm
  // (ENTSOG, GIE): never a silent gap, so it needs attention with the one action that opens it.
  const approval = source.approval;
  if (approval?.required) {
    if (approval.state === "not_approved") {
      return { sourceId, group: "attention", statusKey: "connectors.status.not_approved", action: "approve" };
    }
    if (approval.state === "approved_waiting_for_key") {
      return { sourceId, group: "attention", statusKey: "connectors.status.approved_waiting_for_key", action: "connect" };
    }
    if (approval.state === "failing") return attention("connectors.status.failing");
    if (approval.state === "approved") {
      return { sourceId, group: "connected", statusKey: "connectors.status.approved", action: "open" };
    }
  }
  // A TSO tariff register an operator keeps (DATA-05): not a feed, never stale, never an alarm.
  if (source.integration === "manual_register" || status === "manual_register") {
    return {
      sourceId,
      group: source.operational_status === "manual_register" && everWorked ? "connected" : "available",
      statusKey: "connectors.status.manual_register",
      action: "open",
    };
  }
  if (status === "failed" || source.consecutive_failures > 0) return attention("connectors.status.failing");
  if (status === "stale") return attention("connectors.status.stale");
  if (status === "credential_disabled") return attention("connectors.status.key_disabled");
  if (status === "active") {
    return {
      sourceId,
      group: "connected",
      statusKey: source.operational_status === "active_simulated" ? "connectors.status.simulated" : "connectors.status.live",
      action: "open",
    };
  }
  if (status === "configured") return { sourceId, group: "connected", statusKey: "connectors.status.configured", action: "open" };
  if (status === "needs_credential" && setUp) return attention("connectors.status.key_missing");
  if (status === "no_records" && source.scheduler_enabled) return attention("connectors.status.no_data");

  // Offered, never set up: what it takes to start.
  if (source.integration === "template") {
    return { sourceId, group: "available", statusKey: "connectors.status.template", action: "configure" };
  }
  if (source.integration === "file_import") {
    return { sourceId, group: "available", statusKey: "connectors.status.import", action: "import" };
  }
  if (status === "needs_credential") {
    return { sourceId, group: "available", statusKey: "connectors.status.needs_key", action: "connect" };
  }
  return { sourceId, group: "available", statusKey: "connectors.status.not_scheduled", action: "set_up" };
}

export const CONNECTOR_GROUPS: readonly ConnectorGroup[] = ["attention", "connected", "available"];

export function groupConnectors<T extends ConnectorSourceFacts>(
  sources: readonly T[],
): Record<ConnectorGroup, Array<{ source: T; card: ConnectorCard }>> {
  const groups: Record<ConnectorGroup, Array<{ source: T; card: ConnectorCard }>> = {
    attention: [],
    connected: [],
    available: [],
  };
  for (const source of sources) {
    const card = connectorCard(source);
    groups[card.group].push({ source, card });
  }
  return groups;
}
