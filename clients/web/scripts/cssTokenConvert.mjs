// Mechanical first pass for converting a stylesheet to design tokens (UX-01).
//
//   node scripts/cssTokenConvert.mjs src/components/foo.css [more.css ...]
//
// Rewrites what has exactly one right answer: legacy variable families (--eg-*, --space-*,
// --text-meta, ...) and deprecated --ds-* aliases to their role or step, fallbacks inside
// var(--ds-*) (tokens are always defined), rem font sizes that sit on the scale, and raw radii
// to the radius scale. It does not touch raw colours, em sizes or control heights: those need a
// decision, and `node scripts/cssTokenLint.mjs --list <file>` lists what remains.
import { readFileSync, writeFileSync } from "node:fs";

/** Legacy names to roles. A function picks by property where one name served two roles. */
const VARS = {
  "--eg-ink": (prop) => (prop === "color" ? "--ds-text-1" : "--ds-ink"),
  "--eg-on-ink": "--ds-on-ink",
  "--eg-body": "--ds-text-2",
  "--eg-muted": "--ds-text-3",
  "--muted": "--ds-text-2",
  "--text": "--ds-text-1",
  "--text-muted": "--ds-text-2",
  "--eg-hairline": "--ds-border",
  "--eg-border": "--ds-border",
  "--border": "--ds-border",
  "--line-soft": "--ds-border-subtle",
  "--eg-hairline-strong": "--ds-border-strong",
  "--eg-canvas": "--ds-surface",
  "--eg-surface": "--ds-surface",
  "--surface": "--ds-surface",
  "--eg-canvas-soft": "--ds-bg",
  "--bg": "--ds-bg",
  "--eg-canvas-soft-2": "--ds-surface-2",
  "--surface-strong": "--ds-surface-2",
  "--eg-link": "--ds-accent",
  "--eg-accent": "--ds-accent",
  "--accent": "--ds-accent",
  "--eg-positive": "--ds-positive",
  "--success": "--ds-positive",
  "--eg-negative": "--ds-negative",
  "--eg-danger": "--ds-negative",
  "--danger": "--ds-negative",
  "--eg-warn": "--ds-status-watch",
  "--eg-warning": "--ds-status-watch",
  "--warning": "--ds-status-watch",
  "--ds-warning": "--ds-status-watch",
  "--eg-warn-soft": "--ds-status-watch-soft",
  "--ds-warning-soft": "--ds-status-watch-soft",
  "--eg-positive-soft": "--ds-status-ok-soft",
  "--ds-positive-soft": "--ds-status-ok-soft",
  "--eg-negative-soft": "--ds-status-breach-soft",
  "--ds-negative-soft": "--ds-status-breach-soft",
  "--eg-radius-sm": "--ds-radius-sm",
  "--radius-control": "--ds-radius-sm",
  "--eg-radius-md": "--ds-radius-md",
  "--radius-panel": "--ds-radius-md",
  "--radius-large": "--ds-radius-md",
  "--ds-radius-lg": "--ds-radius-md",
  "--eg-pill": "--ds-radius-pill",
  "--eg-radius-pill": "--ds-radius-pill",
  "--eg-shadow-3": "--ds-shadow-pop",
  "--shadow": "--ds-shadow-pop",
  "--ds-shadow-md": "--ds-shadow-pop",
  "--ds-shadow-lg": "--ds-shadow-modal",
  "--space-1": "--ds-space-1",
  "--space-2": "--ds-space-2",
  "--space-3": "--ds-space-3",
  "--space-4": "--ds-space-4",
  "--space-5": "--ds-space-6",
  "--space-6": "--ds-space-8",
  "--ds-space-5": "--ds-space-4",
  "--text-meta": "--ds-text-xs",
  "--text-body": "--ds-text-base",
  "--text-control": "--ds-text-base",
  "--text-heading": "--ds-text-md",
  "--text-panel-title": "--ds-text-md",
  "--ds-text-lg": "--ds-text-md",
  "--text-workspace-title": "--ds-text-xl",
  "--text-page-title": "--ds-text-xl",
  "--ds-text-2xl": "--ds-text-xl",
  "--ds-text-3xl": "--ds-text-num",
  "--control-compact": "--ds-control-sm",
  "--control-standard": "--ds-control",
  "--control-prominent": "--ds-control",
  "--ds-control-lg": "--ds-control",
  "--motion-fast": "--ds-duration-fast",
  "--motion-standard": "--ds-duration-base",
  "--motion-emphasis": "--ds-duration-slow",
  "--ds-duration": "--ds-duration-base",
  "--eg-font-mono": "--ds-font-ui",
  "--font-mono": "--ds-font-mono",
  "--pnl-profit": "--pnl-profit",
};
/** Shadows that were a 1 px inset outline, not elevation. */
const INSET_OUTLINE = new Set(["--eg-shadow-1", "--eg-shadow-2"]);

