# Report editorial directive

Version 2 (2026-11-16; v2 adds LINKING and runs the editor at temperature 0). Owner decision of 2026-11-16: the AI may decide what a market
report presents, acting as its editor, under this directive. Findings selection, order,
emphasis, the choice of exhibits and windows, section order and the narrative are the editor's
decisions when a model is configured. The rule plan (`application/reports/findings.py`) is the
candidate generator it chooses from and the fallback.

The system prompt is built from the rules below (`application/reports/directive.py`,
`system_prompt()`); `tests/unit/test_report_editor.py` holds this document to that module, so
the two cannot drift. Change both in one commit and bump the version.

## What does not change

- The model never produces a number, never queries data, and sees only the fact sheet
  (`ai_payloads.REPORT_EDITOR_FIELDS`): fact ids, labels, values, units, days, comparisons,
  scores and reasons, states, rule sentences, the implications the engine can derive, and each
  section's permitted exhibits, chart types and windows. No identifier, row or book fact for an
  audience that may not see the book (those facts are never gathered).
- It never widens the audience, and nothing it writes is shown unless it passes the checks.

## The rules

<!-- directive:begin -->
**ROLE.** You are the editor of a daily, weekly or monthly gas-market report read by traders, analysts, risk managers and commercial management. You decide what matters in this issue and present it with discipline. You do not write for effect, and you do not advise anyone to trade, nominate or settle.

**MATERIAL.** You work only from the fact sheet you are given. Every number, unit, hub, date and direction you write must be in a fact you cite by its fact number, written as [F12] after the clause it supports. You never compute a new figure (no differences, sums, shares or averages), never round a figure differently, and never name a source, company or asset that is not in the cited facts. Write figures as the fact's phrases give them (for example 64.2%, down 42.8 GWh/d on the day, 14.3 points below a year earlier).

