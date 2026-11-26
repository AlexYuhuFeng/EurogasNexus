/**
 * Research → Spreads (design basis 2, D.2; CP-16 and CP-23 "Describe a strategy").
 *
 * One StrategySpec, two ways to make it: type it ("forward spread net of transport tariff
 * between TTF and NBP", "英国对荷兰 次月") and the server interprets it (its parser, or the
 * model when allowed: the model only translates), or edit the "Understood as" chips. Every
 * edit re-evaluates on the server; every figure on this page comes from its engine. Questions
 * the server asks (an unknown hub, a tenor not held, an unproven route) are answered with one
 * press. The result states its input classes and is as good as the weakest; simulated inputs
 * keep the whole result marked simulated.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import "@/styles/spreads.css";
import { api } from "@/api/client";
import type { CurveResultDTO, EvaluationDTO, HistoryResultDTO, InputClass, RouteDTO, SpecIssueDTO, StrategySpecDTO } from "@/api/spreads";
import { catalogueFromDTO, type PickerCatalogue } from "@/app/model/instrumentPicker";
import {
  DISPLAY_UNITS,
  INTERPRET_STAGES,
  applyChoice,
  curveChart,
  curveClasses,
  describeFromSearch,
  frontWaterfall,
  historyChart,
  pickRoute,
  routeVia,
  setKind,
  setLegHub,
  setLegTenor,
  spreadName,
  swapDirection,
  toggleCost,
  weakestClass,
} from "@/app/model/spreadsWorkbench";
import { SimulatedScope, simulatedScopeOf, useSimulatedPills } from "@/components/ui/SimulatedScope";
import { Button, InstrumentPicker, Segmented, Select, WorkProgress } from "@/components/ui";
import type { SpreadBoardDTO } from "@/api/spreads";
import { cargoHubOf, cargoSearch, focusHubs, reportSearch, specFromSearch, specName } from "@/app/model/spreadsBoard";
import { NextSteps } from "./NextSteps";
import { SpreadsBoard } from "./SpreadsBoard";
import { Chart, Waterfall, type ChartData } from "@/components/ui/charts";
import { BacktestDetails, type BacktestAnalysis } from "@/components/research/BacktestDetails";
import { StrategyTrackPanel } from "@/components/research/StrategyTrackPanel";
import { formatMeasure } from "@/app/time/valueFormat";
import { useLiveTopics } from "@/app/hooks/useLive";

/** The board re-reads on price notices at most this often: its front-month legs are the one
 * price every screen shows now, a live tick when a feed quotes it. */
export const SPREADS_BOARD_LIVE_MS = 5_000;

const fixed = (value: number | null | undefined, decimals = 3): string =>
  formatMeasure("ratio", value, { decimals });

// Examples in the interface's language only (each locale holds its own three).
const EXAMPLES = ["spreads.example.ttf_nbp", "spreads.example.nbp_m1", "spreads.example.third"] as const;

