import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, beforeEach, test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import react from "@vitejs/plugin-react";
import { createServer } from "vite";

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const sourceRoot = join(webRoot, "src");

const UI_STUB = `
import { createElement } from "react";

export function PanelHeader({ title, meta }) {
  return createElement("header", null, title, meta);
}

export function MetricStrip({ items }) {
  return createElement("div", null, (items ?? []).map((item, index) =>
    createElement("div", { key: index }, item.label, ": ", item.value, item.detail ? " " : "", item.detail)));
}

export function EvidenceBlock({ items }) {
  return createElement("div", null, (items ?? []).map((item, index) =>
    createElement("div", { key: index }, item.label, ": ", item.value, item.detail ? " " : "", item.detail)));
}

export function StatusBadge({ children }) {
  return createElement("span", null, children);
}

export function WorkspaceTabs({ tabs, onActivate }) {
  return createElement("div", null, (tabs ?? []).map((tab) =>
    createElement("button", {
      key: tab.id,
      type: "button",
      onClick: () => onActivate(tab.id),
    }, tab.label)));
}
`;

const STORE_STUB = `
export function useInspectorStore() {
  return { open() {} };
}
`;

const API_STUB = `
export function fetchWeatherForecasts(input) {
  const handler = globalThis["__weatherForecastRequest"];
  if (typeof handler !== "function") {
    throw new Error("weather forecast request handler was not installed");
  }
  return handler(input);
}
`;

const stubPlugin = {
  name: "weather-evidence-test-stubs",
  enforce: "pre",
  resolveId(id) {
    if (id === "@/components/ui" || id.replaceAll("\\", "/").endsWith("/src/components/ui")) return "\0weather-ui";
    if (id === "@/stores/inspector" || id.replaceAll("\\", "/").endsWith("/src/stores/inspector")) return "\0weather-store";
    if (id === "@/api/client" || id.replaceAll("\\", "/").endsWith("/src/api/client")) return "\0weather-api";
    return null;
  },
  load(id) {
    if (id === "\0weather-ui") return UI_STUB;
    if (id === "\0weather-store") return STORE_STUB;
    if (id === "\0weather-api") return API_STUB;
    return null;
  },
};

let server;
let WeatherForecastEvidence;
let SourceCenter;
let requests = [];

before(async () => {
  server = await createServer({
    configFile: false,
    root: webRoot,
    appType: "custom",
    logLevel: "silent",
    plugins: [react(), stubPlugin],
    resolve: {
      alias: { "@": sourceRoot.replaceAll("\\", "/") },
      dedupe: ["react", "react-dom"],
    },
    server: { middlewareMode: true },
    ssr: {
      external: ["react", "react-dom", "react-dom/server", "react/jsx-runtime", "react/jsx-dev-runtime"],
    },
  });
  const weatherModule = await server.ssrLoadModule("/src/components/WeatherForecastEvidence.tsx");
  const sourceCenterModule = await server.ssrLoadModule("/src/components/SourceCenter.tsx");
  WeatherForecastEvidence = weatherModule.WeatherForecastEvidence;
  SourceCenter = sourceCenterModule.SourceCenter;
});

after(async () => {
  delete globalThis["__weatherForecastRequest"];
  if (server) await server.close();
});

beforeEach(() => {
  requests = [];
  globalThis["__weatherForecastRequest"] = (input) => {
    let resolveRequest;
    const promise = new Promise((resolve) => {
      resolveRequest = resolve;
    });
    requests.push({ input, promise, resolve: resolveRequest });
    return promise;
  };
});

const REACT_INTERNALS =
  React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE
  ?? React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;

if (!REACT_INTERNALS) {
  throw new Error("this harness requires React 19 client internals");
}