const REM = { "0.6875rem": "xs", "0.75rem": "sm", "0.8125rem": "base", "0.875rem": "base", "1rem": "md" };
const RADIUS = {
  "2px": "0", "3px": "0", "4px": "var(--ds-radius-sm)", "5px": "var(--ds-radius-sm)", "6px": "var(--ds-radius-sm)",
  "8px": "var(--ds-radius-md)", "10px": "var(--ds-radius-md)", "12px": "var(--ds-radius-md)", "14px": "var(--ds-radius-md)",
  "16px": "var(--ds-radius-md)", "18px": "var(--ds-radius-md)", "50%": "var(--ds-radius-pill)",
  "100px": "var(--ds-radius-pill)", "999px": "var(--ds-radius-pill)", "9999px": "var(--ds-radius-pill)",
};

/** Replace each var(...) whose name is mapped, dropping any fallback. */
function rewriteVars(value, prop) {
  let out = "";
  let i = 0;
  while (i < value.length) {
    const start = value.indexOf("var(", i);
    if (start < 0) {
      out += value.slice(i);
      break;
    }
    out += value.slice(i, start);
    let depth = 0;
    let end = start;
    for (; end < value.length; end += 1) {
      if (value[end] === "(") depth += 1;
      else if (value[end] === ")" && --depth === 0) break;
    }
    const inner = value.slice(start + 4, end);
    const name = inner.split(",")[0].trim();
    const target = VARS[name];
    if (INSET_OUTLINE.has(name)) out += "inset 0 0 0 1px var(--ds-border)";
    else if (target) out += `var(${typeof target === "function" ? target(prop) : target})`;
    else if (name.startsWith("--ds-") || name.startsWith("--pnl-")) out += `var(${name})`;
    else out += `var(${rewriteVars(inner, prop)})`;
    i = end + 1;
  }
  return out;
}

export function convertCss(text) {
  return text.replace(/(^|[{;\s])(--[\w-]+|[a-z-]+)(\s*:\s*)([^;{}]+?)(\s*)(?=;|})/g, (all, lead, prop, colon, value, tail) => {
    let v = value.includes("var(") ? rewriteVars(value, prop) : value;
    if (prop === "font-size" && REM[v.trim()]) v = `var(--ds-text-${REM[v.trim()]})`;
    if (/^border(-[a-z]+)*-radius$/.test(prop)) v = v.split(/\s+/).map((p) => RADIUS[p] ?? p).join(" ");
    if (prop === "font-weight" && /^(700|800|900|bold|bolder)$/.test(v.trim())) v = "var(--ds-weight-semibold)";
    return `${lead}${prop}${colon}${v}${tail}`;
  });
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop())) {
  for (const file of process.argv.slice(2)) {
    const before = readFileSync(file, "utf8");
    const after = convertCss(before);
    if (after !== before) writeFileSync(file, after);
    console.log(`${file}: ${after === before ? "unchanged" : "rewritten"}`);
  }
}
