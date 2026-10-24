import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

// Execute the panel's actual async mutation function with controlled network
// completion, without replacing its guards with a parallel test implementation.
const source = readFileSync(new URL("../src/components/DecisionCasePanel.tsx", import.meta.url), "utf8");
const ast = ts.createSourceFile("panel.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function functionSource(name: string): string {
  let found: ts.FunctionDeclaration | undefined;
  function visit(node: ts.Node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node;
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.ok(found, name);
  return found.getText(ast);
}
function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness() {
  const writes: Array<[string, unknown]> = [];
  const selectionEpoch = { current: 0 };
  const context = vm.createContext({
    selectionEpoch,
    setBusy: (value: boolean) => writes.push(["busy", value]),
    setErrorText: (value: unknown) => writes.push(["error", value]),
    setSelected: (value: unknown) => writes.push(["selected", value]),
    withPack: async (value: unknown) => value,
    refresh: async (isCurrent: () => boolean) => { if (isCurrent()) writes.push(["refresh", true]); },
    explainError: (error: Error) => error.message,
    t: (key: string) => key,
  });
  const compiled = ts.transpileModule(functionSource("run"), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInContext(compiled, context);
  return { writes, selectionEpoch, run: context.run as (operation: () => Promise<unknown>) => Promise<boolean | undefined> };
}

test("a mutation completing after A to B to A cannot replace the new selection or release its busy state", async () => {
  const h = harness();
  const network = deferred();
  const pending = h.run(() => network.promise);
  h.selectionEpoch.current += 2;
  network.resolve({ data: { case_id: "A", evidence: ["old"] } });
  assert.equal(await pending, false);
  assert.deepEqual(h.writes, [["busy", true], ["error", null]]);
});

test("a stale mutation failure cannot report an error or release another case's busy state", async () => {
  const h = harness();
  const network = deferred();
  const pending = h.run(() => network.promise);
  h.selectionEpoch.current += 1;
  network.reject(new Error("old failure"));
  await pending;
  assert.deepEqual(h.writes, [["busy", true], ["error", null]]);
});

test("current success returns confirmation for draft clearing and current failure releases busy", async () => {
  const h = harness();
  assert.equal(await h.run(async () => ({ data: "updated" })), true);
  assert.deepEqual(h.writes.slice(-3), [["selected", "updated"], ["refresh", true], ["busy", false]]);
  await h.run(async () => { throw new Error("current failure"); });
  assert.deepEqual(h.writes.slice(-2), [["error", "current failure"], ["busy", false]]);
});