const dispatcherSlot = "H" in REACT_INTERNALS
  ? {
      get: () => REACT_INTERNALS.H,
      set: (value) => { REACT_INTERNALS.H = value; },
    }
  : {
      get: () => REACT_INTERNALS.ReactCurrentDispatcher.current,
      set: (value) => { REACT_INTERNALS.ReactCurrentDispatcher.current = value; },
    };

function sameDeps(left, right) {
  return left.length === right.length && left.every((value, index) => Object.is(value, right[index]));
}

function makeDispatcher(probe) {
  return {
    useState(initial) {
      const index = probe.nextHook();
      let hook = probe.hooks[index];
      if (!hook) {
        hook = {
          kind: "state",
          value: typeof initial === "function" ? initial() : initial,
        };
        probe.hooks[index] = hook;
      }
      const setState = (next) => {
        if (probe.unmounted) return;
        const value = typeof next === "function" ? next(hook.value) : next;
        if (Object.is(value, hook.value)) return;
        hook.value = value;
        probe.render();
      };
      return [hook.value, setState];
    },

    useReducer(reducer, initialArg, init) {
      const [state, setState] = this.useState(init ? init(initialArg) : initialArg);
      return [state, (action) => setState((previous) => reducer(previous, action))];
    },

    useEffect(create, deps) {
      probe.useEffect(create, deps);
    },

    useLayoutEffect(create, deps) {
      probe.useEffect(create, deps);
    },

    useInsertionEffect() {},

    useRef(initial) {
      const index = probe.nextHook();
      let hook = probe.hooks[index];
      if (!hook) {
        hook = { kind: "ref", current: initial };
        probe.hooks[index] = hook;
      }
      return hook;
    },

    useMemo(factory, deps) {
      const index = probe.nextHook();
      let hook = probe.hooks[index];
      if (!hook || deps === undefined || !sameDeps(hook.deps, deps)) {
        hook = { kind: "memo", value: factory(), deps: deps ? deps.slice() : undefined };
        probe.hooks[index] = hook;
      }
      return hook.value;
    },

    useCallback(callback, deps) {
      return this.useMemo(() => callback, deps);
    },

    useId() {
      const index = probe.nextHook();
      let hook = probe.hooks[index];
      if (!hook) {
        hook = { kind: "id", value: `:weather-${probe.hooks.length}:` };
        probe.hooks[index] = hook;
      }
      return hook.value;
    },

    useSyncExternalStore(_subscribe, getSnapshot) {
      return getSnapshot();
    },

    useDebugValue() {},
    useContext(context) { return context._currentValue; },
    useTransition() { return [false, (callback) => callback()]; },
    useDeferredValue(value) { return value; },
    useImperativeHandle() {},
  };
}

class MountedComponent {
  constructor(Component, props) {
    this.Component = Component;
    this.props = props;
    this.hooks = [];
    this.effects = new Map();
    this.scheduledEffects = [];
    this.hookIndex = 0;
    this.unmounted = false;
    this.flushing = false;
    this.tree = null;
    this.dispatcher = makeDispatcher(this);
    this.render();
  }

  nextHook() {
    return this.hookIndex++;
  }

  render() {
    if (this.unmounted) return;
    this.hookIndex = 0;
    this.scheduledEffects = [];
    const previous = dispatcherSlot.get();
    dispatcherSlot.set(this.dispatcher);
    try {
      this.tree = this.Component(this.props);
    } finally {
      dispatcherSlot.set(previous);
    }
    this.flushEffects();
  }

  useEffect(create, deps) {
    const index = this.nextHook();
    let hook = this.hooks[index];
    const first = !hook;
    if (first) {
      hook = { kind: "effect", deps: null };
      this.hooks[index] = hook;
    }
    const changed =
      first
      || deps === undefined
      || hook.deps === null
      || !sameDeps(hook.deps, deps);
    if (!changed) return;
    hook.deps = deps ? deps.slice() : null;
    this.scheduledEffects.push({ index, create });
  }

