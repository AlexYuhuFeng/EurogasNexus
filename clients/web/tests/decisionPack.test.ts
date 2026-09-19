/**
 * The decision pack: one case's governance artefact, read the way a reviewer signs it.
 *
 * The pack is the product's answer to a quiet failure: the platform recorded everything a decision
 * needs, and none of it in a form anyone could sign, so the artefact was assembled by hand from four
 * reads - exactly the work that gets skipped under deadline. What these tests hold is that the
 * client reads the artefact without improving on it:
 *
 * - the snapshot verdict is measured and three-valued, and `null` (the reference cites no snapshot)
 *   is neither "not resolvable" nor "resolved": those are two different accusations and the pack
 *   made neither;
 * - the blockers come in two vocabularies, and a code this client does not know is rendered raw
 *   rather than dropped, because an unrecognised blocker is the thing a reviewer most needs to see;
 * - no decision, no pack and an unknown pack version are all *stated*, never rendered as an empty
 *   artefact or as a zero;
 * - the hash is not recomputed in the browser (the deployment's canonical JSON is not reproducible
 *   here), and it reaches the DOM character for character, with the note that says the platform
 *   holds no signature kept where a reader looks for one.
 *
 * The source pins at the end keep the panel mounted beside the case's decision controls, free of a
 * primary action and fully bilingual.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  DecisionCaseRecordDTO,
  DecisionPackDTO,
  DecisionPackEvidenceDTO,
} from "../src/api/client.ts";
import {
  DECISION_PACK_VERSION,
  RECOGNISED_DECISION_PACK_BLOCKERS,
  decisionPackAvailability,
  decisionPackHashIsIntact,
  decisionPackPresentation,
  snapshotStateLabelKey,
} from "../src/app/model/decisionPackModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

const HASH_BASIS =
  "sha256 over the canonical JSON of this pack without its content_hash field " +
  "(sorted keys, UTF-8, no insignificant whitespace)";

function evidenceRow(
  overrides: Partial<DecisionPackEvidenceDTO> = {},
): DecisionPackEvidenceDTO {
  return {
    kind: "ROUTE_RECOMMENDATION",
    ref: "route-rec-9",
    label: "NBP recommendation",
    as_of_utc: "2026-09-15T06:00:00+00:00",
    snapshot_id: "snap-42",
    snapshot_resolvable: true,
    ...overrides,
  };
}

function decisionRecord(overrides: Partial<DecisionCaseRecordDTO> = {}): DecisionCaseRecordDTO {
  return {
    outcome: "accepted",
    actor: "pack-reviewer",
    note: "Capacity confirmed.",
    evidence_refs: ["route-rec-9"],
    recorded_at_utc: "2026-09-15T09:00:00+00:00",
    ...overrides,
  };
}

/** The pack exactly as the frozen contract serves it. */
function packDto(overrides: Partial<DecisionPackDTO> = {}): DecisionPackDTO {
  const decision = decisionRecord();
  return {
    pack_version: DECISION_PACK_VERSION,
    case_id: "case-1",
    objective: "Cover tomorrow's NBP balance.",
    status: "DECIDED",
    context: {
      gas_day: "2026-09-15",
      delivery_product: "day-ahead",
      hub_id: "NBP",
      portfolio_ref: null,
      snapshot_id: "snap-42",
      reproducible: true,
      created_by: "pack-analyst",
      created_at_utc: "2026-09-15T05:00:00+00:00",
    },
    evidence: [evidenceRow()],
    assumptions: [{ key: "fx", value: "0.86", source: "ecb", note: "" }],
    alternatives: [
      {
        alternative_id: "alt-1",
        label: "Buy the balance",
        description: "",
        economics_ref: "econ-1",
        warnings: [],
      },
    ],
    ai_findings: ["the spread narrowed"],
    warnings: ["SCENARIO_STALE"],
    decision,
    history: [decision],
    audit: {
      resource: "decision_case:case-1",
      events: [
        {
          event_id: "audit-1",
          action: "decision_case_create",
          principal: "pack-analyst",
          outcome: "recorded",
          severity: "info",
          event_ts_utc: "2026-09-15T05:00:00+00:00",
          detail: "",
        },
      ],
      read_surface: "/api/audit",
    },
    signable: true,
    blockers: [],
    signature_note:
      "This pack is the artefact a reviewer signs; the platform records the human decision and " +
      "its actor, and does not hold a signature.",
    content_hash: `sha256:${"a".repeat(64)}`,
    content_hash_basis: HASH_BASIS,
    ...overrides,
  };
}

