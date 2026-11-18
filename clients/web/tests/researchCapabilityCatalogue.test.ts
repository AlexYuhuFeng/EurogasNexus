/**
 * The research capability catalogue (slice E of the D3 decision).
 *
 * `GET /api/research/capabilities` declares what the research domain can do and the posture each
 * capability carries. The route had no consumer, so the declaration that makes a research figure
 * checkable - which capability produced it, whether that capability may change anything, what it
 * needed to be allowed - was invisible in the product.
 *
 * These tests hold the rows to the route's own payload and hold the panel to the posture
 * vocabulary, including the case where the deployment names a posture this build does not know.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  readWriteClassKey,
  researchCapabilityRows,
  sideEffectClassKey,
} from "../src/app/model/accessCatalogueModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const PAYLOAD = [
  {
    name: "series.read_observations",
    description: "Read observations for a series as of a cutoff.",
    read_write_class: "read",
    deterministic: true,
    side_effect_class: "none",
    required_permission: "research.read",
    provenance_behavior: "returns_source_references",
  },
  {
    name: "dataset.build",
    description: "Materialise a dataset from a validated spec.",
    read_write_class: "write_materialized",
    deterministic: false,
    side_effect_class: "persists_snapshot",
    required_permission: "research.write",
    provenance_behavior: "returns_snapshot_id",
  },
];

test("the rows are the route's payload, ordered so two reads render the same way", () => {
  const rows = researchCapabilityRows(PAYLOAD);
  assert.deepEqual(
    rows.map((row) => row.name),
    ["dataset.build", "series.read_observations"],
  );
  // Every declared field survives the mapping: a catalogue that dropped the posture would be a
  // list of names, which is exactly what the surface could already guess at.
  assert.deepEqual(rows[1], {
    name: "series.read_observations",
    description: "Read observations for a series as of a cutoff.",
    readWriteClass: "read",
    deterministic: true,
    sideEffectClass: "none",
    requiredPermission: "research.read",
    provenanceBehavior: "returns_source_references",
  });
  assert.equal(rows[0].deterministic, false);
});

test("an absent catalogue is no catalogue, never a fabricated row", () => {
  // The route always answers with a list; a missing one is a missing fact, so the surface shows
  // its empty statement rather than inventing capabilities the deployment never declared.
  assert.deepEqual(researchCapabilityRows(null), []);
  assert.deepEqual(researchCapabilityRows([]), []);
});

test("a declared posture becomes words, and an unknown one stays the deployment's own token", () => {
  assert.equal(readWriteClassKey("read"), "research.capabilities.class_read");
  assert.equal(
    readWriteClassKey("read_only_compute"),
    "research.capabilities.class_read_only_compute",
  );
  assert.equal(readWriteClassKey("write_materialized"), "research.capabilities.class_write_materialized");
  assert.equal(readWriteClassKey("export"), "research.capabilities.class_export");
  assert.equal(sideEffectClassKey("none"), "research.capabilities.side_effect_none");
  assert.equal(
    sideEffectClassKey("persists_snapshot"),
    "research.capabilities.side_effect_persists_snapshot",
  );
  assert.equal(
    sideEffectClassKey("persists_definition"),
    "research.capabilities.side_effect_persists_definition",
  );

  // A posture a newer backend declares is not blanked and not guessed at: the surface falls back
  // to the token the deployment sent, so the reader still sees that something was declared.
  assert.equal(readWriteClassKey("streams_to_broker"), null);
  assert.equal(sideEffectClassKey("mutates_ledger"), null);
});