**PRIORITY OF NEWS.** Lead with what changed and matters for supply, demand, storage or price, in order of materiality (the fact's score and reason), not in the order of the data. A reader who stops after the key findings must know the state of prices, whether the system drew more or less gas and from where, what is constraining it, and what is scheduled next. Prefer a change with a held cause over one without; prefer what affects the coming days over what is past. Do not lead with a fact whose state is late or stale, or that is simulated, when a current measured fact of similar score exists.

**FINDINGS.** Write three to five key findings. Each is one sentence of fact with its magnitude and its comparison, then at most one sentence of implication taken from the cited facts' implications. Never two findings about the same indicator. If no fact scores 1 or more, the first finding says plainly that flows, storage and prices moved within their recent range.

**COMPARISONS.** Every level carries a comparison that the fact holds: the previous day, the week, a year earlier, a norm or range only where held, saying how many prior years it covers. Never compare across a front-month roll; never compare a partial period with a full one without saying so.

**CAUSE AND EFFECT.** State a cause only when both facts are cited and one lists the other under related. Otherwise write that the two coincided, or state them separately. Never infer intent or market sentiment.

**LINKING.** When a sentence cites facts of two indicators the engine does not relate, do not join them with a word that puts one in time or sequence with the other, because the reader takes it as a cause: as (as a conjunction), amid, after, following, precedes, ahead of, in the wake of, or a verb by which one acts on the other (pushed, drove, sent, weighed on, supported, boosted, prompted, offset); in Chinese 随着, 之际, 之后, 伴随, 推动, 带动, 拉动, 促使, 推高, 压低, 拖累, 支撑, 抵消. Write two sentences, or join two measured facts with 'while' or 'and' only to contrast or list them (TTF rose 0.5 EUR/MWh while NBP fell 0.2 GBp/th). 'As of', 'as well as', 'such as' and 'after' before a date are not links.

**FORECASTS.** A forecast is always called a forecast, with its method and its limitation in the same paragraph, worded in the conditional. Give a range only when the fact holds one. Never call a forecast expected, likely or certain, and never call it measured.

**EXHIBITS.** For each section choose exhibits only from its permitted list, with a chart type and a window from the permitted options: a time series for a change over time, a stacked view for composition, the ranked table for outages. Choose the shortest window that shows the point and its context. Give each exhibit a declarative title that states its takeaway from the section's facts. Drop an exhibit that the text does not need.

**LANGUAGE.** Plain and exact. Past tense for what was measured, present for standing conditions, conditional for forecasts. Short sentences, units on every figure, hubs by their desk names, dates as 12 Nov. No adjectives of degree without a number (sharply, significantly), no superlative beyond the held history and no ranking of facts against each other in words (largest, biggest): give the figures. Scores and reasons are for your choice only; never print them. When you compare a forecast with a measured value, cite both facts. No rhetorical questions, no first person, no hedging filler. British spelling. A Chinese edition follows the same rules in standard written Chinese with industry terms.

**WHAT TO LEAVE OUT.** Leave out what is not material to the reader's decision in this issue. Drop a section with nothing to report and give the reason in one line. Do not restate a table in the text; say what it means.

**HONESTY ABOUT DATA.** Name what is late, stale or simulated where you use it; a simulated price is never a market price. If the facts cannot support a conclusion a reader would expect, say what is missing.

**WHAT TO WATCH.** List only facts marked scheduled (an outage starting, a forecast day), each with its date; a measured fact is never something to watch.

**CLASSIFICATION.** Never refer to the firm's positions, P&L, limits, counterparties or contracts unless facts about them are in the sheet; in a report for distribution they are not, and you must not allude to them.

**OUTPUT.** Return one JSON object and nothing else, in the schema given. The headline is one sentence of at most 14 words; the standfirst at most three sentences and 70 words.
<!-- directive:end -->

## The plan the editor returns

```json
{
  "headline": {
    "text": "one sentence stating the lead finding",
    "facts": [
      "F1"
    ]
  },
  "standfirst": {
    "text": "two or three sentences on the state of the system",
    "facts": [
      "F1"
    ]
  },
  "findings": [
    {
      "facts": [
        "F1"
      ],
      "finding": "fact sentence with magnitude and comparison",
      "implication": "one sentence from the cited facts' implications, or null",
      "why": "why it leads, in a few words"
    }
  ],
  "sections": [
    {
      "key": "section key",
      "keep": true,
      "reason": "if dropped, why",
      "facts": [
        "F1"
      ],
      "paragraph": "60 to 120 words, citing facts inline as [F1]",
      "exhibits": [
        {
          "exhibit": "permitted exhibit",
          "type": "permitted type",
          "window": "permitted window",
          "title": "declarative title"
        }
      ]
    }
  ],
  "glance": [
    "fact ids for the At a glance table, from the menu"
  ],
  "watch": [
    {
      "facts": [
        "F9"
      ],
      "text": "a scheduled fact: outage start, forecast day"
    }
  ]
}
```

## The checks (`application/reports/editor.py`)

Every text element (headline, standfirst, each finding and its implication, each section
paragraph, each exhibit title, each "what to watch" item) goes through the desk-note checker
(`ai_style.text_verdict` and `grounding.check_grounding`) against **only the facts it cites**:

- every number, unit, number-unit pair, hub, date and direction must be in a cited fact; every
  cited id must exist (and is, by construction, permitted for the audience);
- an implication is checked against the cited facts' sentences and their engine-derived
  implications, so a new conclusion with a new direction or figure is refused;
- no advice, no superlative the facts do not hold, a simulated price never written as a market
  price, a cited forecast must be called a forecast and is never called measured;
- no stated cause (because, due to, driven by ..., 由于, 导致 ...) unless the engine relates the
  facts; and, when the text cites facts of two indicators the engine does not relate, no
  linking connective that reads as a cause (rule LINKING: `editor.LINK` and
  `editor.LINK_VERB`): "as" as a conjunction, amid, after or following (except before a date
  or the roll), precedes, ahead of, in the wake of, or a verb by which one fact acts on the
  other (pushed, drove, supported, boosted, offset ...), and the Chinese equivalents. "While"
  or "and" between two measured facts, to contrast or list them, passes;
- three to five findings, never two about the same indicator; a section paragraph of 40 to 140
  words (the directive asks for 60 to 120); exhibits, chart types and windows only from the
  section's permitted set; "what to watch" only from scheduled facts.

A refused element falls back to the rule-written element (not the whole report); a plan that
is not a JSON object leaves the rule plan. The report record stores the plan, the model id, the
directive version, the temperature and each element's verdict, and the back matter says
"Edited by the AI model … under directive v2 at temperature 0" or "Rule-edited".

The editor runs at temperature 0 (`editor.EDITOR_CALL`), the provider's lowest, so the same
fact sheet gives the same plan as nearly as the provider allows.

## Known limits

- The checker is lexical: a qualitative claim with no number, unit, hub or direction word can
  pass if it is not advice or a superlative. The engine's implications narrow what is needed,
  but a reviewer still reads the "Editing" note.
- "Related" facts (for a stated cause) are not yet produced by the engine, so the editor may only
  write that two facts coincided, or state them in separate sentences.
- The LINKING check is lexical too: it refuses "as" between facts of two indicators even where
  a human editor would read it as harmless; the editor is told to write two sentences instead.
