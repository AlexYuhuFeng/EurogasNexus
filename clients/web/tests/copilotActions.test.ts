/**
 * Architecture V2 Wave 7 - canonical AI actions as product surface.
 *
 * Wave 1 declared Ask / Explain / Compare / Challenge / Draft and the boundary they
 * inherit. These tests pin the part that could silently rot: the Copilot surface
 * offers exactly those five, withholds every one of them unless the active context
 * is complete *and* at least one evidence reference exists, carries the context and
 * the references into the existing backend analysis route, qualifies what comes
 * back as interpretation rather than authority, and records the run as an
 * observable action. All model assertions run without a browser.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { AnalysisResultDTO, ApiMeta } from "../src/api/client.ts";
import type { SelectionContext } from "../src/app/context/selectionContext.ts";
import {
  DEFAULT_TRADER_CONTEXT,
  type TraderContext,
} from "../src/app/context/traderContext.ts";
import {
  AI_INVARIANTS,
  aiActionContract,
  aiActionIsAvailable,
  aiCommands,
  buildPaletteCommands,
  declaredAiActions,
  paletteCommandAvailable,
  paletteUnavailableReasonKey,
} from "../src/app/experience/index.ts";
import {
  COPILOT_BOUNDARY,
  COPILOT_CONTEXT_FIELDS,
  COPILOT_POSTURES,
  COPILOT_REQUEST_ROUTE,
  COPILOT_WITHHELD_CONTEXT,
  COPILOT_WITHHELD_EVIDENCE,
  availableCopilotActions,
  composeCopilotRequest,
  copilotContext,
  copilotContextFieldLabelKey,
  copilotContextFromSearch,
  copilotContextFromSources,
  copilotEvidenceRefs,
  copilotGapLabelKey,
  copilotOffers,
  copilotPostureLabelKey,
  copilotProducesLabelKey,
  copilotQuestion,
  copilotRunRecord,
  copilotTaskForAction,
  copilotWithheldReasonKey,
  qualifyCopilotOutput,
} from "../src/app/model/copilotModel.ts";
import { primaryWorkspaces } from "../src/app/navigation/productNavigation.ts";
import { workspacePageIds } from "../src/workspaceNavigation.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

test("the review surface converged its own AI panel onto the canonical actions", () => {
  const review = readWebSource("components/ReviewWorkspace.tsx");
  const hook = readWebSource("app/hooks/useReviewAnalysis.ts");
  const decision = readWebSource("components/DecisionWorkspace.tsx");

  // The review panel used to carry a question box and an "invoke the provider" switch,
  // which made a sixth AI entry point beside the declared five.
  assert.equal(review.includes("analysis.invoke_deepseek"), false);
  assert.equal(review.includes("analysis.question"), false);
  assert.equal(review.includes("onAnalyze"), false);

  // It now offers the canonical actions, gated by the offer the contract produced, and
  // mounts the hosted Copilot whose transport is the only one in play.
  assert.match(review, /copilotOffers\(copilotSources\.context, copilotSources\.evidenceRefs\)\.map/);
  assert.match(review, /disabled=\{!offer\.available\}/);
  assert.match(review, /<CopilotHost\s+action=\{aiAction\}/s);
  assert.match(review, /const copilotSources = useCopilotSources\(\);/);

  // The report it can generate is the deterministic backend run, and its question is no
  // longer user-typed: an AI-drafted document is the `draft` action's job.
  assert.match(review, /onGenerateReport/);
  assert.match(
    hook,
    /buildAnalysisPayload\(\s*REPORT_QUESTION,\s*false,\s*language,\s*portfolioResources,\s*analysisSnapshotId,\s*\)/s,
  );
  assert.equal(hook.includes("useState"), false);
  // The citation the report may carry is a reproducibility reference chosen from the
  // deployment's own snapshots, not a second AI input: the question stays fixed.
  assert.match(hook, /analysisSnapshotId: string \| null = null/);
  assert.match(decision, /api\.generatePortfolioReport\(review\.analysisPayload\)/);
  assert.equal(decision.includes("review.setAnalysisQuestion"), false);
  assert.equal(decision.includes("api.askAnalysis(review.analysisPayload)"), false);

  // W0-03 C13: the decision's actor is the authenticated identity, so the surface offers no
  // field for it and sends none. A typed name could only ever be an unverified claim.
  assert.equal(review.includes("review.actor_not_authenticated"), false);
  assert.match(review, /t\("review\.actor_authenticated"\)/);
  assert.equal(review.includes("setActor"), false);
  assert.equal(review.includes("actor: actor"), false);
  assert.match(review, /void onRecordDecision\(\{\s*entity_type: entityType,\s*entity_id: trimmedId,\s*decision,/s);
});

test("a workspace mounts the Copilot with the same rule the palette applies", () => {
  const cockpit = readWebSource("components/MarketCockpit.tsx");

  // The workspace offers the five canonical actions from the one registry, resolved from
  // the same canonical sources the shell and the palette use, and gates each with the
  // offer the contract produced rather than with a copy of the rule.
  assert.match(cockpit, /import \{ copilotOffers \} from "@\/app\/model\/copilotModel"/);
  assert.match(cockpit, /import \{ CopilotHost \} from "@\/components\/CopilotPanel"/);
  assert.match(cockpit, /copilotOffers\(copilotSources\.context, copilotSources\.evidenceRefs\)\.map/);
  assert.match(cockpit, /disabled=\{!offer\.available\}/);
  assert.match(
    cockpit,
    /title=\{offer\.withheldReasonKey \? t\(offer\.withheldReasonKey\) : undefined\}/,
  );
  assert.match(cockpit, /onClick=\{\(\) => setAiAction\(offer\.action\)\}/);
  assert.match(cockpit, /<CopilotHost\s+action=\{aiAction\}/s);
  // Evidence comes from the selection the surface already holds, and the panel is a
  // canonical-action surface rather than a sixth action of its own.
  assert.match(cockpit, /const copilotSources = useCopilotSources\(\{/);
  assert.match(cockpit, /routeId: selection\.routeId,/);
  assert.match(cockpit, /strategyRunId: selection\.strategyRunId,/);
  assert.match(cockpit, /import type \{ AiActionKind \} from "@\/app\/experience\/vocabulary"/);
  assert.equal(cockpit.includes("api.analysisQuery"), false, "the Copilot host owns the transport");
});

/** Executable lines only: comments state the rules and are checked separately. */
function codeLines(source: string): string {
  return source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return (
        !trimmed.startsWith("*") &&
        !trimmed.startsWith("//") &&
        !trimmed.startsWith("/*")
      );
    })
    .join("\n");
}

