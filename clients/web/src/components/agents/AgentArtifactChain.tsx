import type { ReactNode } from "react";
import type { AgentArtifactType, AgentReplayDTO } from "@/api/client";
import {
  agentChallengeView,
  agentChainView,
  agentFindingRows,
  agentPlanView,
  agentReviewPackView,
  agentStrategyIRView,
  agentValidationView,
  agentValueList,
  formatAgentCount,
  formatAgentTimestamp,
  type AgentValueList,
} from "@/app/model/agentReplayModel";
import { MetricStrip, PanelHeader, StatusBadge } from "@/components/ui";

type Translate = (key: string) => string;

interface AgentArtifactChainProps {
  replay: AgentReplayDTO;
  t: Translate;
}

/** One fact line of an artifact envelope: label plus persisted value. */
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="agents-fact">
      <span className="agents-fact-key">{label}</span>
      <span className="agents-fact-value">{children}</span>
    </div>
  );
}

/** Bounded persisted value list with an explicit remainder count. */
function ValueListText({
  list,
  emptyLabel,
  moreLabel,
}: {
  list: AgentValueList;
  emptyLabel: string;
  moreLabel: string;
}) {
  if (list.total === 0) return <span className="muted">{emptyLabel}</span>;
  return (
    <>
      <span>{list.values.join(", ")}</span>
      {list.remaining > 0 && (
        <span className="muted">
          {" "}
          +{list.remaining} {moreLabel}
        </span>
      )}
    </>
  );
}

/** Compact key/value rows of one persisted nested record. */
function FieldRows({ rows, t }: { rows: Array<{ key: string; value: string }>; t: Translate }) {
  if (rows.length === 0) return <span className="muted">{t("agents.value_absent")}</span>;
  return (
    <ul className="agents-payload-list">
      {rows.map((row) => (
        <li key={row.key}>
          <code>{row.key}</code> {row.value}
        </li>
      ))}
    </ul>
  );
}