  flushEffects() {
    if (this.flushing) return;
    this.flushing = true;
    try {
      while (this.scheduledEffects.length > 0) {
        const queued = this.scheduledEffects;
        this.scheduledEffects = [];
        for (const effect of queued) {
          if (this.unmounted) return;
          const previous = this.effects.get(effect.index);
          if (previous && previous.cleanup) previous.cleanup();
          const cleanup = effect.create();
          this.effects.set(effect.index, {
            cleanup: typeof cleanup === "function" ? cleanup : undefined,
          });
        }
      }
    } finally {
      this.flushing = false;
    }
  }

  unmount() {
    if (this.unmounted) return;
    this.unmounted = true;
    for (const effect of this.effects.values()) {
      if (effect.cleanup) effect.cleanup();
    }
    this.effects.clear();
    this.scheduledEffects = [];
  }
}

function findAll(node, predicate, found = []) {
  if (Array.isArray(node)) {
    for (const child of node) findAll(child, predicate, found);
    return found;
  }
  if (!node || typeof node !== "object") return found;
  if (predicate(node)) found.push(node);
  if (node.props) findAll(node.props.children, predicate, found);
  return found;
}

function findOne(node, predicate) {
  return findAll(node, predicate)[0];
}

function textOf(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && node.props) return textOf(node.props.children);
  return "";
}

function change(element, value) {
  assert.ok(element && element.props && element.props.onChange, "expected a controlled input");
  element.props.onChange({ currentTarget: { value }, target: { value } });
}

function editField(probe, predicate, index, value, label) {
  const fields = findAll(probe.tree, predicate);
  const element = fields[index];
  assert.ok(element, `expected ${label} at position ${index + 1}`);
  change(element, value);

  const current = findAll(probe.tree, predicate);
  assert.ok(current[index], `expected ${label} to remain mounted after editing`);
  assert.equal(
    current[index].props.value,
    value,
    `${label} must rerender with the edited value before the next edit or submit`,
  );
}

function fillRequired(probe, { series = "series-a", entity = "entity-a" } = {}) {
  const textarea = (node) => node.type === "textarea";
  assert.equal(findAll(probe.tree, textarea).length, 2);
  editField(probe, textarea, 0, series, "series input");
  editField(probe, textarea, 1, entity, "entity input");

  const textInput = (node) => node.type === "input" && node.props.type === "text";
  assert.equal(findAll(probe.tree, textInput).length, 3);
  editField(probe, textInput, 0, "2026-10-27T00:00:00Z", "prediction origin input");
  editField(probe, textInput, 1, "2026-10-27T00:00:00Z", "valid-from input");
  editField(probe, textInput, 2, "2026-10-28T00:00:00Z", "valid-to input");
}

function submit(probe) {
  const form = findOne(probe.tree, (node) => node.type === "form");
  assert.ok(form, "expected the weather evidence form to be mounted");
  return form.props.onSubmit({ preventDefault() {} });
}

function stateOf(probe) {
  const section = findOne(probe.tree, (node) => node.type === "section");
  assert.ok(section, "expected the weather evidence section to be mounted");
  return section.props["data-state"];
}

function rowId(probe) {
  const row = findOne(probe.tree, (node) => node.props?.["data-record"] === "weather-reading");
  return row ? row.props["data-record-id"] : null;
}

function makeEnvelope(rows) {
  return {
    data: rows,
    meta: {
      attribution: "ECMWF open data",
      warnings: [],
      source_references: ["ecmwf-open-data"],
    },
  };
}

function makeRow(observationId, seriesId) {
  return {
    observation_id: observationId,
    series_id: seriesId,
    entity_id: "entity-a",
    model: "IFS",
    run_id: "20261027T00",
    point_id: "grid-1",
    requested_latitude: 48.1,
    requested_longitude: 11.6,
    raw_grib_sha256: "a".repeat(64),
    record_content_sha256: "b".repeat(64),
    valid_at_utc: "2026-10-27T06:00:00Z",
    issued_at_utc: "2026-10-27T00:00:00Z",
    available_at_utc: "2026-10-27T04:00:00Z",
    temperature_c: 12.34,
    grid_latitude: 48.0,
    grid_longitude: 11.5,
  };
}