function traderContext(overrides: Partial<TraderContext> = {}): TraderContext {
  return { gasDay: "2026-09-16", deliveryProduct: "day-ahead", hubId: "NBP", ...overrides };
}

function selectionContext(overrides: Partial<SelectionContext> = {}): SelectionContext {
  return {
    routeId: null,
    resourceId: null,
    strategyId: null,
    strategyVersionId: null,
    strategyRunId: null,
    ...overrides,
  };
}

function copilotContextFixture(
  overrides: {
    trader?: Partial<TraderContext>;
    selection?: Partial<SelectionContext>;
    compositionAvailable?: boolean;
  } = {},
) {
  return copilotContextFromSources({
    workspace: "network",
    trader: traderContext(overrides.trader),
    selection: selectionContext({ routeId: "ROUTE-9", ...overrides.selection }),
    compositionAvailable: overrides.compositionAvailable,
  });
}

function analysisResult(overrides: Partial<AnalysisResultDTO> = {}): AnalysisResultDTO {
  return {
    analysis_id: "analysis-abc",
    task: "DB_INQUIRY",
    provider_id: "DEEPSEEK",
    provider_status: "success",
    answer_en: "English interpretation.",
    answer_zh_cn: "中文解释。",
    citations: ["src-a"],
    sections: [],
    missing_inputs: [],
    warnings: [],
    snapshot_id: "snap-7",
    created_at_utc: "2026-09-16T06:30:00+00:00",
    research_only: true,
    human_review_required: true,
    ...overrides,
  };
}

