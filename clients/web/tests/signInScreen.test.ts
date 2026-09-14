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
  assert.match(screen, /onRetryIdentity/);
  assert.doesNotMatch(screen, /auth\.boundary_note/);
});

test("sign-in styling uses the established type, spacing, control, and radius tokens", () => {
  assert.match(css, /font-family: Inter, -apple-system/);
  for (const token of [
    "--text-control",
    "--text-page-title",
    "--space-3",
    "--space-4",
    "--space-5",
    "--control-standard",
    "--control-prominent",
    "--radius-control",
    "--radius-panel",
  ]) {
    assert.match(css, new RegExp(`var\\(${token}\\)`), token);
  }
  assert.doesNotMatch(css, /letter-spacing|box-shadow|font-family:\s*(Georgia|serif)/);
  assert.doesNotMatch(css, /(?:28px|40px|460px|#f5f7f8|#182026|#d7e0e5)/);
});
