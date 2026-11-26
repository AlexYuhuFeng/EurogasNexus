import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { auditActionLabel, auditActorLabel, auditOutcomeLabel, auditResourceLabel } from "../src/app/model/auditPresentation.ts";
import { dependencyDetailText } from "../src/app/model/runtimeDependencyDetail.ts";

function translator(locale: "en" | "zh") {
  const table = JSON.parse(readFileSync(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf8")) as Record<string, string>;
  return (key: string, options?: Record<string, unknown>) => {
    const text = table[key];
    if (text === undefined) return (options?.defaultValue as string | undefined) ?? key;
    return text.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));
  };
}

const en = translator("en");
const zh = translator("zh");
const names = new Map([["principal-4c67", "Test risk manager"]]);

test("an audit action reads as words, written or composed, in both languages", () => {
  assert.equal(auditActionLabel("auth.local.login", en, "en"), "Signed in");
  assert.equal(auditActionLabel("auth.local.login", zh, "zh-CN"), "登录");
  // No written phrase: composed from its words, never the dotted code.
  assert.equal(auditActionLabel("lng.terminal_terms.update", en, "en"), "LNG terminal terms update");
  assert.equal(auditActionLabel("lng.terminal_terms.update", zh, "zh-CN"), "LNG接收站条款更新");
  // A word the dictionary does not know is kept as written.
  assert.equal(auditActionLabel("widget.frobnicate", en, "en"), "Widget frobnicate");
  assert.equal(auditActionLabel("", en, "en"), "–");
});

test("outcome, resource and actor read as words, naming people", () => {
  assert.equal(auditOutcomeLabel("listed", en, "en"), "Viewed");
  assert.equal(auditOutcomeLabel("denied", zh, "zh-CN"), "被拒绝");
  assert.equal(auditResourceLabel("identity_principal:principal-4c67", en, "en", names), "user · Test risk manager");
  assert.equal(auditResourceLabel("job:job-cdb7", en, "en", names), "job");
  assert.equal(auditActorLabel("principal-4c67", names), "Test risk manager");
  assert.equal(auditActorLabel("demo-start", names), "demo-start");
});

test("a dependency note is translated from its code, or from an older server's English", () => {
  assert.equal(dependencyDetailText({ state: "AVAILABLE", detail: "schema ok", detail_code: "schema_ok" }, zh), "所有数据表齐全");
  assert.equal(dependencyDetailText({ state: "UNKNOWN", detail: "no heartbeat recorded" }, en), "Has not reported yet");
  assert.equal(dependencyDetailText({ state: "AVAILABLE", age_seconds: 600, detail_code: "heartbeat_age" }, en), "Last reported 10 min ago");
  assert.equal(dependencyDetailText({ state: "UNAVAILABLE", detail: "OperationalError", detail_code: "database_error" }, en), "The database did not answer");
  assert.equal(dependencyDetailText({ state: "X", detail: "something new" }, en), "something new");
  assert.equal(dependencyDetailText(undefined, en), "–");
});