function makeSource(overrides = {}) {
  return {
    source_id: "ecmwf-1",
    source_system: "ECMWF_OPEN_DATA",
    category: "weather",
    description: "ECMWF open data",
    operational_status: "active",
    workflow_ready: true,
    credential_state: "not_required",
    connectivity_status: "connected",
    live_record_count: 0,
    preview_substitute_record_count: 0,
    preview_substitute_status: null,
    credential_provider_id: null,
    entitlement_scope: "public",
    credential_requirements: [],
    freshness_state: "fresh",
    freshness_status: "fresh",
    scheduler_enabled: false,
    next_run_at_utc: null,
    certification_stage: "not_required",
    effective_last_success_at_utc: null,
    effective_record_count: 0,
    effective_source_system: "ECMWF_OPEN_DATA",
    consecutive_failures: 0,
    datasets: ["weather"],
    diagnostics: [],
    circuit_state: null,
    freshness_expectation_minutes: null,
    last_failure_at_utc: null,
    preview_substitute_source_system: null,
    last_ingestion_status: null,
    last_ingestion_message: null,
    ...overrides,
  };
}

function sourceCenterProps(source) {
  const t = (key) => key;
  return {
    t,
    sources: [source],
    sourceCategories: ["all", "weather"],
    sourceCategory: "all",
    sourceCategoryCounts: new Map([["all", 1], ["weather", 1]]),
    sourceStats: {
      total: 1,
      active: 1,
      issues: 0,
      records: 0,
      missingCredentials: 0,
    },
    sourcePostureRows: [],
    filteredSources: [source],
    selectedSource: source,
    selectedCredentialProvider: undefined,
    credentialProviders: [],
    credentialProvider: "",
    credentialLabel: "",
    credentialValue: "",
    credentialMessage: null,
    credentialConnection: null,
    credentialEntryReadonly: false,
    flows: [],
    capacity: [],
    storage: [],
    lng: [],
    tsoAccessCount: 0,
    tsoTariffs: [],
    latestCapacityRows: [],
    onSourceCategoryChange() {},
    onSourceSelect() {},
    registryRead: {
      state: "ready",
      hasReading: true,
      noticeKey: null,
      failureEndpointKey: null,
      failureMessageKey: null,
      retry: {
        disabled: true,
        busy: false,
        attempts: 0,
        attemptsLabel: "",
        lastAttemptLabel: null,
        runningLabel: null,
      },
    },
    onRegistryRetry() {},
    onCredentialProviderChange() {},
    onCredentialLabelChange() {},
    onCredentialValueChange() {},
    onCredentialSubmit() {},
    onCredentialConnectionTest() {},
    sourceLabel(prefix, value) { return `${prefix}.${value ?? "unknown"}`; },
    categoryProviderSummary() { return "provider"; },
    sourceNextAction() { return ""; },
    runtimeDbReady: true,
    runReadiness: {
      canRequest: false,
      disclosureKeys: [],
      firstBlockerKey: null,
    },
    sourceRunOutcome: null,
    onRequestSourceRun() {},
    formatSourceTimestamp() { return "n/a"; },
  };
}

function listFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (["node_modules", ".git", "dist", "coverage", "tests"].includes(entry.name)) continue;
      files.push(...listFiles(path));
    } else {
      files.push(path);
    }
  }
  return files;
}

function isPlainObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function flattenKeys(value, prefix, keys, seen = new WeakSet()) {
  if (Array.isArray(value)) {
    if (prefix) keys.add(prefix);
    return;
  }
  if (isPlainObject(value)) {
    if (seen.has(value)) {
      if (prefix) keys.add(prefix);
      return;
    }
    seen.add(value);
    for (const [key, child] of Object.entries(value)) {
      flattenKeys(child, prefix ? `${prefix}.${key}` : key, keys, seen);
    }
    return;
  }
  if (prefix) keys.add(prefix);
}