test("a snapshot the pack could not resolve, one it resolved and one it never claimed read differently", () => {
  const resolved = decisionPackPresentation(
    packDto({ evidence: [evidenceRow({ snapshot_resolvable: true })] }),
  );
  const unresolved = decisionPackPresentation(
    packDto({
      evidence: [evidenceRow({ snapshot_resolvable: false, snapshot_id: "snap-missing" })],
    }),
  );
  const notCited = decisionPackPresentation(
    packDto({ evidence: [evidenceRow({ snapshot_resolvable: null, snapshot_id: null })] }),
  );

  assert.equal(resolved.evidence[0].snapshotState, "resolved");
  assert.equal(unresolved.evidence[0].snapshotState, "unresolved");
  assert.equal(notCited.evidence[0].snapshotState, "not-cited");

  // A `null` is not a soft form of `false`: the reference cited no snapshot, so the pack claimed
  // nothing, and rendering it as "not on record" would invent an accusation the payload never made.
  assert.notEqual(notCited.evidence[0].snapshotState, "unresolved");
  assert.notEqual(notCited.evidence[0].snapshotState, "resolved");
  assert.equal(notCited.evidence[0].snapshotId, null);

  // The three states are three different sentences, not one sentence with three colours.
  const keys = ["resolved", "unresolved", "not-cited"].map((state) =>
    snapshotStateLabelKey(state as "resolved" | "unresolved" | "not-cited"),
  );
  assert.deepEqual(keys, [
    "decision_pack.snapshot.resolved",
    "decision_pack.snapshot.unresolved",
    "decision_pack.snapshot.not_cited",
  ]);
  assert.equal(new Set(keys).size, 3);

  // A reference whose snapshot is missing stays in the list: it is the hole the reviewer is looking
  // for, and the pack's own blocker names it.
  assert.equal(unresolved.evidence.length, 1);
  assert.equal(unresolved.evidence[0].ref, "route-rec-9");
});

test("an absent resolvability field is not-cited rather than a verdict", () => {
  // A deployment that predates the tri-state sends no field at all. `undefined` is not `false`.
  const evidence = { ...evidenceRow(), snapshot_resolvable: undefined } as unknown as
    DecisionPackEvidenceDTO;
  const model = decisionPackPresentation(packDto({ evidence: [evidence] }));

  assert.equal(model.evidence[0].snapshotState, "not-cited");
  // Reproducibility is a declared state too: a pack that declares neither value says nothing.
  const undeclared = decisionPackPresentation(
    packDto({
      context: { ...packDto().context, reproducible: null, portfolio_ref: null },
    }),
  );
  const byLabel = new Map(undeclared.context.map((row) => [row.labelKey, row.value]));
  assert.deepEqual(byLabel.get("decision_pack.context.reproducible"), { kind: "not-recorded" });
  // A declared-but-empty field is carried as not-recorded rather than dropped or shown as blank.
  assert.deepEqual(byLabel.get("decision_pack.context.portfolio_ref"), { kind: "not-recorded" });
  assert.deepEqual(byLabel.get("decision_pack.context.gas_day"), {
    kind: "text",
    value: "2026-09-15",
  });
});

test("no recorded decision is a statement, and the blockers that follow are shown", () => {
  const undecided = packDto({
    status: "OPEN",
    decision: null,
    history: [],
    signable: false,
    blockers: ["DECISION_PACK_DECISION_NOT_RECORDED", "evidence_required"],
  });
  const model = decisionPackPresentation(undecided);

  assert.equal(model.canShow, true);
  assert.equal(model.decision, null);
  assert.equal(model.noDecisionKey, "decision_pack.decision.none");
  assert.equal(model.signable, false);
  // The history the pack carries is empty here, so the panel states that rather than nothing.
  assert.deepEqual(model.history, []);
  // The line a reviewer reads is the explicit "none recorded yet", in both locales.
  assert.match(en[model.noDecisionKey] ?? "", /No decision is recorded yet/);
  assert.ok(zh[model.noDecisionKey]?.trim());
  assert.notEqual(en[model.noDecisionKey], zh[model.noDecisionKey]);

  // A pack that carries records but names no decision says "none recorded": the client does not
  // promote the newest record and call it the decision.
  const historyOnly = decisionPackPresentation(
    packDto({ decision: null, history: [decisionRecord(), decisionRecord({ outcome: "rejected" })] }),
  );
  assert.equal(historyOnly.decision, null);
  assert.equal(historyOnly.history.length, 2);
});

