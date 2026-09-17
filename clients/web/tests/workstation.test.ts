/**
 * Architecture V2 Wave 10 - desktop workstation contract tests.
 *
 * Wave 10 gives the desktop terminal real workstation behaviour without forking
 * business logic. These tests pin the properties that make a thin host safe: a
 * window profile is a layout rather than an authority, a native notification cannot
 * carry a commercial value, a deep link cannot claim one either, diagnostics export
 * is an allowlist, and the shortcut model is unambiguous.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  DEEP_LINK_CONTEXT_KEYS,
  DEEP_LINK_FORBIDDEN_PARAMS,
  DEEP_LINK_SCHEME,
  DIAGNOSTICS_ALLOWED_FIELDS,
  DIAGNOSTICS_FORBIDDEN_FIELDS,
  NOTIFICATION_EVENT_KINDS,
  NOTIFICATION_POLICIES,
  WORKSTATION_PROFILES,
  WORKSTATION_PROFILE_IDS,
  WORKSTATION_SHORTCUTS,
  buildDeepLink,
  buildDiagnosticsBundle,
  buildNotificationPayload,
  notificationIsAllowed,
  notificationPolicy,
  openableWindows,
  parseDeepLink,
  planWorkstation,
  shortcutConflicts,
  windowStateKey,
  workstationProfile,
} from "../src/app/host/workstation.ts";
import { HOST_COMMAND_CAPABILITIES, HOST_COMMANDS, hostCapabilities } from "../src/app/host/hostCapabilities.ts";
import { workspacePageIds } from "../src/workspaceNavigation.ts";
import { primaryWorkspaces } from "../src/app/navigation/productNavigation.ts";

test("a window profile is a layout over declared pages, never a second authority", () => {
  assert.equal(WORKSTATION_PROFILES.length, WORKSTATION_PROFILE_IDS.length);

  const primaryIds = new Set(primaryWorkspaces.map((workspace) => workspace.id));
  for (const profile of WORKSTATION_PROFILES) {
    assert.equal(primaryIds.has(profile.primary), true, `${profile.id} primary`);
    assert.equal(profile.windows.length > 0, true, `${profile.id} has windows`);
    // Exactly one primary window owns the profile's focus.
    assert.equal(
      profile.windows.filter((window) => window.role === "primary").length,
      1,
      `${profile.id} primary windows`,
    );

    for (const window of profile.windows) {
      assert.equal(workspacePageIds.includes(window.page), true, `${profile.id}:${window.page}`);
      assert.equal(window.requires.length > 0, true, `${profile.id}:${window.windowId} requires a capability`);
      for (const capability of window.requires) {
        assert.equal(capability in hostCapabilities("desktop"), true, capability);
      }
    }

    // Window ids are unique inside a profile: the layout key depends on it.
    const ids = profile.windows.map((window) => window.windowId);
    assert.equal(new Set(ids).size, ids.length, `${profile.id} window ids`);
  }

  // A profile is reachable by id, and an unknown id is an error rather than an
  // empty layout that looks like "this desk has no windows".
  assert.equal(workstationProfile("trading-desk").windows.length, 3);
  assert.throws(() => workstationProfile("not-a-profile" as never));
});

test("a host opens only the windows its capabilities allow, and a layout remembers no authority", () => {
  const profile = workstationProfile("market-monitor");
  const desktop = (capability: keyof ReturnType<typeof hostCapabilities>) =>
    hostCapabilities("desktop")[capability];
  const browser = (capability: keyof ReturnType<typeof hostCapabilities>) =>
    hostCapabilities("browser")[capability];
  const withoutNotifications = (capability: keyof ReturnType<typeof hostCapabilities>) =>
    capability === "notifications" ? false : hostCapabilities("desktop")[capability];

  assert.equal(openableWindows(profile, desktop).length, 2);
  // A shell without the notification capability still opens the analysis window;
  // it simply does not claim the monitoring window it cannot serve.
  assert.deepEqual(
    openableWindows(profile, withoutNotifications).map((window) => window.windowId),
    ["market"],
  );

  // A host without multi-window is not a failed host: the desk degrades to its
  // primary page in the window it has, and the plan says so instead of refusing.
  const browserPlan = planWorkstation("trading-desk", browser);
  assert.equal(browserPlan.supported, false);
  assert.deepEqual(browserPlan.windows, []);
  assert.deepEqual(browserPlan.fallback, { page: "market", task: "curves" });

  const desktopPlan = planWorkstation("trading-desk", desktop);
  assert.equal(desktopPlan.supported, true);
  assert.equal(desktopPlan.windows.length, 3);
  assert.deepEqual(desktopPlan.fallback, { page: "market", task: "curves" });

  // Every profile degrades to a real page, so a plan is always actionable.
  for (const profile of WORKSTATION_PROFILES) {
    const plan = planWorkstation(profile.id, browser);
    assert.equal(workspacePageIds.includes(plan.fallback.page), true, profile.id);
    assert.equal(plan.supported, false);
  }

  // The persisted layout key is derived from ids only, so a layout cannot remember
  // an identity, a capability or a commercial value for the next person at the
  // machine.
  const key = windowStateKey("trading-desk", "market");
  assert.equal(key, "eurogas.window.trading-desk.market");
  for (const profile of WORKSTATION_PROFILES) {
    for (const window of profile.windows) {
      const windowKey = windowStateKey(profile.id, window.windowId);
      assert.match(windowKey, /^eurogas\.window\.[a-z-]+\.[a-z-]+$/);
    }
  }
});

test("a native notification carries codes and references, never a commercial value", () => {
  // Every declared family has a policy, and a family may notify at the severity the
  // product promised or above it only.
  for (const kind of NOTIFICATION_EVENT_KINDS) {
    const policy = notificationPolicy(kind);
    assert.equal(NOTIFICATION_POLICIES.includes(policy), true);
    assert.equal(notificationIsAllowed(kind, "info"), policy.minimumSeverity === "info");
    assert.equal(notificationIsAllowed(kind, "critical"), true);
  }

  const payload = buildNotificationPayload({
    kind: "monitoring-alert",
    severity: "critical",
    titleKey: "experience.notification.monitoring_alert.title",
    bodyKey: "experience.notification.monitoring_alert.body",
    refs: ["alert-1"],
    codes: ["SOURCE_STALE"],
    // A caller that passes values gets a payload without them: the allowlist is the
    // mechanism, so a withheld row cannot leak onto the operating system.
    price: 31.4,
    volumeMwh: 1200,
    pnlGbp: -15000,
    entitlement: ["EEX"],
    note: "TTF day-ahead closed at 31.4 EUR/MWh",
  });

  assert.ok(payload);
  assert.deepEqual(Object.keys(payload).sort(), [
    "bodyKey",
    "codes",
    "humanReviewRequired",
    "kind",
    "refs",
    "severity",
    "titleKey",
  ]);
  assert.equal(JSON.stringify(payload).includes("31.4"), false);
  assert.equal(JSON.stringify(payload).includes("1200"), false);
  assert.equal(JSON.stringify(payload).includes("15000"), false);
  assert.equal(JSON.stringify(payload).includes("EEX"), false);
  assert.deepEqual(payload.refs, ["alert-1"]);
  assert.deepEqual(payload.codes, ["SOURCE_STALE"]);

  // The client composes the copy (it owns the localisation); the host renders it.
  assert.equal(payload.titleKey, "experience.notification.monitoring_alert.title");
  assert.equal(payload.humanReviewRequired, true);

  // An unknown family, a severity below the policy floor, and a payload without copy
  // produce no notification at all, rather than an in-app event dressed up as an OS
  // interruption.
  assert.equal(buildNotificationPayload({ kind: "not-a-family", severity: "critical" }), null);
  assert.equal(buildNotificationPayload({ kind: "monitoring-alert", severity: "info" }), null);
  assert.equal(
    buildNotificationPayload({
      kind: "monitoring-alert",
      severity: "critical",
      titleKey: "experience.notification.monitoring_alert.title",
    }),
    null,
  );
});

test("a deep link opens only declared pages and refuses authority parameters", () => {
  const target = parseDeepLink("eurogas://market?task=curves&gasDay=2026-09-16&hub=TTF");
  assert.ok(target);
  assert.equal(target.page, "market");
  assert.equal(target.task, "curves");
  assert.equal(target.context.hub, "TTF");

  // Unknown page, unknown scheme and a malformed URL open nothing.
  assert.equal(parseDeepLink("eurogas://monitoring?task=overview"), null);
  assert.equal(parseDeepLink("https://evil.example/market"), null);
  assert.equal(parseDeepLink("not a url"), null);

  // A link that tries to carry an authority is refused outright: honouring the page
  // while ignoring the parameter would let the caller believe it had been applied.
  for (const forbidden of DEEP_LINK_FORBIDDEN_PARAMS) {
    assert.equal(parseDeepLink(`eurogas://market?${forbidden}=ADMIN`), null, forbidden);
  }

  // Only declared context keys survive, so a link cannot smuggle extra state.
  const extra = parseDeepLink("eurogas://market?hub=TTF&theme=dark&filter=secret");
  assert.ok(extra);
  assert.deepEqual(Object.keys(extra.context).sort(), ["hub"]);

  // Links the product builds are always parseable back, and an unknown page falls
  // back to the default page rather than producing an unopenable link.
  const built = buildDeepLink("review", { gasDay: "2026-09-16", token: "nope" });
  assert.equal(built.startsWith(`${DEEP_LINK_SCHEME}://review?`), true);
  assert.equal(built.includes("token"), false);
  assert.equal(parseDeepLink(built)?.page, "review");
  assert.equal(buildDeepLink("not-a-page" as never), "eurogas://network");

  // Every declared context key round-trips.
  for (const key of DEEP_LINK_CONTEXT_KEYS) {
    assert.equal(buildDeepLink("market", { [key]: "value" }).includes(`${key}=value`), true, key);
  }
});

test("the shortcut model is unambiguous and stays inside the host contract", () => {
  assert.deepEqual(shortcutConflicts(), []);
  assert.equal(new Set(WORKSTATION_SHORTCUTS.map((item) => item.id)).size, WORKSTATION_SHORTCUTS.length);

  for (const shortcut of WORKSTATION_SHORTCUTS) {
    assert.match(shortcut.binding, /^(Ctrl|Alt|Escape)/, shortcut.id);
    assert.match(shortcut.commandId, /^[a-z]+(\.[a-z-]+)+$/, shortcut.id);
  }

  // The workstation adds no native command of its own: a desktop behaviour that
  // needed one would have to declare its capability class first.
  const declaredCommands = new Set(Object.values(HOST_COMMANDS));
  for (const shortcut of WORKSTATION_SHORTCUTS) {
    assert.equal(declaredCommands.has(shortcut.commandId as never), false, shortcut.id);
  }
  for (const command of declaredCommands) {
    assert.equal(typeof HOST_COMMAND_CAPABILITIES[command as never], "string", command);
  }
});

test("a diagnostics bundle is an allowlist that cannot carry a credential or a value", () => {
  const bundle = buildDiagnosticsBundle({
    clientVersion: "0.5.0",
    schemaRevision: "0036_job_records",
    hostKind: "desktop",
    endpointFailureCodes: { marketContext: "timeout" },
    // Present in the source object, absent from the export.
    accessToken: "eyJhbGciOi",
    refreshToken: "refresh-token",
    apiKey: "sk-live-key",
    price: 31.4,
    volumeMwh: 1200,
    pnlGbp: -15000,
    counterparty: "Example Energy Trading",
  });

  assert.deepEqual(Object.keys(bundle).sort(), [
    "clientVersion",
    "endpointFailureCodes",
    "hostKind",
    "schemaRevision",
  ]);
  const serialised = JSON.stringify(bundle);
  for (const secret of ["eyJhbGciOi", "refresh-token", "sk-live-key", "31.4", "1200", "15000", "Example Energy"]) {
    assert.equal(serialised.includes(secret), false, secret);
  }

  // The excluded names are declared, and no name is both allowed and forbidden.
  const allowed = new Set<string>(DIAGNOSTICS_ALLOWED_FIELDS);
  for (const forbidden of DIAGNOSTICS_FORBIDDEN_FIELDS) {
    assert.equal(allowed.has(forbidden), false, forbidden);
  }
  // A field that appears in both lists is a programming error, not a silent leak.
  assert.equal(
    DIAGNOSTICS_ALLOWED_FIELDS.some((field) =>
      (DIAGNOSTICS_FORBIDDEN_FIELDS as readonly string[]).includes(field),
    ),
    false,
  );
});