function addDictionary(localeKeys, language, resource) {
  if (!isPlainObject(resource) || !localeKeys[language]) return;
  const keys = new Set();
  flattenKeys(resource, "", keys);
  for (const key of keys) localeKeys[language].add(key);
}

function ingestResource(localeKeys, resource, language) {
  if (!isPlainObject(resource)) return;
  if (isPlainObject(resource.en) || isPlainObject(resource.zh)) {
    if (isPlainObject(resource.en)) addDictionary(localeKeys, "en", resource.en);
    if (isPlainObject(resource.zh)) addDictionary(localeKeys, "zh", resource.zh);
    return;
  }
  if (language) {
    addDictionary(localeKeys, language, resource);
    return;
  }
  for (const key of ["resources", "translation", "messages"]) {
    if (isPlainObject(resource[key])) {
      ingestResource(localeKeys, resource[key], undefined);
      return;
    }
  }
}

function detectLanguage(file) {
  for (const part of file.split(/[\\/]/).reverse()) {
    const token = part.replace(/\.[^.]+$/, "").toLowerCase();
    if (token === "en" || token.startsWith("en-") || token.startsWith("en_")) return "en";
    if (token === "zh" || token.startsWith("zh-") || token.startsWith("zh_")) return "zh";
  }
  return null;
}

function ingestModule(localeKeys, module, file) {
  const language = detectLanguage(file);
  for (const [name, value] of Object.entries(module)) {
    if (name === "en" || name === "zh") {
      ingestResource(localeKeys, value, name);
    } else if (["default", "resources", "messages", "translation"].includes(name)) {
      ingestResource(localeKeys, value, language);
    } else if (isPlainObject(value) && (isPlainObject(value.en) || isPlainObject(value.zh))) {
      ingestResource(localeKeys, value, undefined);
    } else if (language && isPlainObject(value)) {
      ingestResource(localeKeys, value, language);
    }
  }
}

function weatherKeys(keys) {
  return [...keys]
    .filter((key) => key === "sources.weather" || key.startsWith("sources.weather."))
    .sort();
}

test("the form starts empty and does not synthesize a date, series, or HDD", () => {
  const originalNow = Date.now;
  let nowCalls = 0;
  Date.now = () => {
    nowCalls += 1;
    return originalNow();
  };
  let probe;
  try {
    probe = new MountedComponent(WeatherForecastEvidence, { t: (key) => key });
  } finally {
    Date.now = originalNow;
  }

  assert.equal(probe ? nowCalls : nowCalls, 0, "mount must not read the wall clock");
  assert.equal(requests.length, 0, "mount must not auto-submit a forecast request");
  assert.equal(stateOf(probe), "not-ready");

  const textareas = findAll(probe.tree, (node) => node.type === "textarea");
  assert.deepEqual(textareas.map((node) => node.props.value), ["", ""]);
  const textInputs = findAll(probe.tree, (node) => node.type === "input" && node.props.type === "text");
  assert.deepEqual(textInputs.map((node) => node.props.value), ["", "", ""]);
  const numberInput = findOne(probe.tree, (node) => node.type === "input" && node.props.type === "number");
  assert.equal(numberInput.props.value, "100");

  assert.equal(findOne(probe.tree, (node) => node.props?.["data-record"] === "weather-readings"), undefined);
  const initialText = textOf(probe.tree);
  assert.doesNotMatch(initialText, /\bHDD\b|heating[- ]degree/i);
  assert.doesNotMatch(initialText, /°C/);
});

