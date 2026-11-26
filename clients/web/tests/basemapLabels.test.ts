/**
 * Basemap place names: Chinese shows one variant, never "德国/德國"; English is unchanged.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { basemapName, basemapNameExpression } from "../src/app/basemapLabels.ts";

const germany = {
  name: "Germany",
  "name:en": "Germany",
  "name:zh": "德国/德國",
  "name:zh-Hans": "德国",
  "name:zh-Hant": "德國",
};

test("Chinese prefers name:zh-Hans and never joins two variants", () => {
  assert.equal(basemapName(germany, "zh"), "德国");
  assert.equal(basemapName({ name: "Germany", "name:en": "Germany", "name:zh": "德国/德國" }, "zh-CN"), "Germany");
  assert.equal(basemapName({ name: "Netherlands", "name:en": "Netherlands", "name:zh": "荷兰" }, "zh"), "荷兰");
  // The traditional name merely repeated in name:zh-Hant is a duplicate, so English is used.
  assert.equal(
    basemapName({ name: "Netherlands", "name:en": "Netherlands", "name:zh": "荷蘭", "name:zh-Hant": "荷蘭" }, "zh"),
    "Netherlands",
  );
  assert.equal(basemapName({ name: "Nederland", "name:latin": "Nederland" }, "zh"), "Nederland");
});

test("English and other languages use name:en, then Latin, then name", () => {
  assert.equal(basemapName(germany, "en"), "Germany");
  assert.equal(basemapName({ name: "Deutschland", "name:latin": "Deutschland" }, "en"), "Deutschland");
  assert.equal(basemapName({ name: "Deutschland" }, "en"), "Deutschland");
  assert.equal(basemapName({}, "en"), null);
});

test("the MapLibre expression mirrors the same order", () => {
  const chinese = JSON.stringify(basemapNameExpression("zh"));
  assert.match(chinese, /name:zh-Hans/);
  assert.match(chinese, /name:zh-Hant/);
  assert.match(chinese, /index-of/);
  assert.match(chinese, /name:en/);
  // No concatenation expression: a joined variant is exactly what must not be drawn.
  assert.doesNotMatch(chinese, /"concat"/);
  const english = JSON.stringify(basemapNameExpression("en"));
  assert.match(english, /name:en/);
  assert.doesNotMatch(english, /name:zh/);
});
