import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const screen = readFileSync(new URL("../src/components/SignInScreen.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/components/SignInScreen.css", import.meta.url), "utf8");

test("sign-in actions reflect server-advertised capabilities", () => {
  // Company SSO only when the deployment has it; nothing about SSO otherwise.
  assert.match(screen, /\{authStatus\.oidcConfigured && \(\s*<div className="sign-in-sso">[\s\S]*?onOidcSignIn/);
  assert.doesNotMatch(screen, /authStatus\.oidcConfigured \? \(/);
  assert.doesNotMatch(screen, /t\("auth\.sso_unavailable"\)|auth\.sso_title/);
  // The form only when the server advertises it (tester sign-in or local accounts); secondary
  // beside SSO, primary alone. The small "Tester sign-in" title belongs to the tester sign-in.
  assert.match(screen, /passwordFormAvailable && \(/);
  assert.match(screen, /authStatus\.oidcConfigured \? "sign-in-secondary" : "sign-in-primary"/);
  assert.match(screen, /devLoginAvailable && <span className="sign-in-block-title">\{t\("auth\.dev_title"\)\}<\/span>/);
  // "or" only when both are offered.
  assert.match(screen, /authStatus\.oidcConfigured && passwordFormAvailable && \([\s\S]*?className="sign-in-or" role="separator"/);
  // With no method at all, say so and offer the identity check.
  assert.match(screen, /const noMethods = !authStatus\.oidcConfigured && !passwordFormAvailable;/);
  assert.match(screen, /auth\.no_methods/);
  assert.doesNotMatch(screen, /auth\.dev_hint/);
  // The identity retry appears only when SSO is configured and failing, or nothing is offered.
  assert.match(screen, /const ssoFailing = authStatus\.oidcConfigured && authErrorKey !== null && SSO_FAILURE_KEYS\.has\(authErrorKey\);/);
  assert.match(screen, /\{ssoFailing && retry\}/);
  assert.equal((screen.match(/\{retry\}|&& retry\}/g) ?? []).length, 2, "retry rendered in exactly two states");
  assert.match(screen, /className="sign-in-retry-row"/);
  assert.match(screen, /className="sign-in-retry" onClick=\{onRetryIdentity\}/);
  assert.match(css, /\.sign-in-retry \{[\s\S]*?width: auto;/);
  assert.doesNotMatch(css, /\.sign-in-retry \{[\s\S]*?width: 100%;/);
  assert.doesNotMatch(screen, /auth\.boundary_note/);
});

test("sign-in is one heading and the methods: no eyebrow, no body line, no brand bullets or footer", () => {
  assert.equal((screen.match(/<h1\b/g) ?? []).length, 1);
  // One heading: "Sign in", "Choose your password" in the forced change after a temporary one,
  // or "Second factor" in the code step (security review H6).
  assert.match(
    screen,
    /<h1 id="sign-in-title">\s*\{passwordChange \? t\("auth\.change_title"\) : mfaStep \? t\("auth\.mfa_title"\) : t\("auth\.title"\)\}\s*<\/h1>/,
  );
  // The code step keeps the one-time-code autocomplete hint.
  assert.match(screen, /autoComplete="one-time-code"/);
  for (const removed of ["auth.eyebrow", "auth.body", "auth.brand_point_", "auth.brand_foot", "sign-in-brand-points"]) {
    assert.doesNotMatch(screen, new RegExp(removed.replace(".", "\\.")), removed);
  }
  // The brand panel: lock-up, one line, and the mark drawn large from the same paths.
  assert.match(screen, /<BrandMark variant="wordmark" tone="reverse"/);
  assert.match(screen, /auth\.brand_tagline/);
  assert.match(screen, /className="sign-in-brand-watermark"[\s\S]*?d=\{BRAND_HEX_UPPER\}[\s\S]*?d=\{BRAND_HEX_LOWER\}[\s\S]*?d=\{BRAND_WAVE\}/);
  // The version the client already knows, without a request, in the display spelling.
  assert.match(screen, /CLIENT_DISPLAY_VERSION/);
  // Credentials keep their autocomplete hints and labels.
  assert.match(screen, /autoComplete="username"/);
  assert.match(screen, /autoComplete="current-password"/);
  assert.match(screen, /htmlFor="sign-in-username"/);
  assert.match(screen, /htmlFor="sign-in-password"/);
});

test("sign-in styling uses the established type, spacing, control, and radius tokens", () => {
  // The bundled interface face through its token (fonts.css), never a device stack.
  assert.match(css, /font-family: var\(--ds-font-ui\)/);
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