function responseMeta(overrides: Partial<ApiMeta> = {}): ApiMeta {
  return {
    research_only: true,
    human_review_required: true,
    source_references: [],
    warnings: [],
    ...overrides,
  };
}

test("the surface offers exactly the five canonical actions, each with its posture and output", () => {
  const context = copilotContextFixture();
  const evidenceRefs = copilotEvidenceRefs({ routeId: "ROUTE-9", resourceId: "RES-1" });
  const offers = copilotOffers(context, evidenceRefs);

  assert.deepEqual(
    offers.map((offer) => offer.action),
    declaredAiActions(),
  );
  assert.deepEqual(
    offers.map((offer) => offer.action),
    ["ask", "explain", "compare", "challenge", "draft"],
  );

  // The palette's AI commands are derived from the same registry, so a sixth action
  // cannot appear in one place without the other.
  assert.deepEqual(
    aiCommands().map((command) => command.target.aiAction),
    offers.map((offer) => offer.action),
  );

  const en = readLocale("en");
  const zh = readLocale("zh");
  for (const offer of offers) {
    // Posture, what it produces and the evidence it will carry, before invocation.
    assert.ok(COPILOT_POSTURES.includes(offer.posture), offer.action);
    assert.equal(offer.evidenceRefs.length, 2, offer.action);
    assert.deepEqual(offer.evidenceRefs, evidenceRefs);
    assert.equal(offer.available, true, offer.action);
    assert.equal(offer.withheldReasonKey, null, offer.action);

    for (const key of [offer.labelKey, offer.postureKey, offer.producesKey]) {
      assert.ok(en[key]?.trim(), key);
      assert.ok(zh[key]?.trim(), key);
      assert.notEqual(en[key], zh[key], key);
    }
    // The English wording is the Wave 1 contract's own wording, not a copy that can drift.
    assert.equal(en[offer.producesKey], aiActionContract(offer.action).produces, offer.action);
    assert.equal(offer.produces, aiActionContract(offer.action).produces, offer.action);
  }

  // The posture vocabulary is closed: every posture label is bilingual.
  for (const posture of COPILOT_POSTURES) {
    const key = copilotPostureLabelKey(posture);
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
  }
});