test("the blockers are split by vocabulary, and an unknown code is passed through raw", () => {
  const model = decisionPackPresentation(
    packDto({
      signable: false,
      // The pack's own codes, the case's own code, and a code added by a newer backend.
      blockers: [
        "DECISION_PACK_EVIDENCE_MISSING",
        "evidence_required",
        "DECISION_PACK_SOMETHING_NEW",
        "snapshot_recommended",
      ],
    }),
  );

  // The pack's vocabulary is recognised and translated...
  assert.deepEqual(
    model.packBlockers.map((blocker) => blocker.code),
    ["DECISION_PACK_EVIDENCE_MISSING"],
  );
  assert.equal(
    model.packBlockers[0].labelKey,
    "decision_pack.blocker.evidence_missing",
  );
  assert.ok(en["decision_pack.blocker.evidence_missing"]?.trim());
  assert.ok(zh["decision_pack.blocker.evidence_missing"]?.trim());

  // ...and everything else travels through as its raw self, in the order the pack declared it.
  // Nothing is dropped: not the case's own vocabulary, and not a code this client has never seen.
  assert.deepEqual(model.otherBlockers, [
    "evidence_required",
    "DECISION_PACK_SOMETHING_NEW",
    "snapshot_recommended",
  ]);
  // Every recognised code has copy, and each one is a distinct key.
  const labelKeys = RECOGNISED_DECISION_PACK_BLOCKERS.map(
    (code) => decisionPackPresentation(packDto({ blockers: [code] })).packBlockers[0].labelKey,
  );
  assert.equal(new Set(labelKeys).size, RECOGNISED_DECISION_PACK_BLOCKERS.length);
  for (const key of labelKeys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("a pack that is signable and still names a blocker keeps the blocker visible", () => {
  // The backend composes exactly this: a recorded decision plus evidence makes a pack signable,
  // while an evidence reference whose snapshot is not on record still lands in the blocker list.
  const model = decisionPackPresentation(
    packDto({
      signable: true,
      blockers: ["DECISION_PACK_SNAPSHOT_UNRESOLVED"],
      decision: decisionRecord(),
    }),
  );

  assert.equal(model.signable, true);
  assert.deepEqual(
    model.packBlockers.map((blocker) => blocker.code),
    ["DECISION_PACK_SNAPSHOT_UNRESOLVED"],
  );
  // The panel renders the list for a signable pack too, under the caveat heading rather than the
  // blocker one: readiness is the pack's statement, and the blocker is still a fact about it.
  const panel = readWebSource("components/decision/DecisionPackPanel.tsx");
  assert.match(panel, /model\.packBlockers\.length > 0 \|\| model\.otherBlockers\.length > 0/);
  assert.match(panel, /model\.signable\s*\?\s*"decision_pack\.caveats\.title"\s*:\s*"decision_pack\.blockers\.title"/);
});

test("a case read with no pack states why, and a pack of another shape is not guessed at", () => {
  const absent = decisionPackPresentation(undefined);
  assert.equal(absent.canShow, false);
  assert.equal(absent.reason, "no-pack");
  assert.equal(absent.reasonKey, "decision_pack.unavailable.no_pack");
  // Nothing is carried, so a caller cannot accidentally render an empty artefact beside the reason.
  assert.deepEqual(absent.context, []);
  assert.deepEqual(absent.evidence, []);
  assert.deepEqual(absent.packBlockers, []);
  assert.deepEqual(absent.otherBlockers, []);
  assert.equal(absent.hash.contentHash, null);

  assert.equal(decisionPackPresentation(null).reasonKey, "decision_pack.unavailable.no_pack");

  // A pack composed under a shape this surface does not render is stated, not read as if it matched.
  const other = decisionPackPresentation(
    packDto({ pack_version: "decision-pack-99" }),
  );
  assert.equal(other.canShow, false);
  assert.equal(other.reason, "version");
  assert.equal(other.reasonKey, "decision_pack.unavailable.version");
  assert.deepEqual(other.evidence, []);

  assert.equal(decisionPackAvailability(packDto()).showable, true);
  assert.equal(decisionPackAvailability(packDto()).reasonKey, null);
});

test("the hash is checked as a declaration and never recomputed", () => {
  assert.equal(decisionPackHashIsIntact(packDto()), "intact");
  assert.equal(
    decisionPackHashIsIntact(packDto({ content_hash: `sha256:${"0".repeat(64)}` })),
    "intact",
  );
  // Absent is `unknown`, not `invalid`: nothing was stated, which is not a failed statement.
  assert.equal(decisionPackHashIsIntact(packDto({ content_hash: "" })), "unknown");
  assert.equal(decisionPackHashIsIntact(undefined), "unknown");
  assert.equal(
    decisionPackHashIsIntact({ ...packDto(), content_hash: null } as unknown as DecisionPackDTO),
    "unknown",
  );
  // Present but not a sha256 digest: the basis says what the value should look like.
  assert.equal(decisionPackHashIsIntact(packDto({ content_hash: "md5:abc" })), "invalid");

  // The model says in the artefact's own terms that it cannot recompute the digest, because the
  // deployment's canonical JSON is not reproducible in a browser.
  const model = readWebSource("app/model/decisionPackModel.ts");
  assert.match(model, /never recomputes, reformats or repairs the value/);
  assert.equal(model.includes("crypto"), false);
});

test("the hash travels to the DOM character for character", () => {
  const hash = `sha256:${"0123456789abcdef".repeat(4)}`;
  const model = decisionPackPresentation(packDto({ content_hash: hash }));

  assert.equal(model.hash.contentHash, hash);
  assert.equal(model.hash.state, "intact");
  // As it arrived, not as the client would prefer it: no trimming, no truncation, no re-wrapping.
  assert.equal(
    decisionPackPresentation(packDto({ content_hash: `  ${hash}  ` })).hash.contentHash,
    `  ${hash}  `,
  );
  // The basis is the deployment's own sentence: it explains what the hash covers and how to
  // recompute it, so it is carried verbatim rather than paraphrased.
  assert.equal(model.hash.basis, HASH_BASIS);

  const panel = readWebSource("components/decision/DecisionPackPanel.tsx");
  // A `<code>` element, selectable, carrying the value itself - not a shortened form of it.
  assert.match(
    panel,
    /<code className=\{`decision-pack-content-hash is-\$\{model\.hash\.state\}`\}>\s*\{model\.hash\.contentHash \?\? t\("decision_pack\.hash\.absent"\)\}/,
  );
  assert.match(panel, /\{t\("decision_pack\.hash\.basis"\)\}/);
  assert.match(panel, /\{model\.hash\.basis \?\? t\("decision_pack\.not_recorded"\)\}/);
  // The sentence that ties a signed copy to the record, in both locales.
  assert.match(panel, /t\("decision_pack\.hash\.match"\)/);
  assert.match(en["decision_pack.hash.match"] ?? "", /hash/);
  assert.match(zh["decision_pack.hash.match"] ?? "", /哈希/);
  assert.equal(
    decisionPackPresentation(packDto({ content_hash: "" })).hash.state,
    "unknown",
  );
});

test("the pack is presented whole: context, evidence, assumptions, alternatives, findings, warnings", () => {
  const model = decisionPackPresentation(packDto());

  // Labels are translation keys, not English text.
  for (const row of model.context) {
    assert.match(row.labelKey, /^decision_pack\.context\.[a-z_]+$/);
    assert.ok(en[row.labelKey]?.trim(), `en ${row.labelKey}`);
    assert.ok(zh[row.labelKey]?.trim(), `zh ${row.labelKey}`);
    assert.notEqual(en[row.labelKey], zh[row.labelKey], row.labelKey);
  }
  assert.equal(model.context.length, 8);
  // The evidence row carries the declared reference, the kind's shared label key and the instant.
  const evidence = model.evidence[0];
  assert.equal(evidence.ref, "route-rec-9");
  assert.equal(evidence.label, "NBP recommendation");
  assert.equal(evidence.asOfUtc, "2026-09-15T06:00:00+00:00");
  assert.equal(evidence.kindLabelKey, "decision_case.evidence.ROUTE_RECOMMENDATION");
  assert.ok(en[evidence.kindLabelKey]?.trim() && zh[evidence.kindLabelKey]?.trim());

  assert.deepEqual(model.assumptions, [
    { key: "fx", value: "0.86", source: "ecb", note: "" },
  ]);
  assert.equal(model.alternatives[0].alternativeId, "alt-1");
  assert.equal(model.alternatives[0].economicsRef, "econ-1");
  assert.deepEqual(model.aiFindings, ["the spread narrowed"]);
  assert.deepEqual(model.warnings, ["SCENARIO_STALE"]);

  // The decision block is the newest record, with its actor and the evidence it cites.
  assert.equal(model.decision?.outcomeLabelKey, "decision_case.outcome.accepted");
  assert.equal(model.decision?.actor, "pack-reviewer");
  assert.equal(model.decision?.recordedAtUtc, "2026-09-15T09:00:00+00:00");
  assert.deepEqual(model.decision?.evidenceRefs, ["route-rec-9"]);

  // The audit trail is part of the artefact, cited against the case it belongs to.
  assert.equal(model.auditResource, "decision_case:case-1");
  assert.equal(model.auditRows[0].action, "decision_case_create");
  assert.equal(model.auditRows[0].principal, "pack-analyst");
  assert.equal(model.auditReadSurface, "/api/audit");
  // The signature note is carried as the pack states it, and the pack never claims signable on its
  // own terms: `signable` is read from the payload.
  assert.match(model.signatureNote ?? "", /does not hold a signature/);
});

test("the panel shows the pack's own signature sentence wherever a reader looks for one", () => {
  const panel = readWebSource("components/decision/DecisionPackPanel.tsx");

  assert.match(panel, /t\("decision_pack\.signature\.title"\)/);
  assert.match(panel, /\{model\.signatureNote \?\? t\("decision_pack\.signature\.none"\)\}/);
  // The sentence is rendered in both branches: a signable pack still says the platform holds no
  // signature, which is the whole point of the note.
  assert.match(panel, /t\("decision_pack\.signable\.ready"\)/);
  assert.match(panel, /t\("decision_pack\.signable\.blocked"\)/);
  const signableSection = panel.slice(panel.indexOf("decision-pack-signable"));
  assert.ok(signableSection.includes('t("decision_pack.signature.title")'));
  // No signature control of any kind: this slice presents, it does not sign.
  for (const banned of ["type=\"submit\"", "onSubmit", "signatureValue", "FormData"]) {
    assert.equal(panel.includes(banned), false, banned);
  }
});

test("the pack panel is mounted where the case detail is, beside the decision controls", () => {
  const casePanel = readWebSource("components/DecisionCasePanel.tsx");
  const workspace = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(
    casePanel,
    /import \{ DecisionPackPanel \} from "@\/components\/decision\/DecisionPackPanel";/,
  );
  assert.match(
    casePanel,
    /<DecisionPackPanel t=\{t\} model=\{decisionPackPresentation\(selected\.pack\)\} \/>/,
  );

  // The pack sits inside the case's own detail article, above the controls that record the outcome,
  // so the reviewer reads the artefact they are signing and then has the decision controls below it.
  const detail = casePanel.indexOf('<article className="decision-case-detail">');
  const pack = casePanel.indexOf("<DecisionPackPanel");
  const controls = casePanel.indexOf('<div className="decision-case-record">');
  assert.ok(detail > 0 && pack > detail, "the pack is inside the case detail");
  assert.ok(controls > pack, "the pack sits above the decision controls");

  // And that detail is the review task's: the case panel is mounted only for `task === "review"`.
  assert.match(workspace, /task === "review" && \(\s*<DecisionCasePanel/);

  // The pack rides on the read the case panel already makes, and a write is followed by that read
  // so the artefact does not vanish the moment a reviewer records the outcome.
  assert.match(casePanel, /const read = await api\.decisionCase\(caseDto\.case_id\);/);
  assert.match(casePanel, /setSelected\(await withPack\(result\.data\)\)/);
  assert.match(casePanel, /const response = await api\.decisionCase\(caseId\);/);
});

test("the panel adds no primary action, no interactivity and no second read", () => {
  const panel = readWebSource("components/decision/DecisionPackPanel.tsx");
  const model = readWebSource("app/model/decisionPackModel.ts");

  assert.equal(panel.includes("primaryAction="), false);
  // It is presentational: no fetch, no store, no clock, no effects.
  for (const banned of ["useEffect", "useState", "api.", "fetch(", "navigator.clipboard"]) {
    assert.equal(panel.includes(banned), false, banned);
  }
  // The only interactive element is the decided outcome's own controls, in the case panel above;
  // this panel renders the artefact and nothing else. (Comments explaining why are allowed.)
  const withoutComments = panel
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith("*") && !trimmed.startsWith("//") && !trimmed.startsWith("/*");
    })
    .join("\n");
  assert.equal(withoutComments.includes("<button"), false);
  assert.equal(withoutComments.includes("onClick"), false);

  // The three snapshot states reach the DOM as three different classes, and the model owns the
  // tri-state rather than the panel re-deriving it.
  assert.match(panel, /className=\{`decision-pack-snapshot is-\$\{row\.snapshotState\}`\}/);
  assert.match(model, /snapshot_resolvable === false/);
  assert.match(model, /item\.snapshot_resolvable === true/);
  // Nothing turns an absent value into a zero or an empty list.
  assert.equal(model.includes("?? 0"), false);
  assert.equal(model.includes("|| 0"), false);
});

test("every pack string is declared in both locales, and none carries a question mark", () => {
  const panel = readWebSource("components/decision/DecisionPackPanel.tsx");
  const model = readWebSource("app/model/decisionPackModel.ts");

  const keys = new Set<string>();
  for (const match of panel.matchAll(/t\("([^"]+)"\)/g)) keys.add(match[1]);
  // Keys the panel composes or states as a fallback outside a `t("...")` call.
  for (const match of panel.matchAll(/"([a-z0-9_.]+)"/g)) {
    if (match[1].startsWith("decision_pack.")) keys.add(match[1]);
  }
  for (const match of model.matchAll(/"([a-z0-9_.]+)"/g)) {
    if (match[1].startsWith("decision_pack.")) keys.add(match[1]);
  }
  // And the keys the model only produces at runtime: the three snapshot words, the recognised
  // blockers' copy, the statement that no decision is recorded, and both refusal reasons.
  keys.add(snapshotStateLabelKey("resolved"));
  keys.add(snapshotStateLabelKey("unresolved"));
  keys.add(snapshotStateLabelKey("not-cited"));
  const blockers = decisionPackPresentation(
    packDto({ signable: false, blockers: [...RECOGNISED_DECISION_PACK_BLOCKERS] }),
  );
  for (const blocker of blockers.packBlockers) keys.add(blocker.labelKey);
  keys.add(blockers.noDecisionKey);
  // The two refusal reasons, and the statement the hash block makes when the pack declares none.
  keys.add(decisionPackAvailability(undefined).reasonKey ?? "");
  keys.add(decisionPackPresentation(packDto({ pack_version: "decision-pack-99" })).reasonKey ?? "");
  keys.add("decision_pack.hash.unknown");
  keys.add("decision_pack.hash.invalid");

  assert.ok(keys.size >= 45, `expected the pack's whole vocabulary, saw ${keys.size}`);
  for (const key of keys) {
    if (key === "") continue;
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
    assert.equal(en[key].includes("?"), false, `${key} carries a question mark`);
    assert.equal(zh[key].includes("?"), false, `${key} carries a question mark`);
    // Labels are keys, and a key never contains prose a reader could mistake for a label.
    assert.match(key, /^decision_pack\./, key);
  }

  // The heading the panel picks between is declared in both locales too.
  for (const key of ["decision_pack.blockers.title", "decision_pack.caveats.title"]) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
});