test("A-B-A edits invalidate the result, abort the request, and stale completion cannot restore it", async () => {
  const probe = new MountedComponent(WeatherForecastEvidence, { t: (key) => key });
  fillRequired(probe);

  const firstSubmit = submit(probe);
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].input.seriesIds, ["series-a"]);
  requests[0].resolve(makeEnvelope([makeRow("obs-a", "series-a")]));
  await firstSubmit;
  assert.equal(stateOf(probe), "ready");
  assert.equal(rowId(probe), "obs-a");

  change(findAll(probe.tree, (node) => node.type === "textarea")[0], "series-b");
  assert.equal(stateOf(probe), "not-ready", "an input edit must invalidate the displayed result");
  assert.equal(rowId(probe), null);

  change(findAll(probe.tree, (node) => node.type === "textarea")[0], "series-a");
  assert.equal(stateOf(probe), "not-ready", "returning to the old input must not resurrect the result");

  const secondSubmit = submit(probe);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1].input.seriesIds, ["series-a"]);
  const abortedSignal = requests[1].input.signal;

  change(findAll(probe.tree, (node) => node.type === "textarea")[0], "series-b");
  assert.equal(abortedSignal.aborted, true, "editing while a request is in flight must abort it");
  assert.equal(stateOf(probe), "not-ready");

  const thirdSubmit = submit(probe);
  assert.equal(requests.length, 3);
  assert.deepEqual(requests[2].input.seriesIds, ["series-b"]);
  requests[2].resolve(makeEnvelope([makeRow("obs-b", "series-b")]));
  await thirdSubmit;
  assert.equal(stateOf(probe), "ready");
  assert.equal(rowId(probe), "obs-b");

  requests[1].resolve(makeEnvelope([makeRow("obs-a-stale", "series-a")]));
  await secondSubmit;
  assert.equal(stateOf(probe), "ready");
  assert.equal(rowId(probe), "obs-b", "a stale completion must not overwrite the newer result");
  assert.equal(findOne(probe.tree, (node) => node.props?.["data-record-id"] === "obs-a-stale"), undefined);

  change(findAll(probe.tree, (node) => node.type === "textarea")[0], "series-a");
  assert.equal(stateOf(probe), "not-ready", "the final A edit must invalidate the B result");
  assert.equal(rowId(probe), null);
  assert.equal(requests.length, 3, "input edits must not trigger implicit requests");
});

test("unmount aborts the in-flight forecast read", async () => {
  const probe = new MountedComponent(WeatherForecastEvidence, { t: (key) => key });
  fillRequired(probe);
  const pending = submit(probe);
  assert.equal(requests.length, 1);
  const signal = requests[0].input.signal;
  assert.equal(signal.aborted, false);

  probe.unmount();
  assert.equal(signal.aborted, true, "unmount must abort the active request");

  requests[0].resolve(makeEnvelope([makeRow("obs-after-unmount", "series-a")]));
  await pending;
  assert.equal(requests.length, 1);
});

test("an empty response is the empty state, not an absent or zero reading", async () => {
  const probe = new MountedComponent(WeatherForecastEvidence, { t: (key) => key });
  fillRequired(probe);
  const pending = submit(probe);
  requests[0].resolve(makeEnvelope([]));
  await pending;

  assert.equal(stateOf(probe), "empty");
  assert.equal(stateOf(probe) === "ready", false);
  assert.equal(stateOf(probe) === "not-ready", false);
  const empty = findOne(probe.tree, (node) => node.props?.["data-empty-state"] === "weather-readings");
  assert.ok(empty, "empty responses must render their own explicit state");
  assert.equal(findOne(probe.tree, (node) => node.props?.["data-record"] === "weather-readings"), undefined);
  assert.match(textOf(probe.tree), /ECMWF open data/);
});

