import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const screen = readFileSync(new URL("../src/components/SignInScreen.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/components/SignInScreen.css", import.meta.url), "utf8");

test("sign-in actions reflect server-advertised capabilities", () => {
  assert.match(screen, /authStatus\.oidcConfigured \? \(/);
  assert.match(screen, /authStatus\.oidcConfigured \? \([\s\S]*?onOidcSignIn[\s\S]*?:\s*\(\s*<p className="sign-in-status"/);
  assert.match(screen, /devLoginAvailable && \(/);
  assert.match(screen, /authStatus\.oidcConfigured \? "sign-in-secondary" : "sign-in-primary"/);
  assert.match(screen, /auth\.no_methods/);
  assert.doesNotMatch(screen, /auth\.dev_hint/);
  assert.match(screen, /className="sign-in-retry-row"/);
  assert.match(screen, /className="sign-in-retry" onClick=\{onRetryIdentity\}/);
  assert.match(css, /\.sign-in-retry \{[\s\S]*?width: auto;/);
  assert.doesNotMatch(css, /\.sign-in-retry \{[\s\S]*?width: 100%;/);
  assert.doesNotMatch(screen, /auth\.boundary_note/);
});

test("sign-in styling uses the established type, spacing, control, and radius tokens", () => {
  assert.match(css, /font-family: Inter, -apple-system/);
  // The design-token roles and steps (tokens.css), not the legacy families they replaced.
  for (const token of [
    "--ds-text-base",
    "--ds-text-xl",
    "--ds-space-3",
    "--ds-space-4",
    "--ds-space-6",
    "--ds-control",
    "--ds-radius-sm",
    "--ds-radius-md",
  ]) {
    assert.match(css, new RegExp(`var\\(${token}\\)`), token);
  }
  assert.doesNotMatch(css, /letter-spacing|box-shadow|font-family:\s*(Georgia|serif)/);
  assert.doesNotMatch(css, /(?:28px|40px|460px|#f5f7f8|#182026|#d7e0e5)/);
});