export function SpreadsWorkbench() {
  const { t, i18n } = useTranslation();
  const zh = i18n.language.toLowerCase().startsWith("zh");
  const [text, setText] = useState("");
  const [spec, setSpec] = useState<StrategySpecDTO | null>(null);
  const [issues, setIssues] = useState<SpecIssueDTO[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationDTO | null>(null);
  const [basis, setBasis] = useState<{ basis: string; ai: string; readAsText: boolean } | null>(null);
  const [stage, setStage] = useState<number | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [catalogue, setCatalogue] = useState<PickerCatalogue | null>(null);
  const evaluateSeq = useRef(0);
  const [board, setBoard] = useState<SpreadBoardDTO | null>(null);
  const [boardFailed, setBoardFailed] = useState(false);
  // Set once the desk asks for something: the default study then never replaces it.
  const asked = useRef(false);
  // The hubs the board was first read for (the desk's focus hubs): a live re-read keeps them.
  const boardHubs = useRef<string[] | null>(null);
  const rereadBoard = useCallback(() => {
    const hubs = boardHubs.current;
    if (hubs === null) return;
    api.spreadsBoard(hubs).then((response) => setBoard(response.data)).catch(() => undefined);
  }, []);
  useLiveTopics(["prices"], rereadBoard, { minIntervalMs: SPREADS_BOARD_LIVE_MS });

  const evaluate = useCallback(async (next: StrategySpecDTO) => {
    const seq = ++evaluateSeq.current;
    setSpec(next);
    setEvaluating(true);
    setFailed(null);
    try {
      const response = await api.spreadsEvaluate(next);
      if (seq !== evaluateSeq.current) return;
      setEvaluation(response.data);
      setIssues(response.data.issues);
    } catch {
      if (seq === evaluateSeq.current) setFailed("spreads.failed.evaluate");
    } finally {
      if (seq === evaluateSeq.current) setEvaluating(false);
    }
  }, []);

  const interpret = useCallback(async (description: string) => {
    const clean = description.trim();
    if (clean.length < 3) return;
    asked.current = true;
    setStage(0);
    setFailed(null);
    // The stages move while the server reads; the bar never fills before the answer.
    const timers = [window.setTimeout(() => setStage(1), 500), window.setTimeout(() => setStage(2), 1400)];
    try {
      const response = await api.spreadsInterpret({ text: clean, language: zh ? "zh-CN" : "en" });
      const data = response.data;
      setBasis({ basis: data.basis, ai: data.ai, readAsText: data.read_as_text });
      setIssues(data.issues);
      setSpec(data.spec);
      setEvaluation(null);
      if (data.ready) await evaluate(data.spec);
    } catch {
      setFailed("spreads.failed.interpret");
    } finally {
      timers.forEach((timer) => window.clearTimeout(timer));
      setStage(null);
    }
  }, [evaluate, zh]);

  // The page opens on the desk's spread board, computed from what is held (rule 19): focus
  // hubs first, then the majors. A link's study (a spec, or a description) opens on top of it.
  useEffect(() => {
    let live = true;
    const search = typeof window === "undefined" ? "" : window.location.search;
    const linked = describeFromSearch(search);
    const linkedSpec = specFromSearch(search);
    api.myPreferences()
      .then((response) => focusHubs(response.data?.effective?.strip_focus_hubs), () => [] as string[])
      .then((hubs) => {
        boardHubs.current = hubs;
        return api.spreadsBoard(hubs);
      })
      .then((response) => {
        if (!live) return;
        setBoard(response.data);
        // A link to one part of the board (Fundamentals → "the Win − Sum spread").
        const anchor = window.location.hash.slice(1);
        if (anchor) window.setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ block: "start" }), 50);
      })
      .catch(() => { if (live) setBoardFailed(true); });
    api.marketInstruments().then((response) => {
      if (!live) return;
      setCatalogue(catalogueFromDTO(response.data));
      if (linkedSpec) {
        asked.current = true;
        void evaluate(linkedSpec);
      } else if (linked) {
        setText(linked);
        void interpret(linked);
      }
    }).catch(() => {
      if (live) setFailed("spreads.failed.catalogue");
    });
    return () => { live = false; };
    // Once per mount: later changes go through the board, the chips or the describe box.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The answer bar or another Research page opens Spreads with a study in the URL while the
  // page may be open.
  useEffect(() => {
    const onPop = () => {
      const linkedSpec = specFromSearch(window.location.search);
      if (linkedSpec) {
        void evaluate(linkedSpec);
        return;
      }
      const linked = describeFromSearch(window.location.search);
      if (linked && linked !== text) {
        setText(linked);
        void interpret(linked);
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [interpret, text]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void interpret(text);
  };

  const result = evaluation?.result ?? null;
  const openStudy = (next: StrategySpecDTO) => {
    asked.current = true;
    void evaluate(next);
    window.setTimeout(() => document.querySelector("[data-understood]")?.scrollIntoView({ block: "start", behavior: "smooth" }), 50);
  };
  const studyOpen = Boolean(spec);
  const curveRoute = result && result.kind === "curve" ? result.route : null;
  const classes = useMemo(() => (result && result.kind === "curve" ? curveClasses(result) : []), [result]);
  const hubCatalogue = catalogue;

  return (
    <div className="spreads-page" data-spreads-workbench="true">

      <form className="spreads-describe" onSubmit={onSubmit} aria-label={t("spreads.describe.label")}>
        <label className="spreads-describe-label" htmlFor="spreads-describe-input">{t("spreads.describe.label")}</label>
        <div className="spreads-describe-row">
          <textarea
            id="spreads-describe-input"
            className="spreads-describe-input"
            rows={2}
            maxLength={4000}
            value={text}
            placeholder={t("spreads.describe.placeholder")}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void interpret(text);
              }
            }}
          />
          <Button type="submit" variant="primary" loading={stage !== null} disabled={text.trim().length < 3}>
            {t("spreads.describe.run")}
          </Button>
        </div>
        <p className="spreads-describe-hint">
          {t("spreads.describe.hint")}{" "}
          {EXAMPLES.map((key) => (
            <button key={key} type="button" className="spreads-example" onClick={() => { const example = t(key); setText(example); void interpret(example); }}>
              {t(key)}
            </button>
          ))}
        </p>
      </form>

      {stage !== null && (
        <WorkProgress
          stages={INTERPRET_STAGES.map((key) => t(key))}
          current={stage}
          label={t("spreads.progress.label")}
          reserve="6rem"
        />
      )}

      {failed && <p className="spreads-failed" role="alert">{t(failed)}</p>}

      {/* The board is the page's default view; with a study open it folds above it. */}
      {board ? (
        studyOpen ? (
          <details className="spreads-board-fold">
            <summary>{t("spreads.board.title")}</summary>
            <SpreadsBoard board={board} onOpen={openStudy} />
          </details>
        ) : (
          <SimulatedScope scope={board.simulated ? "all" : "none"} notice={t("spreads.simulated_banner")}>
            <SpreadsBoard board={board} onOpen={openStudy} />
          </SimulatedScope>
        )
      ) : boardFailed ? (
        <p className="spreads-failed" role="alert">{t("spreads.board.failed")}</p>
      ) : (
        <WorkProgress stages={[t("spreads.board.loading")]} current={0} label={t("spreads.board.loading")} reserve="20rem" />
      )}

      {spec && (
        <section className="spreads-understood" aria-label={t("spreads.understood.title")} data-understood="true">
          <h2 className="spreads-section-title">
            {t("spreads.understood.title")}
            {basis && (
              <span className="spreads-basis">
                {t(`spreads.basis.${basis.basis}`)}
                {basis.readAsText ? ` · ${t("spreads.basis.code_as_text")}` : ""}
              </span>
            )}
          </h2>
          <div className="spreads-chips">
            <Segmented
              label={t("spreads.chip.kind")}
              options={[{ value: "curve", label: t("spreads.kind.curve") }, { value: "history", label: t("spreads.kind.history") }]}
              value={spec.kind}
              onChange={(kind) => void evaluate(setKind(spec, kind))}
            />
            {spec.legs.map((leg, index) => (
              <div key={`${index}-${leg.hub}`} className="spreads-leg" data-leg={leg.weight > 0 ? "sell" : "buy"}>
                <span className="spreads-leg-side">{t(leg.weight > 0 ? "spreads.leg.plus" : "spreads.leg.minus")}</span>
                <InstrumentPicker
                  id={`spreads-leg-${index}`}
                  scope={spec.kind === "history" ? "instrument" : "hub"}
                  label={t("spreads.leg.label", { index: index + 1 })}
                  catalogue={hubCatalogue}
                  value={spec.kind === "history" && leg.tenor ? `${leg.hub}:${leg.tenor}` : leg.hub}
                  onChange={(selection) => {
                    let next = selection.hub !== leg.hub ? setLegHub(spec, index, selection.hub) : spec;
                    if (selection.instrument) next = setLegTenor(next, index, selection.instrument.code);
                    void evaluate(next);
                  }}
                />
              </div>
            ))}
            <Button variant="secondary" size="sm" onClick={() => void evaluate(swapDirection(spec))}>
              {t("spreads.chip.swap")}
            </Button>
            <label className="spreads-chip-field">
              <span>{t("spreads.chip.unit")}</span>
              <Select
                value={spec.unit ?? "EUR/MWh"}
                options={DISPLAY_UNITS.map((unit) => ({ value: unit, label: unit }))}
                onChange={(unit) => void evaluate({ ...spec, unit })}
              />
            </label>
            <Segmented
              label={t("spreads.chip.fx")}
              options={[{ value: "forward", label: t("spreads.fx.forward") }, { value: "spot", label: t("spreads.fx.spot") }]}
              value={spec.fx}
              onChange={(fx) => void evaluate({ ...spec, fx })}
            />
            <Button variant={spec.cost ? "primary" : "secondary"} size="sm" aria-pressed={Boolean(spec.cost)} onClick={() => void evaluate(toggleCost(spec))}>
              {spec.cost
                ? t("spreads.chip.cost_on", { from: spec.cost.from_hub, to: spec.cost.to_hub })
                : t("spreads.chip.cost_off")}
              {spec.cost && routeVia(curveRoute?.hubs).length > 0 && ` ${t("spreads.route.via", { hubs: routeVia(curveRoute?.hubs).join(", ") })}`}
            </Button>
            {spec.cost && curveRoute && (
              <RoutePicker route={curveRoute} unit={spec.unit ?? "EUR/MWh"} onPick={(through) => void evaluate(pickRoute(spec, through))} />
            )}
          </div>
          {spec.kind === "history" && <RuleChips spec={spec} onChange={(next) => void evaluate(next)} />}
          <p className="spreads-formula" data-formula="true">
            {t("spreads.formula", { spread: spreadName(spec), unit: spec.unit ?? "EUR/MWh" })}
            {spec.cost ? ` ${t("spreads.formula_cost", { from: spec.cost.from_hub, to: spec.cost.to_hub })}` : ""}
          </p>
        </section>
      )}

      {issues.length > 0 && spec && (
        <section className="spreads-questions" aria-label={t("spreads.questions.title")} data-questions="true">
          <h2 className="spreads-section-title">{t("spreads.questions.title")}</h2>
          <ul>
            {issues.map((issue) => (
              <li key={`${issue.code}-${issue.field}`}>
                <span>{t(`spreads.issue.${issue.code}`, { defaultValue: issue.message })}</span>
                {issue.choices.length > 0 && (
                  <span className="spreads-choices">
                    {issue.choices.map((choice) => (
                      <button key={choice} type="button" className="spreads-choice" onClick={() => void evaluate(applyChoice(spec, issue, choice))}>
                        {t(`spreads.choice.${choice}`, { defaultValue: choice })}
                      </button>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {evaluating && !result && (
        <WorkProgress stages={[t("spreads.progress.computing")]} current={0} label={t("spreads.progress.computing")} reserve="16rem" />
      )}

      {result && result.kind === "curve" && spec && <CurveResult result={result} spec={spec} classes={classes} />}
      {result && result.kind === "history" && spec && <HistoryResult result={result} spec={spec} />}
      {result && spec && <SpreadNextSteps spec={spec} />}
      {/* Track this strategy: a paper shadow run on the same spec (StrategyTrackPanel). */}
      <StrategyTrackPanel spec={spec ?? null} />
    </div>
  );
}

/** From a spread to a cargo priced against it, and to a report about it. */
function SpreadNextSteps({ spec }: { spec: StrategySpecDTO }) {
  const { t } = useTranslation();
  const search = typeof window === "undefined" ? "" : window.location.search;
  const name = specName(spec);
  const hub = cargoHubOf(spec);
  return (
    <NextSteps
      label={t("research.next.label")}
      steps={[
        { id: "cargo", label: t("research.next.price_cargo", { hub }), href: cargoSearch(search, hub) },
        {
          id: "report",
          label: t("research.next.add_report"),
          href: reportSearch(search, t("research.next.spread_question", { spread: name })),
        },
      ]}
    />
  );
}

/** The transport route chosen, the other routes with their extra cost, those unavailable. */
function RoutePicker({ route, unit, onPick }: { route: RouteDTO; unit: string; onPick: (through: string[] | null) => void }) {
  const { t } = useTranslation();
  const alternatives = route.alternatives ?? [];
  const unavailable = route.unavailable ?? [];
  const count = 1 + alternatives.length + unavailable.length;
  const name = (hubs: string[] | undefined) => {
    const via = routeVia(hubs);
    return via.length > 0 ? t("spreads.route.via", { hubs: via.join(", ") }) : t("spreads.route.direct");
  };
  return (
    <details className="spreads-routes" data-route-picker="true">
      <summary>{t("spreads.route.routes", { count })}</summary>
      <ul role="list">
        <li data-route-option="chosen" aria-current="true">
          <strong>{name(route.hubs)}</strong>{" "}
          {route.in_display_unit != null ? `${fixed(route.in_display_unit)} ${unit}` : t("spreads.route.not_priced")}
          {" · "}{route.picked ? t("spreads.route.your_pick") : route.complete ? t("spreads.route.cheapest") : t("spreads.route.none_complete")}
          {route.picked && (
            <button type="button" className="spreads-choice" onClick={() => onPick(null)}>{t("spreads.route.use_cheapest")}</button>
          )}
        </li>
        {alternatives.map((option) => (
          <li key={(option.hubs ?? []).join(">")} data-route-option="alternative">
            <button type="button" className="spreads-choice" onClick={() => onPick(routeVia(option.hubs))}>{name(option.hubs)}</button>{" "}
            {option.in_display_unit != null ? `${fixed(option.in_display_unit)} ${unit}` : "–"}
            {option.extra_cost != null && <span className="spreads-converted"> ({t("spreads.route.extra", { value: `${option.extra_cost >= 0 ? "+" : ""}${fixed(option.extra_cost)}`, unit })})</span>}
          </li>
        ))}
        {unavailable.map((option) => (
          <li key={option.hubs.join(">")} data-route-option="unavailable">
            {name(option.hubs)}: {t("spreads.route.unavailable", { legs: option.missing.join("; ") })}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** A number chip that commits on Enter or when it loses focus, not on every keystroke. */
function NumberChip({ label, value, min, max, step, onCommit, id }: {
  label: string; value: number | null | undefined; min: number; max: number; step: number; id: string;
  onCommit: (value: number | null) => void;
}) {
  const [draft, setDraft] = useState(value === null || value === undefined ? "" : String(value));
  useEffect(() => setDraft(value === null || value === undefined ? "" : String(value)), [value]);
  const commit = () => {
    const parsed = draft.trim() === "" ? null : Number(draft);
    if (parsed !== null && (!Number.isFinite(parsed) || parsed < min || parsed > max)) {
      setDraft(value === null || value === undefined ? "" : String(value));
      return;
    }
    if (parsed !== (value ?? null)) onCommit(parsed);
  };
  return (
    <label className="spreads-chip-field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        className="spreads-number"
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => { if (event.key === "Enter") commit(); }}
      />
    </label>
  );
}

/** History only: the entry/exit rule and the sizing, as the spec holds them. */
function RuleChips({ spec, onChange }: { spec: StrategySpecDTO; onChange: (spec: StrategySpecDTO) => void }) {
  const { t } = useTranslation();
  const rule = spec.rule;
  const kind = rule?.kind ?? "none";
  const setRule = (patch: Partial<NonNullable<StrategySpecDTO["rule"]>>) =>
    onChange({ ...spec, rule: { kind: "zscore", lookback: 20, ...(rule ?? {}), ...patch } });
  return (
    <div className="spreads-chips" data-rule-chips="true">
      <Segmented
        label={t("spreads.rule.label")}
        options={[
          { value: "none", label: t("spreads.rule.none") },
          { value: "zscore", label: t("spreads.rule.zscore") },
          { value: "threshold", label: t("spreads.rule.threshold") },
        ]}
        value={kind}
        onChange={(next) => onChange({
          ...spec,
          rule: next === "none" ? null : { kind: next, lookback: rule?.lookback ?? 20, entry_z: rule?.entry_z ?? 2, exit_z: rule?.exit_z ?? 0.5, low: rule?.low ?? null, high: rule?.high ?? null },
        })}
      />
      {rule && (
        <NumberChip id="spreads-rule-lookback" label={t("spreads.rule.lookback")} value={rule.lookback} min={5} max={250} step={1}
          onCommit={(value) => setRule({ lookback: value ?? 20 })} />
      )}
      {rule?.kind === "zscore" && (
        <>
          <NumberChip id="spreads-rule-entry" label={t("spreads.rule.entry_z")} value={rule.entry_z ?? 2} min={0.1} max={10} step={0.1}
            onCommit={(value) => setRule({ entry_z: value ?? 2 })} />
          <NumberChip id="spreads-rule-exit" label={t("spreads.rule.exit_z")} value={rule.exit_z ?? 0.5} min={0} max={10} step={0.1}
            onCommit={(value) => setRule({ exit_z: value ?? 0.5 })} />
        </>
      )}
      {rule?.kind === "threshold" && (
        <>
          <NumberChip id="spreads-rule-low" label={t("spreads.rule.low", { unit: spec.unit ?? "" })} value={rule.low} min={-1000} max={1000} step={0.01}
            onCommit={(value) => setRule({ low: value })} />
          <NumberChip id="spreads-rule-high" label={t("spreads.rule.high", { unit: spec.unit ?? "" })} value={rule.high} min={-1000} max={1000} step={0.01}
            onCommit={(value) => setRule({ high: value })} />
        </>
      )}
      {rule && (
        <NumberChip id="spreads-volume" label={t("spreads.rule.volume")} value={spec.volume_mwh_per_day ?? 1000} min={1} max={10_000_000} step={100}
          onCommit={(value) => onChange({ ...spec, volume_mwh_per_day: value })} />
      )}
    </div>
  );
}

/** A price's own simulated mark: dropped when the whole result is simulated (said once). */
function SimPill() {
  const { t } = useTranslation();
  return useSimulatedPills() ? <span className="spreads-sim">{t("instrument_picker.sim")}</span> : null;
}

function ClassLine({ classes, result }: { classes: readonly InputClass[]; result: InputClass }) {
  const { t } = useTranslation();
  return (
    <p className="spreads-classes" data-result-class={result}>
      {t("spreads.classes.inputs")}{" "}
      {classes.map((item) => (
        <span key={item} className="spreads-class" data-class={item}>{t(`spreads.class.${item}`)}</span>
      ))}
      {" "}{t("spreads.classes.result")}{" "}
      <span className="spreads-class" data-class={result}>{t(`spreads.class.${result}`)}</span>
    </p>
  );
}

/** Months listed before "Show all". */
const TABLE_ROWS = 12;
const SHORT_OPERATOR: Record<string, string> = {
  "National Gas TSO": "NGT",
  "BBL company": "BBL",
  Interconnector: "IUK",
  "Fluxys Belgium": "Fluxys",
  "Gasunie Deutschland": "GUD",
};

/** A tariff leg's operator as a desk abbreviates it (the full name stays in the table). */
function shortOperator(tso: string): string {
  return SHORT_OPERATOR[tso] ?? tso.split(/[\s/]/)[0];
}

function CurveResult({ result, spec, classes }: { result: CurveResultDTO; spec: StrategySpecDTO; classes: InputClass[] }) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  // One class for every month and every leg: said once above the table, not on each row.
  const rowClasses = new Set(result.rows.map((row) => row.input_class));
  const legClasses = new Set(result.rows.flatMap((row) => row.legs.map((leg) => leg.price_class)));
  const uniform = rowClasses.size === 1 && legClasses.size <= 1 && (legClasses.size === 0 || [...legClasses][0] === [...rowClasses][0])
    ? [...rowClasses][0]
    : null;
  const chart = curveChart(result);
  const data = useMemo<ChartData>(() => ({
    axis: "period",
    x: chart.x,
    xTitle: t("chart.delivery_month"),
    unit: result.unit,
    series: [
      // Gross is context (a second colour) but keeps the month markers the net has.
      ...(chart.hasCost ? [{ id: "gross", label: t("spreads.series.gross"), values: chart.gross, colour: 8, simulated: chart.simulated, decimals: 3 }] : []),
      { id: "net", label: t(chart.hasCost ? "spreads.series.net" : "spreads.series.spread"), values: chart.net, simulated: chart.simulated, decimals: 3 },
    ],
    // A labelled zero rule takes part in end-label placement, so no label sits on it.
    rules: [{ id: "zero", value: 0, label: "0", kind: "zero" as const }],
  }), [chart, result.unit, t]);
  const waterfall = frontWaterfall(result, {
    gross: t("spreads.waterfall.gross"),
    net: t("spreads.waterfall.net"),
    leg: (hub) => hub,
    tariff: (tso, direction) => `${shortOperator(tso)} ${t(`spreads.direction.${direction.toLowerCase()}`)}`,
  });
  const firstFx = result.rows.flatMap((row) => row.legs).find((leg) => leg.fx)?.fx ?? null;
  const fxNote = firstFx
    ? firstFx.method === "derived: covered interest parity"
      ? t("spreads.note.fx_derived", { benchmarks: firstFx.rates.map((rate) => rate.label.split(" (")[0]).join(", ") })
      : firstFx.method === "licensed"
        ? t("spreads.fx.licensed")
        : t("spreads.fx.spot_short")
    : t("spreads.note.fx_none");
  const route = result.route;
  const title = chart.hasCost && spec.cost
    ? t("spreads.title.curve_net", { spread: spreadName(spec), from: spec.cost.from_hub, to: spec.cost.to_hub })
    : t("spreads.title.curve", { spread: spreadName(spec) });
  // The class line is the curve's source mark; when every price is simulated the per-leg pills drop.
  const scope = simulatedScopeOf(result.rows.flatMap((row) => row.legs.map((leg) => leg.price_class === "simulated")));
  return (
    <section className="spreads-result" data-result="curve" aria-label={title}>
      <SimulatedScope scope={scope}>
      <ClassLine classes={classes} result={result.input_class} />
      {result.coverage && (
        <p className="spreads-coverage" role="note" data-coverage={result.coverage.priced_to}>
          {t("spreads.coverage", { to: result.coverage.priced_to, from: result.coverage.unpriced_from })}
        </p>
      )}
      {result.empty ? (
        <p className="spreads-empty">{t("spreads.empty_curve")}</p>
      ) : (
        <Chart
          id="spreads-curve"
          title={title}
          data={data}
          t={t}
          height={240}
          simulated={result.simulated}
          note={[
            t("spreads.note.fx", { labels: fxNote }),
            route ? t("spreads.note.route", {
              direction: route.direction,
              via: route.via.join(" + "),
              years: route.gas_years.join(", ") || "–",
              load: t("spreads.note.load"),
            }) : "",
          ].filter(Boolean).join(" ")}
        />
      )}
      {waterfall && waterfall.items.length > 2 && (
        <Waterfall
          id="spreads-front-waterfall"
          title={t("spreads.title.waterfall", { month: waterfall.row.label })}
          unit={result.unit}
          items={waterfall.items}
          t={t}
          decimals={3}
          simulated={waterfall.row.simulated}
        />
      )}
      {route && (
        <div className="spreads-route" data-route="true">
          <h3>{t("spreads.route.title", { direction: route.direction })}</h3>
          <table className="spreads-table">
            <thead>
              <tr>
                <th scope="col">{t("spreads.route.point")}</th>
                <th scope="col">{t("spreads.route.operator")}</th>
                <th scope="col">{t("spreads.route.direction")}</th>
                <th scope="col" className="num">{t("spreads.route.tariff")}</th>
                <th scope="col">{t("spreads.route.gas_year")}</th>
                <th scope="col">{t("spreads.route.class")}</th>
              </tr>
            </thead>
            <tbody>
              {route.legs.map((leg, index) => (
                <tr key={`${leg.point_name}-${leg.direction}-${index}`}>
                  <td>{leg.point_name}</td>
                  <td>{leg.tso}</td>
                  <td>{t(`spreads.direction.${leg.direction.toLowerCase()}`)}</td>
                  <td className="num">{leg.value === null ? t("spreads.class.missing") : `${fixed(leg.value)} ${leg.currency}/MWh`}</td>
                  <td>{leg.gas_year ?? "–"}</td>
                  <td><span className="spreads-class" data-class={leg.input_class}>{t(`spreads.class.${leg.input_class}`)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {route.missing.length > 0 && <p className="spreads-missing">{t("spreads.route.missing", { legs: route.missing.join("; ") })}</p>}
        </div>
      )}
      {uniform && !(uniform === "simulated" && scope === "all") && (
        <p className="spreads-uniform" data-uniform-class={uniform}>
          {t("spreads.table.uniform", { count: result.rows.length })}{" "}
          <span className="spreads-class" data-class={uniform}>{t(`spreads.class.${uniform}`)}</span>
        </p>
      )}
      <div className="spreads-table-wrap">
        <table className="spreads-table" data-curve-table="true">
          <caption>{t("spreads.table.caption", { unit: result.unit })}</caption>
          <thead>
            <tr>
              <th scope="col">{t("spreads.table.delivery")}</th>
              {spec.legs.map((leg) => <th key={leg.hub} scope="col" className="num">{leg.hub}</th>)}
              <th scope="col">{t("spreads.table.fx")}</th>
              <th scope="col" className="num">{t("spreads.series.gross")}</th>
              {spec.cost && <th scope="col" className="num">{t("spreads.table.cost")}</th>}
              <th scope="col" className="num">{t(spec.cost ? "spreads.series.net" : "spreads.series.spread")}</th>
              {!uniform && <th scope="col">{t("spreads.table.class")}</th>}
            </tr>
          </thead>
          <tbody>
            {(showAll ? result.rows : result.rows.slice(0, TABLE_ROWS)).map((row) => {
              const fx = row.legs.find((leg) => leg.fx)?.fx ?? null;
              return (
                <tr key={row.month} data-month={row.month.slice(0, 7)}>
                  <th scope="row">{row.label}</th>
                  {spec.legs.map((leg) => {
                    const cell = row.legs.find((item) => item.hub === leg.hub);
                    return (
                      <td key={leg.hub} className="num">
                        {cell ? (
                          <>
                            <span>{fixed(cell.native_value)} {cell.native_unit}</span>
                            {cell.native_unit !== result.unit && <span className="spreads-converted"> = {fixed(cell.value)}</span>}
                            {!uniform && cell.price_class === "simulated" && <SimPill />}
                          </>
                        ) : "–"}
                      </td>
                    );
                  })}
                  <td>{fx ? `${fx.desk_quote.pair} ${fixed(fx.desk_quote.rate, 4)} · ${t(fx.method === "derived: covered interest parity" ? "spreads.fx.derived" : fx.method === "licensed" ? "spreads.fx.licensed" : "spreads.fx.spot_short")}` : row.refused ?? "–"}</td>
                  <td className="num" data-figure="gross">{fixed(row.gross)}</td>
                  {spec.cost && (
                    <td className="num" data-figure="cost">
                      {row.cost === null ? t("spreads.class.missing") : fixed(row.cost)}
                      {row.tariff_year_differs && <span className="spreads-assumed" title={t("spreads.tariff_year_differs", { years: row.route_gas_years?.join(", "), delivery: row.delivery_gas_year })}> *</span>}
                    </td>
                  )}
                  <td className="num" data-figure="net"><strong>{fixed(row.net)}</strong></td>
                  {!uniform && <td><span className="spreads-class" data-class={row.input_class}>{t(`spreads.class.${row.input_class}`)}</span></td>}
                </tr>
              );
            })}
          </tbody>
        </table>
        {result.rows.length > TABLE_ROWS && (
          <button type="button" className="spreads-show-all" aria-expanded={showAll} onClick={() => setShowAll((value) => !value)}>
            {showAll ? t("spreads.table.show_fewer", { count: TABLE_ROWS }) : t("spreads.table.show_all", { count: result.rows.length })}
          </button>
        )}
        {result.rows.some((row) => row.tariff_year_differs) && <p className="spreads-footnote">* {t("spreads.tariff_year_note")}</p>}
      </div>
      </SimulatedScope>
    </section>
  );
}

function HistoryResult({ result, spec }: { result: HistoryResultDTO; spec: StrategySpecDTO }) {
  const { t } = useTranslation();
  const chart = historyChart(result);
  const unit = result.unit ?? spec.unit ?? "EUR/MWh";
  const data = useMemo<ChartData>(() => ({
    axis: "gas-day",
    x: chart.x,
    xTitle: t("spreads.history.x"),
    unit,
    series: [{ id: "spread", label: spreadName(spec), values: chart.spread, simulated: result.simulated, decimals: 3 }],
    rules: [
      { id: "zero", value: 0, kind: "zero" as const },
      ...chart.rules.map((rule) => ({ id: rule.id, value: rule.value, label: t("spreads.history.route_line", { direction: rule.label }), kind: "threshold" as const })),
    ],
  }), [chart, unit, spec, result.simulated, t]);
  const stats = result.analysis.statistics;
  const classes = weakestClass([result.simulated ? "simulated" : "indicative"]);
  return (
    <section className="spreads-result" data-result="history">
      <SimulatedScope scope={result.simulated ? "all" : "none"}>
      <ClassLine classes={[classes]} result={classes} />
      <Chart
        id="spreads-history"
        title={t("spreads.title.history", { spread: spreadName(spec) })}
        data={data}
        t={t}
        height={240}
        simulated={result.simulated}
        note={result.route
          ? chart.rules.length > 0
            ? t("spreads.history.route_note", { month: result.route.delivery.label })
            : t("spreads.history.route_missing", {
                month: result.route.delivery.label,
                legs: result.route.lines.flatMap((line) => line.missing).join("; ") || "–",
              })
          : undefined}
      />
      <dl className="spreads-stats">
        {(["last", "mean", "std", "zscore_last", "percentile_last", "half_life_days", "days"] as const).map((key) => (
          <div key={key}>
            <dt>{t(`spreads.stat.${key}`)}</dt>
            <dd>{key === "days" ? String(stats[key] ?? "–") : fixed(stats[key] as number | null, key === "percentile_last" || key === "half_life_days" ? 1 : 3)}</dd>
          </div>
        ))}
        {spec.rule && (
          <>
            <div>
              <dt>{t("spreads.rule.trades")}</dt>
              <dd data-figure="trades">{String(result.analysis.metrics.trades ?? "–")}</dd>
            </div>
            <div>
              <dt>{t("spreads.rule.hit_rate")}</dt>
              <dd>{result.analysis.metrics.hit_rate === null || result.analysis.metrics.hit_rate === undefined ? "–" : `${fixed((result.analysis.metrics.hit_rate as number) * 100, 0)} %`}</dd>
            </div>
            <div>
              <dt>{t("spreads.rule.pnl", { unit: (result.analysis as { pnl_currency?: string }).pnl_currency || unit.split("/")[0] })}</dt>
              <dd data-figure="pnl">{fixed(result.analysis.metrics.total_pnl as number | null, 0)}</dd>
            </div>
          </>
        )}
      </dl>
      {spec.rule && (
        <BacktestDetails
          analysis={result.analysis as unknown as BacktestAnalysis}
          unit={unit}
          currency={(result.analysis as { pnl_currency?: string }).pnl_currency || unit.split("/")[0]}
          simulated={result.simulated}
        />
      )}
      </SimulatedScope>
    </section>
  );
}