test("an action is withheld without a complete context or without evidence", () => {
  const evidenceRefs = copilotEvidenceRefs({ routeId: "ROUTE-9" });
  const complete = copilotContextFixture();
  const incompleteTrader = copilotContextFixture({ trader: { gasDay: "" } });
  const unresolvedComposition = copilotContextFixture({ compositionAvailable: false });

  assert.equal(complete.complete, true);
  assert.equal(incompleteTrader.complete, false);
  assert.ok(incompleteTrader.missingFields.includes("gas-day"));
  assert.equal(unresolvedComposition.complete, false);

  // The model's gate is the Wave 1 gate, for every action and every combination.
  for (const action of declaredAiActions()) {
    for (const context of [complete, incompleteTrader, unresolvedComposition]) {
      for (const refs of [[], evidenceRefs]) {
        const expected = aiActionIsAvailable(action, {
          activeContextComplete: context.complete,
          evidenceRefCount: refs.length,
        });
        const offer = copilotOffers(context, refs).find((item) => item.action === action);
        assert.ok(offer);
        assert.equal(offer.available, expected, `${action}/${refs.length}`);
        assert.equal(offer.withheldReasonKey === null, expected, `${action}/${refs.length}`);
        if (!expected) {
          assert.equal(
            offer.withheldReasonKey,
            context.complete ? COPILOT_WITHHELD_EVIDENCE : COPILOT_WITHHELD_CONTEXT,
          );
        }
      }
    }
  }

  // Absence of evidence is a reason to withhold *every* action, never to guess.
  assert.deepEqual(availableCopilotActions(complete, []), []);
  assert.deepEqual(availableCopilotActions(incompleteTrader, evidenceRefs), []);
  assert.deepEqual(availableCopilotActions(complete, evidenceRefs), declaredAiActions());

  assert.equal(copilotWithheldReasonKey(complete, []), COPILOT_WITHHELD_EVIDENCE);
  assert.equal(copilotWithheldReasonKey(incompleteTrader, evidenceRefs), COPILOT_WITHHELD_CONTEXT);

  // Evidence references come from the Active Context and carry identities only.
  assert.deepEqual(copilotEvidenceRefs({}), []);
  assert.deepEqual(copilotEvidenceRefs({ routeId: "  ", resourceId: null }), []);
  assert.deepEqual(
    copilotEvidenceRefs({
      routeId: "ROUTE-9",
      resourceId: "RES-1",
      strategyVersionId: "V-3",
      strategyRunId: "RUN-4",
    }),
    [
      { kind: "route", ref: "ROUTE-9" },
      { kind: "resource", ref: "RES-1" },
      { kind: "strategy-version", ref: "V-3" },
      { kind: "strategy-run", ref: "RUN-4" },
    ],
  );

  const en = readLocale("en");
  const zh = readLocale("zh");
  for (const key of [
    COPILOT_WITHHELD_CONTEXT,
    COPILOT_WITHHELD_EVIDENCE,
    ...COPILOT_CONTEXT_FIELDS.map((field) => copilotContextFieldLabelKey(field)),
    copilotGapLabelKey("analysis-snapshot"),
    "experience.palette.unavailable_evidence",
  ]) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("the context is read from the canonical sources and never invented", () => {
  const resolved = copilotContextFromSearch({
    search: "?workspace=market&gasDay=2026-09-16&product=day-ahead&hub=TTF&route=ROUTE-9",
    persisted: {},
  });
  assert.equal(resolved.activeContext.workspace, "market");
  assert.equal(resolved.activeContext.gasDay, "2026-09-16");
  assert.equal(resolved.activeContext.deliveryProduct, "day-ahead");
  assert.equal(resolved.activeContext.hubId, "TTF");
  assert.equal(resolved.activeContext.routeId, "ROUTE-9");
  assert.equal(resolved.complete, true);
  assert.equal(resolved.contextKey.startsWith("market|2026-09-16|day-ahead|TTF|ROUTE-9"), true);
  assert.deepEqual(copilotEvidenceRefs(resolved.activeContext), [
    { kind: "route", ref: "ROUTE-9" },
  ]);

  // The canonical precedence holds: URL beats the persisted preference, an unusable
  // value falls back rather than flowing into the context.
  const persistedWins = copilotContextFromSearch({
    search: "?workspace=network",
    persisted: { gasDay: "2026-09-10", deliveryProduct: "month-ahead", hubId: "NBP" },
  });
  assert.equal(persistedWins.activeContext.gasDay, "2026-09-10");
  assert.equal(persistedWins.activeContext.hubId, "NBP");
  assert.equal(persistedWins.complete, true);

  // An unusable URL value never flows into the context: the canonical resolver
  // replaces it with the persisted/default basis instead of carrying a bad day.
  const unusable = copilotContextFromSearch({
    search: "?workspace=nowhere&gasDay=not-a-day&product=hourly",
    persisted: {},
  });
  assert.equal(unusable.activeContext.workspace, "network");
  assert.equal(unusable.activeContext.gasDay, DEFAULT_TRADER_CONTEXT.gasDay);
  assert.equal(unusable.activeContext.deliveryProduct, DEFAULT_TRADER_CONTEXT.deliveryProduct);
  assert.equal(unusable.complete, true);
  assert.deepEqual(unusable.missingFields, ["hub"]);

  // A hub focus is a basis, not a requirement: a run without one covers every hub.
  const withoutHub = copilotContextFixture({ trader: { hubId: null } });
  assert.equal(withoutHub.complete, true);
  assert.deepEqual(withoutHub.missingFields, ["hub"]);

  // Context is not authority and gaps are named, never papered over.
  assert.deepEqual(copilotContextFixture().gaps, [
    "organization",
    "portfolio",
    "decision-case",
    "analysis-snapshot",
  ]);
  assert.equal(copilotContextFixture().reproducible, false);
  assert.equal(copilotContext(copilotContextFixture().activeContext, false).complete, false);
});

test("a run is composed onto the existing analysis route, context and evidence included", () => {
  const context = copilotContextFixture();
  const evidenceRefs = copilotEvidenceRefs({
    routeId: "ROUTE-9",
    resourceId: "RES-1",
  });
  const request = composeCopilotRequest({
    action: "explain",
    question: "Which inputs produced this allocation",
    context,
    evidenceRefs,
    language: "zh-CN",
  });

  assert.equal(COPILOT_REQUEST_ROUTE, "/analysis/query");
  // Only the declared analysis request fields are sent; nothing is added ad hoc.
  assert.deepEqual(Object.keys(request).sort(), [
    "invoke_provider",
    "language",
    "model",
    "provider_id",
    "question",
    "selected_assets",
    "selected_contracts",
    "selected_terms",
    "task",
  ]);
  assert.equal(request.task, copilotTaskForAction("explain"));
  assert.equal(request.language, "zh-CN");
  assert.equal(request.invoke_provider, true);
  assert.deepEqual(request.selected_assets, ["ROUTE-9", "RES-1"]);
  assert.deepEqual(request.selected_contracts, []);
  assert.deepEqual(request.selected_terms, []);

  const question = copilotQuestion({
    action: "explain",
    question: "Which inputs produced this allocation",
    context,
    evidenceRefs,
  });
  assert.equal(request.question, question);
  assert.ok(question.startsWith("[EXPLAIN] Which inputs produced this allocation"));
  assert.ok(question.includes("gas day 2026-09-16"));
  assert.ok(question.includes(`Context key: ${context.contextKey}`));
  assert.ok(question.includes("route:ROUTE-9, resource:RES-1"));

  // English stays English; an empty question falls back to the contract framing
  // rather than sending an empty prompt.
  assert.equal(composeCopilotRequest({
    action: "ask",
    question: "",
    context,
    evidenceRefs,
    language: "en",
  }).language, "en");
  assert.ok(
    copilotQuestion({ action: "ask", question: "  ", context, evidenceRefs }).includes(
      aiActionContract("ask").purpose,
    ),
  );
});

test("output is qualified as interpretation, with no numeric authority", () => {
  const qualified = qualifyCopilotOutput({
    result: analysisResult(),
    meta: responseMeta(),
    language: "en",
  });
  assert.equal(qualified.interpretation, true);
  assert.equal(qualified.numericAuthority, "none");
  assert.equal(qualified.researchOnly, true);
  assert.equal(qualified.humanReviewRequired, true);
  assert.equal(qualified.providerInvoked, true);
  assert.equal(qualified.answer, "English interpretation.");
  assert.equal(qualified.answerLanguage, "en");
  assert.equal(qualified.snapshotId, "snap-7");

  // Fail closed: either the body or the envelope reporting a flag is enough.
  const bodySilent = qualifyCopilotOutput({
    result: analysisResult({ research_only: false, human_review_required: false }),
    meta: responseMeta(),
    language: "en",
  });
  assert.equal(bodySilent.researchOnly, true);
  assert.equal(bodySilent.humanReviewRequired, true);

  const metaSilent = qualifyCopilotOutput({
    result: analysisResult(),
    meta: responseMeta({ research_only: false, human_review_required: false }),
    language: "en",
  });
  assert.equal(metaSilent.researchOnly, true);
  assert.equal(metaSilent.humanReviewRequired, true);

  const unflagged = qualifyCopilotOutput({
    result: analysisResult({ research_only: false, human_review_required: false }),
    meta: responseMeta({ research_only: false, human_review_required: false }),
    language: "en",
  });
  assert.equal(unflagged.researchOnly, false);
  assert.equal(unflagged.humanReviewRequired, false);

  // A provider that did not answer leaves a deterministic summary, and the surface
  // says so instead of presenting it as a model interpretation.
  const notInvoked = qualifyCopilotOutput({
    result: analysisResult({ provider_status: "LLM_PROVIDER_NOT_INVOKED" }),
    meta: responseMeta(),
    language: "en",
  });
  assert.equal(notInvoked.providerInvoked, false);
  // An empty answer in the request language falls back, and names the language shown.
  const chinese = qualifyCopilotOutput({
    result: analysisResult({ answer_zh_cn: "  " }),
    meta: responseMeta(),
    language: "zh-CN",
  });
  assert.equal(chinese.answer, "English interpretation.");
  assert.equal(chinese.answerLanguage, "en");
  // Envelope warnings are never dropped.
  const withWarnings = qualifyCopilotOutput({
    result: analysisResult({ warnings: ["LLM_PAYLOAD_FILTERED:contract_prices"] }),
    meta: responseMeta({ warnings: ["meta-warning"] }),
    language: "en",
  });
  assert.deepEqual(withWarnings.warnings, [
    "LLM_PAYLOAD_FILTERED:contract_prices",
    "meta-warning",
  ]);
});

test("a run is recorded as an observable action, not as hidden reasoning", () => {
  const context = copilotContextFixture();
  const evidenceRefs = copilotEvidenceRefs({ routeId: "ROUTE-9" });
  const input = {
    action: "challenge" as const,
    question: "Which assumption would change this decision",
    context,
    evidenceRefs,
    language: "en",
  };
  const record = copilotRunRecord({ ...input, recordedAtUtc: "2026-09-16T06:31:00.000Z" });

  assert.equal(record.action, "challenge");
  assert.equal(record.question, copilotQuestion(input));
  assert.equal(record.contextKey, context.contextKey);
  assert.deepEqual(record.evidenceRefs, evidenceRefs);
  assert.equal(record.route, COPILOT_REQUEST_ROUTE);
  assert.deepEqual(record.request, composeCopilotRequest(input));
  assert.equal(record.recordedAtUtc, "2026-09-16T06:31:00.000Z");
  // The record has no home for reasoning, and the contract forbids storing it.
  assert.equal(record.hiddenReasoning, null);
  assert.deepEqual(Object.keys(record).sort(), [
    "action",
    "contextKey",
    "evidenceRefs",
    "hiddenReasoning",
    "question",
    "recordedAtUtc",
    "request",
    "route",
  ]);
  assert.equal(AI_INVARIANTS.storesHiddenReasoning, false);
});

test("the product boundary is restated, not merely implied", () => {
  assert.equal(COPILOT_BOUNDARY.interpretationOnly, true);
  assert.equal(COPILOT_BOUNDARY.numericAuthority, "none");
  assert.equal(COPILOT_BOUNDARY.inheritsUserAuthority, true);
  assert.equal(COPILOT_BOUNDARY.mayWidenEntitlement, false);
  assert.equal(COPILOT_BOUNDARY.mayInventMissingData, false);
  assert.equal(COPILOT_BOUNDARY.mayExecuteOrNominate, false);
  assert.equal(COPILOT_BOUNDARY.storesHiddenReasoning, false);
  assert.equal(COPILOT_BOUNDARY.requiresReauthorisationPerCall, true);

  // The invariant set the boundary derives from is the Wave 1 one.
  assert.equal(AI_INVARIANTS.deterministicEnginesOwnNumbers, true);
  assert.equal(AI_INVARIANTS.mayExecuteOrNominate, false);

  const panel = codeLines(readWebSource("components/CopilotPanel.tsx"));
  for (const banned of ["order", "nomination", "settle", "execute", "trade"]) {
    assert.equal(new RegExp(`\\b${banned}\\b`, "i").test(panel), false, banned);
  }
  // The boundary is stated in the surface, from the shared bilingual vocabulary.
  assert.match(readWebSource("components/CopilotPanel.tsx"), /t\("experience\.copilot\.boundary"\)/);

  // The client calls the backend route only: no vendor host, no DB, no direct fetch.
  for (const file of [
    "app/model/copilotModel.ts",
    "app/hooks/useCopilot.ts",
    "components/CopilotPanel.tsx",
  ]) {
    const source = codeLines(readWebSource(file));
    for (const banned of [
      "fetch(",
      "sqlalchemy",
      "postgres",
      "DATABASE_URL",
      "deepseek.com",
      "localStorage",
    ]) {
      assert.equal(source.includes(banned), false, `${file}: ${banned}`);
    }
  }
  assert.match(readWebSource("components/CopilotPanel.tsx"), /api\.analysisQuery\(body\)/);
  assert.equal(
    readWebSource("components/CopilotPanel.tsx").includes("/analysis/query"),
    false,
    "the route is named once, in the model",
  );
});

test("the palette reaches the Copilot and offers no AI command that would do nothing", () => {
  const hook = readWebSource("app/hooks/useCommandPalette.ts");
  const component = readWebSource("components/CommandPalette.tsx");
  const shell = readWebSource("app/shell/AppShell.tsx");

  // The AI invocation surface exists, so the commands are offered in the runtime
  // palette: the Copilot hosted here, or a handler the host supplied.
  assert.match(hook, /const offersAiCommands = options\.includeAiActions !== false;/);
  assert.match(hook, /\(offersAiCommands && command\.group === "ai"\)/);
  assert.match(hook, /evidenceRefCount: evidenceRefs\.length/);
  assert.match(component, /import \{ CopilotHost \} from "@\/components\/CopilotPanel"/);
  assert.match(component, /<CopilotHost/);
  assert.match(component, /if \(unavailable\.has\(command\.id\)\) return;/);
  assert.match(component, /command\.target\.aiAction && aiSurface === "palette"/);
  assert.match(component, /experience\.palette\.unavailable_evidence/);

  // The shell mounts the palette; the Copilot is a surface inside that shell element,
  // never a new top-level navigation page (V2 rule: a new capability does not
  // automatically earn a new page).
  assert.match(shell, /<CommandPalette/);
  assert.equal(buildPaletteCommands().some((command) => command.id.includes("copilot")), false);
  assert.equal(workspacePageIds.includes("copilot" as never), false);
  assert.equal(
    primaryWorkspaces.some((primary) => primary.pages.includes("copilot" as never)),
    false,
  );

  const [ask] = aiCommands();
  assert.ok(ask);
  // Unchanged behaviour for a caller that cannot see evidence references...
  assert.equal(
    paletteCommandAvailable(ask, { capabilities: ["research.query"], activeContextComplete: true }),
    true,
  );
  // ...and the Copilot gate once it can.
  const analyst = {
    capabilities: ["research.query"],
    activeContextComplete: true,
    evidenceRefCount: 0,
  };
  assert.equal(paletteCommandAvailable(ask, analyst), false);
  assert.equal(paletteUnavailableReasonKey(ask, analyst), "experience.palette.unavailable_evidence");
  assert.equal(
    paletteCommandAvailable(ask, { ...analyst, evidenceRefCount: 1 }),
    true,
  );
  assert.equal(
    paletteUnavailableReasonKey(ask, { ...analyst, activeContextComplete: false }),
    "experience.palette.unavailable_context",
  );
  assert.equal(
    paletteUnavailableReasonKey(ask, { ...analyst, capabilities: [] }),
    "experience.palette.unavailable_capability",
  );

  // The hook wires the controller to an injected transport and never names an
  // endpoint of its own: the composition point chooses the route.
  const copilotHook = readWebSource("app/hooks/useCopilot.ts");
  assert.match(copilotHook, /await runAnalysis\(composeCopilotRequest\(input\)\)/);
  assert.equal(codeLines(copilotHook).includes('"/analysis'), false);
  assert.equal(codeLines(copilotHook).includes("fetch("), false);
});

test("the Copilot vocabulary is bilingual, complete and bounded", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  const keys = Object.keys(en).filter((key) => key.startsWith("experience.copilot."));
  assert.ok(keys.length > 0);
  for (const key of keys) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
    assert.equal(en[key].includes("?"), false, key);
    assert.equal(zh[key].includes("?"), false, key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);

  // Every literal key the surface renders exists in both locales. This is the same
  // contract the repository-wide translation gate applies.
  const sources =
    readWebSource("components/CopilotPanel.tsx") + readWebSource("components/CommandPalette.tsx");
  const literalKeys = [...sources.matchAll(/\bt\(\s*"([^"]+)"\s*\)/g)].map((match) => match[1]);
  assert.ok(literalKeys.length > 0);
  for (const key of literalKeys) {
    assert.ok(en[key]?.trim(), `en is missing ${key}`);
    assert.ok(zh[key]?.trim(), `zh is missing ${key}`);
  }
});