/** Payload of one chain artifact, rendered compactly by artifact kind. */
function ArtifactPayload({
  envelope,
  t,
}: {
  envelope: AgentReplayDTO["artifacts"][AgentArtifactType];
  t: Translate;
}) {
  const more = t("agents.more_values");
  const absent = t("agents.value_absent");

  if (envelope.artifact_type === "research_plan") {
    const plan = agentPlanView(envelope.payload);
    if (!plan) return null;
    return (
      <div className="agents-payload">
        <Fact label={t("agents.plan.objective")}>{plan.objective}</Fact>
        <Fact label={t("agents.plan.question")}>{plan.question}</Fact>
        <Fact label={t("agents.plan.status")}>
          <StatusBadge variant="source" status={plan.status.toLowerCase() || "unknown"}>
            {plan.status || absent}
          </StatusBadge>
        </Fact>
        <Fact label={t("agents.plan.product")}>{plan.product || absent}</Fact>
        <Fact label={t("agents.plan.horizon")}>{plan.horizon || absent}</Fact>
        <Fact label={t("agents.plan.scope")}>
          <ValueListText list={plan.marketScope} emptyLabel={absent} moreLabel={more} />
        </Fact>
        <Fact label={t("agents.plan.entities")}>
          <ValueListText list={plan.entities} emptyLabel={absent} moreLabel={more} />
        </Fact>
        <Fact label={t("agents.plan.hypotheses")}>
          <ValueListText list={plan.hypotheses} emptyLabel={absent} moreLabel={more} />
        </Fact>
        <Fact label={t("agents.plan.strategy_allowed")}>
          {plan.strategyGenerationAllowed ? t("agents.yes") : t("agents.no")}
        </Fact>
        <Fact label={t("agents.plan.stopping_conditions")}>
          <ValueListText list={plan.stoppingConditions} emptyLabel={absent} moreLabel={more} />
        </Fact>
        <Fact label={t("agents.plan.analyses")}>
          {plan.analyses.length === 0 ? (
            <span className="muted">{absent}</span>
          ) : (
            <ul className="agents-payload-list">
              {plan.analyses.map((analysis) => (
                <li key={analysis.analysisId || analysis.analysisType}>
                  <code>{analysis.analysisType}</code> {analysis.analysisId}
                  {analysis.inputSeries.total > 0 && (
                    <span className="muted"> — {analysis.inputSeries.values.join(", ")}</span>
                  )}
                  {analysis.parameters !== "" && <span className="muted"> ({analysis.parameters})</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.plan.required_evidence")}>
          {plan.evidence.length === 0 ? (
            <span className="muted">{absent}</span>
          ) : (
            <ul className="agents-payload-list">
              {plan.evidence.map((requirement) => (
                <li key={requirement.seriesId}>
                  <code>{requirement.seriesId}</code>{" "}
                  {requirement.required ? t("agents.plan.evidence_required") : t("agents.plan.evidence_optional")}
                  {requirement.maxSourceAgeSeconds !== "" && (
                    <span className="muted"> · {requirement.maxSourceAgeSeconds}s</span>
                  )}
                  {requirement.temporalIntegrityMin !== "" && (
                    <span className="muted"> · {requirement.temporalIntegrityMin}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.plan.data_quality")}>
          <FieldRows rows={plan.dataQuality} t={t} />
        </Fact>
        <Fact label={t("agents.plan.statistical")}>
          <FieldRows rows={plan.statistical} t={t} />
        </Fact>
      </div>
    );
  }

  if (envelope.artifact_type === "findings") {
    const findings = agentFindingRows(envelope.payload);
    return (
      <div className="agents-payload">
        <Fact label={t("agents.findings.count")}>{formatAgentCount(findings.length)}</Fact>
        {findings.length === 0 ? (
          <p className="muted">{absent}</p>
        ) : (
          <ul className="agents-payload-list agents-findings-list">
            {findings.map((finding) => (
              <li key={finding.findingId}>
                <div className="agents-finding-line">
                  <code>{finding.findingId}</code>
                  <span>{finding.question || absent}</span>
                  <StatusBadge variant="source" status={finding.qualityState.toLowerCase() || "unknown"}>
                    {finding.qualityState || absent}
                  </StatusBadge>
                </div>
                <div className="agents-finding-line muted">
                  <span>
                    {t("agents.findings.statistic")}: {finding.statistic || absent}
                  </span>
                  <span>
                    {t("agents.findings.value")}: {finding.value || absent}
                    {finding.unit !== "" && ` ${finding.unit}`}
                  </span>
                  <span>
                    {t("agents.findings.sample")}: {finding.sample || absent}
                  </span>
                  <span>
                    {t("agents.findings.period")}: {finding.period || absent}
                  </span>
                  <span>
                    {t("agents.created_at")}: {finding.createdAt || absent}
                  </span>
                </div>
                <div className="agents-finding-line muted">
                  <span>
                    {t("agents.findings.methodology")}: {finding.methodology || absent}
                  </span>
                </div>
                <div className="agents-finding-line muted">
                  <span>
                    {t("agents.findings.limitations")}:{" "}
                    <ValueListText list={finding.limitations} emptyLabel={absent} moreLabel={more} />
                  </span>
                  <span>
                    {t("agents.findings.evidence")}:{" "}
                    <ValueListText list={finding.evidence} emptyLabel={absent} moreLabel={more} />
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (envelope.artifact_type === "strategy_ir") {
    const strategy = agentStrategyIRView(envelope.payload);
    if (!strategy) return null;
    return (
      <div className="agents-payload">
        <Fact label={t("agents.strategy_ir.schema_version")}>{strategy.schemaVersion || absent}</Fact>
        <Fact label={t("agents.strategy_ir.hypothesis")}>{strategy.hypothesis}</Fact>
        <Fact label={t("agents.strategy_ir.universe")}>{strategy.universe || absent}</Fact>
        <Fact label={t("agents.strategy_ir.sizing")}>{strategy.sizing || absent}</Fact>
        <Fact label={t("agents.strategy_ir.components")}>
          {strategy.components.length === 0 ? (
            <span className="muted">{absent}</span>
          ) : (
            <ul className="agents-payload-list">
              {strategy.components.map((component) => (
                <li key={component.componentId}>
                  <code>{component.componentId}</code> {component.componentType}
                  {component.weight !== "" && <span className="muted"> · {component.weight}</span>}
                  {component.conditions !== "" && <span className="muted"> · {component.conditions}</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.strategy_ir.parameters")}>
          {strategy.parameters.length === 0 ? (
            <span className="muted">{absent}</span>
          ) : (
            <ul className="agents-payload-list">
              {strategy.parameters.map((parameter) => (
                <li key={parameter.parameterId}>
                  <code>{parameter.parameterId}</code> {parameter.parameterType}
                  {parameter.unit !== "" && <span className="muted"> {parameter.unit}</span>}
                  {parameter.defaultValue !== "" && (
                    <span className="muted"> · {parameter.defaultValue}</span>
                  )}
                  {parameter.bounds !== "" && <span className="muted"> · {parameter.bounds}</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.strategy_ir.risk_controls")}>
          <FieldRows rows={strategy.riskControls} t={t} />
        </Fact>
        <Fact label={t("agents.strategy_ir.economic_assumptions")}>
          <FieldRows rows={strategy.economicAssumptions} t={t} />
        </Fact>
        <Fact label={t("agents.strategy_ir.data_requirements")}>
          <FieldRows rows={strategy.dataRequirements} t={t} />
        </Fact>
        <Fact label={t("agents.strategy_ir.evaluation_windows")}>
          <FieldRows rows={strategy.evaluationWindows} t={t} />
        </Fact>
      </div>
    );
  }

  if (envelope.artifact_type === "validation") {
    const validation = agentValidationView(envelope.payload);
    if (!validation) return null;
    return (
      <div className="agents-payload">
        <Fact label={t("agents.validation.plan_id")}>{validation.planId || absent}</Fact>
        <Fact label={t("agents.validation.plan_status")}>{validation.planStatus || absent}</Fact>
        <Fact label={t("agents.validation.plan_source")}>{validation.planValidationSource || absent}</Fact>
        <Fact label={t("agents.validation.plan_issues")}>
          {validation.planIssues.length === 0 ? (
            <span className="muted">{t("agents.validation.no_issues")}</span>
          ) : (
            <ul className="agents-payload-list">
              {validation.planIssues.map((issue) => (
                <li key={`${issue.code}-${issue.detail}`}>
                  <code>{issue.code}</code> {issue.detail}
                  {issue.evidence !== "" && <span className="muted"> · {issue.evidence}</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.validation.strategy_source")}>
          {validation.strategyValidationSource || absent}
        </Fact>
        <Fact label={t("agents.validation.strategy_ok")}>
          {validation.strategyOk === null
            ? absent
            : validation.strategyOk
              ? t("agents.yes")
              : t("agents.no")}
        </Fact>
        <Fact label={t("agents.validation.strategy_issues")}>
          {validation.strategyIssues.length === 0 ? (
            <span className="muted">{t("agents.validation.no_issues")}</span>
          ) : (
            <ul className="agents-payload-list">
              {validation.strategyIssues.map((issue) => (
                <li key={`${issue.code}-${issue.detail}`}>
                  <code>{issue.code}</code> {issue.detail}
                  {issue.field !== "" && <span className="muted"> · {issue.field}</span>}
                </li>
              ))}
            </ul>
          )}
        </Fact>
        <Fact label={t("agents.validation.feature_catalog")}>
          {validation.featureCatalogId || absent}
        </Fact>
        <Fact label={t("agents.validation.run_blockers")}>
          <ValueListText list={validation.runBlockers} emptyLabel={absent} moreLabel={more} />
        </Fact>
        <Fact label={t("agents.validation.run_warnings")}>
          <ValueListText list={validation.runWarnings} emptyLabel={absent} moreLabel={more} />
        </Fact>
      </div>
    );
  }

  if (envelope.artifact_type === "challenge_report") {
    const challenge = agentChallengeView(envelope.payload);
    if (!challenge) return null;
    return (
      <div className="agents-payload">
        <Fact label={t("agents.challenge.overall_result")}>
          <StatusBadge variant="source" status={challenge.overallResult.toLowerCase() || "unknown"}>
            {challenge.overallResult || absent}
          </StatusBadge>
        </Fact>
        <Fact label={t("agents.challenge.strategy_version")}>
          {challenge.strategyVersionId || absent}
        </Fact>
        <Fact label={t("agents.challenge.backtest_run")}>{challenge.backtestRunId || absent}</Fact>
        <Fact label={t("agents.challenge.follow_up")}>{challenge.recommendedFollowUp || absent}</Fact>
        <Fact label={t("agents.challenge.items")}>
          {challenge.items.length === 0 ? (
            <span className="muted">{absent}</span>
          ) : (
            <ul className="agents-payload-list">
              {challenge.items.map((item, index) => (
                <li key={`${item.challenge}-${index}`}>
                  <code>{item.severity || absent}</code> {item.challenge}
                  <span className="muted"> · {item.result}</span>
                  {item.recommendedFollowUp !== "" && (
                    <span className="muted"> · {item.recommendedFollowUp}</span>
                  )}
                  {item.evidence.length > 0 && (
                    <span className="muted">
                      {" "}
                      ·{" "}
                      {item.evidence.map((row) => `${row.key}=${row.value}`).join(", ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Fact>
      </div>
    );
  }

  const pack = agentReviewPackView(envelope.payload);
  if (!pack) return null;
  return (
    <div className="agents-payload">
      <Fact label={t("agents.review_pack.status")}>
        <StatusBadge variant="source" status={pack.status.toLowerCase() || "unknown"}>
          {pack.status || absent}
        </StatusBadge>
      </Fact>
      <Fact label={t("agents.review_pack.objective")}>{pack.objective}</Fact>
      <Fact label={t("agents.review_pack.key_findings")}>
        <ValueListText list={pack.keyFindings} emptyLabel={absent} moreLabel={more} />
      </Fact>
      <Fact label={t("agents.review_pack.warnings")}>
        <ValueListText list={pack.warnings} emptyLabel={absent} moreLabel={more} />
      </Fact>
      <Fact label={t("agents.review_pack.known_limitations")}>
        <ValueListText list={pack.knownLimitations} emptyLabel={absent} moreLabel={more} />
      </Fact>
      <Fact label={t("agents.review_pack.alternative_hypotheses")}>
        <ValueListText list={pack.alternativeHypotheses} emptyLabel={absent} moreLabel={more} />
      </Fact>
      <Fact label={t("agents.review_pack.data_provenance")}>
        <ValueListText list={pack.dataProvenance} emptyLabel={absent} moreLabel={more} />
      </Fact>
      <Fact label={t("agents.review_pack.backtest")}>
        <FieldRows rows={pack.backtest} t={t} />
      </Fact>
      <Fact label={t("agents.review_pack.robustness")}>
        <FieldRows rows={pack.robustness} t={t} />
      </Fact>
      <Fact label={t("agents.created_at")}>{pack.createdAt || absent}</Fact>
    </div>
  );
}

/**
 * Ordered CR-15 artifact chain: presence, identity, lineage, rights, timestamps
 * and each artifact's own compact payload. Read-only evidence, no execution.
 */
export function AgentArtifactChain({ replay, t }: AgentArtifactChainProps) {
  const chain = agentChainView(replay);
  const absent = t("agents.value_absent");
  const more = t("agents.more_values");
  const labels: Record<AgentArtifactType, string> = {
    research_plan: t("agents.artifact.research_plan"),
    findings: t("agents.artifact.findings"),
    strategy_ir: t("agents.artifact.strategy_ir"),
    validation: t("agents.artifact.validation"),
    challenge_report: t("agents.artifact.challenge_report"),
    review_pack: t("agents.artifact.review_pack"),
  };
  const steps = agentValueList(replay.fixture?.evidence_refs, 4);

  return (
    <div className="agents-chain">
      <PanelHeader
        title={t("agents.chain")}
        meta={replay.artifact_chain?.chain_hash ? replay.artifact_chain.chain_hash : absent}
      />
      <p className="panel-copy">{t("agents.chain_help")}</p>

      <MetricStrip
        className="metric-grid agents-chain-metrics"
        items={[
          {
            label: t("agents.chain_progress"),
            value: `${formatAgentCount(chain.presentCount)}/${formatAgentCount(chain.total)}`,
            detail: t("agents.chain_progress_help"),
          },
          {
            label: t("agents.chain_missing"),
            value: formatAgentCount(chain.missingCount),
            detail: chain.missing.length > 0
              ? chain.missing.map((type) => labels[type]).join(", ")
              : t("agents.chain_none_missing"),
          },
          {
            label: t("agents.chain_state"),
            value: chain.complete ? t("agents.chain_complete") : t("agents.chain_incomplete"),
          },
          { label: t("agents.fixture_id"), value: replay.fixture?.fixture_id || absent },
          {
            label: t("agents.fixture_tool_invocations"),
            value: formatAgentCount(replay.fixture?.tool_invocation_ids?.length ?? 0),
          },
          { label: t("agents.fixture_evidence_refs"), value: formatAgentCount(steps.total) },
        ]}
      />

      <p className="agents-cot-note">
        <strong>{t("agents.hidden_cot")}</strong> {t("agents.hidden_cot_none")}
      </p>

      <ol className="agents-chain-list">
        {chain.entries.map((entry) => {
          const envelope = entry.envelope;
          return (
            <li key={entry.artifactType} className={`agents-chain-entry${entry.present ? "" : " is-absent"}`}>
              <div className="agents-chain-heading">
                <span className="agents-chain-position">{entry.position}</span>
                <strong>{labels[entry.artifactType]}</strong>
                <StatusBadge
                  variant="source"
                  status={entry.present ? "present" : "missing"}
                >
                  {entry.present ? t("agents.artifact_present") : t("agents.artifact_missing")}
                </StatusBadge>
                {entry.operationId !== "" && <span className="status-badge">{entry.operationId}</span>}
                {entry.stage !== "" && (
                  <span className="muted">
                    {t("agents.stage")}: {entry.stage}
                  </span>
                )}
              </div>

              {!entry.present && (
                <p className="agents-chain-absent">
                  <strong>{t("agents.artifact_absent")}</strong> {t("agents.artifact_absent_help")}
                </p>
              )}
              {entry.envelopeMissing && (
                <p className="agents-chain-absent">{t("agents.artifact_body_unavailable")}</p>
              )}

              {envelope && (
                <>
                  <div className="agents-fact-grid">
                    <Fact label={t("agents.operation_id")}>{envelope.operation_id || absent}</Fact>
                    <Fact label={t("agents.stage")}>{envelope.stage || absent}</Fact>
                    <Fact label={t("agents.artifact_id")}>{envelope.artifact_id || absent}</Fact>
                    <Fact label={t("agents.artifact_ids")}>
                      <ValueListText
                        list={agentValueList(envelope.artifact_ids, 4)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.replay_id")}>
                      {envelope.replay_identity?.replay_id || absent}
                    </Fact>
                    <Fact label={t("agents.content_hash")}>
                      {envelope.replay_identity?.content_hash || absent}
                    </Fact>
                    <Fact label={t("agents.deterministic")}>
                      {envelope.replay_identity?.deterministic
                        ? t("agents.deterministic_yes")
                        : t("agents.deterministic_no")}
                    </Fact>
                    <Fact label={t("agents.fixture_id")}>{envelope.fixture?.fixture_id || absent}</Fact>
                    <Fact label={t("agents.fixture_kind")}>{envelope.fixture?.fixture_kind || absent}</Fact>
                    <Fact label={t("agents.fixture_model")}>
                      {envelope.fixture?.deterministic_model
                        ? `${envelope.fixture.deterministic_model.model_provider}/${envelope.fixture.deterministic_model.model_id}`
                        : absent}
                    </Fact>
                    <Fact label={t("agents.fixture_evidence_refs")}>
                      <ValueListText
                        list={agentValueList(envelope.fixture?.evidence_refs, 3)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.fixture_tool_invocations")}>
                      <ValueListText
                        list={agentValueList(envelope.fixture?.tool_invocation_ids, 3)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>

                    <Fact label={t("agents.lineage.upstream")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.upstream_artifact_ids, 4)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.invocations")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.producing_invocation_ids, 4)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.source_families")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.source_families)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.series")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.series_ids)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.snapshots")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.snapshot_ids)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.source_refs")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.source_references)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.lineage.evidence_deps")}>
                      <ValueListText
                        list={agentValueList(envelope.lineage?.evidence_dependencies)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>

                    <Fact label={t("agents.rights.state")}>
                      <StatusBadge
                        variant="source"
                        status={(envelope.rights?.entitlement_state ?? "unknown").toLowerCase()}
                      >
                        {envelope.rights?.entitlement_state || absent}
                      </StatusBadge>
                    </Fact>
                    <Fact label={t("agents.rights.states")}>
                      <ValueListText
                        list={agentValueList(envelope.rights?.entitlement_states)}
                        emptyLabel={absent}
                        moreLabel={more}
                      />
                    </Fact>
                    <Fact label={t("agents.rights.principal")}>{envelope.rights?.principal_id || absent}</Fact>
                    <Fact label={t("agents.rights.boundary")}>{envelope.rights?.policy_boundary || absent}</Fact>
                    <Fact label={t("agents.rights.evaluated")}>
                      {formatAgentCount(envelope.rights?.evaluated_invocation_ids?.length ?? 0)}
                    </Fact>

                    <Fact label={t("agents.created_at")}>
                      {formatAgentTimestamp(envelope.timestamps?.created_at) || absent}
                    </Fact>
                    <Fact label={t("agents.run_started_at")}>
                      {formatAgentTimestamp(envelope.timestamps?.run_started_at) || absent}
                    </Fact>
                    <Fact label={t("agents.run_completed_at")}>
                      {formatAgentTimestamp(envelope.timestamps?.run_completed_at) || absent}
                    </Fact>
                  </div>

                  <div className="agents-payload-block">
                    <span className="eyebrow">{t("agents.payload")}</span>
                    {entry.present && envelope.payload !== null ? (
                      <ArtifactPayload envelope={envelope} t={t} />
                    ) : (
                      <p className="muted">{t("agents.payload_absent")}</p>
                    )}
                  </div>
                </>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
