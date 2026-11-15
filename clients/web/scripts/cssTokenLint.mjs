// CSS token lint (UX-01): converted stylesheets take every colour, font size, radius, control
// height and weight from the design tokens (src/styles/tokens.css).
//
// Most of the existing CSS predates the tokens. Those files are listed, with their current count
// of violations, in css-token-baseline.json. The baseline can only shrink:
//   - a file not in the baseline must have no violations (new and converted files);
//   - a listed file may not have more violations than its baseline count;
//   - a listed file with fewer violations fails until the baseline is lowered to match
//     (`npm run lint:css -- --update`), so progress is recorded and cannot be given back;
//   - `--update` never raises a count or adds a file.
// tests/cssTokenLint.test.ts runs this in `npm test`, which CI runs.
//
//   node scripts/cssTokenLint.mjs            # report; exit 1 on a failure
//   node scripts/cssTokenLint.mjs --update   # lower baseline counts to what is measured
//   node scripts/cssTokenLint.mjs --list <file>   # print one file's violations
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(WEB_ROOT, "src");
export const BASELINE_FILE = path.join(WEB_ROOT, "scripts", "css-token-baseline.json");
/** The token file is where raw values live; it is the only file exempt. */
export const TOKEN_FILE = "src/styles/tokens.css";

const FONT_SIZE_TOKENS = ["xs", "sm", "base", "md", "xl", "num"].map((s) => `var(--ds-text-${s})`);
const RADIUS_TOKENS = ["sm", "md", "pill"].map((s) => `var(--ds-radius-${s})`);
/** Older token names that point at a step of the scale; converted files use the step itself. */
export const DEPRECATED_TOKENS = new Set([
  "--ds-text-lg",
  "--ds-text-2xl",
  "--ds-text-3xl",
  "--ds-space-5",
  "--ds-radius-lg",
  "--ds-control-lg",
  "--ds-duration",
  "--ds-shadow-sm",
  "--ds-shadow-md",
  "--ds-shadow-lg",
  "--ds-positive-soft",
  "--ds-negative-soft",
  "--ds-warning",
  "--ds-warning-soft",
]);
const NAMED_COLOURS =
  /(^|[\s,(])(white|black|red|green|blue|yellow|orange|purple|gray|grey|silver|navy|teal|maroon|olive|lime|aqua|fuchsia|pink|brown|gold|cyan|magenta)(?=$|[\s,)])/i;
const COLOUR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(/;

/**
 * The legacy variable families: every non-role name tokens.css still defines for old
 * stylesheets, and the --eg-* family. A component's own custom property (set from an inline
 * style, say) is not one of these and is allowed.
 */
const LEGACY_VARIABLES = new Set(
  [...readFileSync(path.join(WEB_ROOT, TOKEN_FILE), "utf8").matchAll(/^\s*(--[\w-]+)\s*:/gm)]
    .map((m) => m[1])
    .filter((name) => !name.startsWith("--ds-") && !name.startsWith("--pnl-")),
);
const isLegacyVariable = (name) =>
  LEGACY_VARIABLES.has(name) || name.startsWith("--eg-") || ["--focus", "--line-soft", "--success", "--text-muted", "--font-mono"].includes(name);

export function cssFiles(dir = SRC) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return cssFiles(full);
    return name.endsWith(".css") ? [full] : [];
  });
}

const rel = (file) => path.relative(WEB_ROOT, file).split(path.sep).join("/");

/** Declarations as {prop, value, line}. Selectors and at-rule preludes never match. */
function declarations(text) {
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, " "));
  const out = [];
  const re = /(^|[{;\s])(--[\w-]+|[a-z-]+)\s*:\s*([^;{}]+?)\s*(?=;|})/g;
  let m;
  while ((m = re.exec(clean))) {
    const line = clean.slice(0, m.index + m[1].length).split("\n").length;
    out.push({ prop: m[2], value: m[3].replace(/\s+/g, " ").replace(/\s*!important$/, ""), line });
  }
  return out;
}