test("SourceCenter mounts forecast evidence only for ECMWF and keys it by source id", () => {
  const ecmwf = makeSource();
  const ecmwfMarkup = renderToStaticMarkup(
    React.createElement(SourceCenter, sourceCenterProps(ecmwf)),
  );
  assert.match(ecmwfMarkup, /source-weather-evidence/);
  assert.match(ecmwfMarkup, /data-state="not-ready"/);

  const other = makeSource({
    source_id: "entsog-1",
    source_system: "ENTSOG",
    category: "flows",
  });
  const otherMarkup = renderToStaticMarkup(
    React.createElement(SourceCenter, sourceCenterProps(other)),
  );
  assert.doesNotMatch(otherMarkup, /source-weather-evidence/);

  const first = new MountedComponent(SourceCenter, sourceCenterProps(ecmwf));
  const firstEvidence = findOne(first.tree, (node) => node.type === WeatherForecastEvidence);
  assert.ok(firstEvidence, "ECMWF selection must mount WeatherForecastEvidence");
  assert.equal(firstEvidence.key, "ecmwf-1");

  const second = new MountedComponent(SourceCenter, sourceCenterProps(makeSource({ source_id: "ecmwf-2" })));
  const secondEvidence = findOne(second.tree, (node) => node.type === WeatherForecastEvidence);
  assert.ok(secondEvidence);
  assert.equal(secondEvidence.key, "ecmwf-2");

  const absent = new MountedComponent(SourceCenter, sourceCenterProps(other));
  assert.equal(findOne(absent.tree, (node) => node.type === WeatherForecastEvidence), undefined);
  assert.equal(requests.length, 0, "mounting SourceCenter must not issue a forecast request");
});

test("English and Chinese locale dictionaries keep identical keys", async () => {
  const allFiles = listFiles(webRoot);
  const localeFiles = allFiles.filter((file) => {
    const extension = extname(file).toLowerCase();
    if (![".json", ".ts", ".js"].includes(extension)) return false;
    const normalized = file.replaceAll("\\", "/");
    return /\/(?:locales?|i18n|translations?)\//i.test(normalized)
      || /\/(?:locales?|i18n|translations?)\.(?:json|ts|js)$/i.test(normalized)
      || /\/(?:en|zh)(?:[-_.][^/]*)?\.(?:json|ts|js)$/i.test(normalized);
  });
  assert.ok(localeFiles.length > 0, "expected locale dictionaries under clients/web");

  const localeKeys = { en: new Set(), zh: new Set() };
  for (const file of localeFiles) {
    if (extname(file).toLowerCase() === ".json") {
      const source = readFileSync(file, "utf8").replace(/^\uFEFF/, "");
      ingestResource(localeKeys, JSON.parse(source), detectLanguage(file));
      continue;
    }
    const moduleId = `/${relative(webRoot, file).replaceAll("\\", "/")}`;
    try {
      const module = await server.ssrLoadModule(moduleId);
      ingestModule(localeKeys, module, file);
    } catch (error) {
      if (detectLanguage(file)) {
        throw new Error(`failed to load locale module ${moduleId}: ${error.message}`);
      }
    }
  }

  assert.ok(localeKeys.en.size > 0, "expected an English locale dictionary");
  assert.ok(localeKeys.zh.size > 0, "expected a Chinese locale dictionary");
  const englishWeather = weatherKeys(localeKeys.en);
  const chineseWeather = weatherKeys(localeKeys.zh);
  assert.equal(englishWeather.length, 40, "expected 40 English weather keys");
  assert.equal(chineseWeather.length, 40, "expected 40 Chinese weather keys");
  assert.ok(
    englishWeather.includes("sources.weather.title"),
    "the English dictionary must contain the weather evidence title",
  );

  const missingFromZh = [...localeKeys.en].filter((key) => !localeKeys.zh.has(key)).sort();
  const missingFromEn = [...localeKeys.zh].filter((key) => !localeKeys.en.has(key)).sort();
  assert.deepEqual(missingFromZh, [], "Chinese locale is missing English keys");
  assert.deepEqual(missingFromEn, [], "English locale is missing Chinese keys");
});