/** Every rule a converted stylesheet must follow. Returns [{line, rule, text}]. */
export function lintCss(text) {
  const decls = declarations(text);
  const local = new Set(decls.filter((d) => d.prop.startsWith("--")).map((d) => d.prop));
  const problems = [];
  const flag = (d, rule) => problems.push({ line: d.line, rule, text: `${d.prop}: ${d.value}` });
  for (const d of decls) {
    const { prop, value } = d;
    // A mask's black means "opaque", not a colour anyone sees.
    const paints = !/^(-webkit-)?mask/.test(prop) && prop !== "font-family";
    if (paints && (COLOUR_LITERAL.test(value) || (!prop.startsWith("--") && NAMED_COLOURS.test(value)))) {
      flag(d, "raw colour: use a colour role");
    }
    if (prop === "font-size" && !FONT_SIZE_TOKENS.includes(value) && !["inherit", "unset"].includes(value)) {
      flag(d, "font size off the type scale: use var(--ds-text-xs|sm|base|md|xl|num)");
    }
    if (prop === "font" && /\d(px|em|rem|%)/.test(value)) flag(d, "font shorthand with a raw size");
    if (/^border(-[a-z]+)*-radius$/.test(prop)) {
      const parts = value.split(/\s+/);
      if (!parts.every((p) => RADIUS_TOKENS.includes(p) || p === "0" || p === "inherit")) {
        flag(d, "radius off the scale: use var(--ds-radius-sm|md|pill) or 0");
      }
    }
    if (/^(min-|max-)?(height|block-size)$/.test(prop)) {
      const px = value.match(/^(\d+(?:\.\d+)?)px$/);
      if (px && Number(px[1]) >= 18 && Number(px[1]) <= 48) {
        flag(d, "control-sized height: use var(--ds-control-sm|control|control-touch)");
      }
    }
    if (prop === "font-weight" && !/^(var\(--ds-weight-(regular|medium|semibold)\)|400|500|600|normal|inherit)$/.test(value)) {
      flag(d, "weight off the scale: 400, 500 or 600");
    }
    for (const ref of value.matchAll(/var\((--[\w-]+)/g)) {
      const name = ref[1];
      if (DEPRECATED_TOKENS.has(name)) flag(d, `deprecated token ${name}`);
      else if (isLegacyVariable(name) && !local.has(name)) flag(d, `legacy variable ${name}: use a --ds- role`);
    }
  }
  return problems;
}

export function measure() {
  const counts = {};
  for (const file of cssFiles()) {
    const key = rel(file);
    if (key === TOKEN_FILE) continue;
    counts[key] = lintCss(readFileSync(file, "utf8")).length;
  }
  return counts;
}

export function readBaseline() {
  return JSON.parse(readFileSync(BASELINE_FILE, "utf8")).files;
}

/** Compare a measurement with the baseline. */
export function check(counts = measure(), baseline = readBaseline()) {
  const failures = [];
  for (const [file, count] of Object.entries(counts)) {
    const allowed = baseline[file];
    if (allowed === undefined) {
      if (count > 0) failures.push(`${file}: ${count} raw values in a converted file (not in the baseline)`);
    } else if (count > allowed) {
      failures.push(`${file}: ${count} raw values, baseline ${allowed} (it may only shrink)`);
    } else if (count < allowed) {
      failures.push(`${file}: ${count} raw values, baseline still says ${allowed}: run npm run lint:css -- --update`);
    }
  }
  for (const file of Object.keys(baseline)) {
    if (!(file in counts)) failures.push(`${file}: listed in the baseline but no longer exists; remove it (--update)`);
  }
  const remaining = Object.values(counts).reduce((a, b) => a + b, 0);
  const legacyFiles = Object.keys(counts).filter((f) => f in baseline && counts[f] > 0).length;
  const converted = Object.keys(counts).filter((f) => counts[f] === 0).length;
  return { failures, remaining, legacyFiles, converted, total: Object.keys(counts).length };
}

function main(argv) {
  if (argv[0] === "--list") {
    const file = path.resolve(WEB_ROOT, argv[1]);
    for (const p of lintCss(readFileSync(file, "utf8"))) console.log(`${rel(file)}:${p.line}  ${p.rule}  [${p.text}]`);
    return 0;
  }
  const counts = measure();
  if (argv[0] === "--update") {
    const baseline = readBaseline();
    const next = {};
    for (const [file, allowed] of Object.entries(baseline)) {
      if (!(file in counts) || counts[file] === 0) continue;
      next[file] = Math.min(allowed, counts[file]);
    }
    const doc = JSON.parse(readFileSync(BASELINE_FILE, "utf8"));
    doc.files = next;
    writeFileSync(BASELINE_FILE, `${JSON.stringify(doc, null, 2)}\n`);
  }
  const result = check(counts);
  console.log(
    `CSS token lint: ${result.converted} of ${result.total} stylesheets clean; ` +
      `${result.legacyFiles} not yet converted, ${result.remaining} raw values remaining.`,
  );
  for (const f of result.failures) console.log(`  FAIL ${f}`);
  return result.failures.length ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
