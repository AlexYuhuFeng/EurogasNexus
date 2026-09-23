/**
 * A component's hooks must not depend on the identity transition (shell half).
 *
 * The browser logged React's `Internal React error: Expected static flag was missing` once per
 * application mount, on every workspace, with no component stack. Its cause was in `AppShell`:
 * the release-compatibility guard and the identity gate returned *before* `useInspectorStore()`
 * and `useCommandPalette()`, so the same component instance rendered with no hooks while the
 * identity was unresolved and with both of them after a successful sign-in. React reported that
 * changed hook list on exactly the sign-in transition - and a hook list that depends on which
 * render produced it is a defect whether or not React complains about it.
 *
 * The rule is checked structurally rather than by memory: in every component in the client, no
 * hook call may follow an early return in that component's own body. The identity gate keeps its
 * early return; the hooks moved into the component the gate mounts.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const ROOT = new URL("../", import.meta.url);
const SRC = fileURLToPath(new URL("src", ROOT));

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`src/${relativePath}`, ROOT), "utf8");
}

function tsxFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".tsx"))
    .map((entry) => path.join(entry.parentPath ?? directory, entry.name))
    .sort();
}

function hookName(node: ts.Expression): string | null {
  if (ts.isCallExpression(node)) {
    return hookName(node.expression);
  }
  if (ts.isIdentifier(node) && /^use[A-Z]/.test(node.text)) return node.text;
  if (ts.isPropertyAccessExpression(node) && /^use[A-Z]/.test(node.name.text)) {
    return node.name.text;
  }
  return null;
}

/** Hook calls made directly by one statement of a component body. */
function hooksInStatement(statement: ts.Statement): string[] {
  if (ts.isExpressionStatement(statement)) {
    const hook = hookName(statement.expression);
    return hook ? [hook] : [];
  }
  if (ts.isVariableStatement(statement)) {
    return statement.declarationList.declarations.flatMap((declaration) =>
      declaration.initializer ? (hookName(declaration.initializer) ?? []) : [],
    );
  }
  return [];
}

function returnsFrom(statement: ts.Statement): boolean {
  if (ts.isReturnStatement(statement)) return true;
  if (ts.isBlock(statement)) return statement.statements.some(returnsFrom);
  if (ts.isIfStatement(statement)) {
    return (
      returnsFrom(statement.thenStatement) ||
      (statement.elseStatement !== undefined && returnsFrom(statement.elseStatement))
    );
  }
  return false;
}

interface ComponentScan {
  readonly file: string;
  readonly name: string;
  readonly hooks: string[];
  readonly hooksAfterEarlyReturn: { hook: string; line: number; returnLine: number }[];
}

function componentName(node: ts.FunctionLikeDeclaration, source: ts.SourceFile): string {
  if (node.name && ts.isIdentifier(node.name)) return node.name.text;
  const parent = node.parent;
  if (parent && ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) {
    return parent.name.text;
  }
  return `${path.basename(source.fileName)}:${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}`;
}

function scanComponents(): ComponentScan[] {
  const scans: ComponentScan[] = [];
  for (const file of tsxFiles(SRC)) {
    const source = ts.createSourceFile(
      file,
      readFileSync(file, "utf8"),
      ts.ScriptTarget.ES2022,
      true,
      ts.ScriptKind.TSX,
    );
    const visit = (node: ts.Node): void => {
      if (
        (ts.isFunctionDeclaration(node) ||
          ts.isFunctionExpression(node) ||
          ts.isArrowFunction(node)) &&
        node.body &&
        ts.isBlock(node.body)
      ) {
        const hooks: string[] = [];
        const hooksAfterEarlyReturn: ComponentScan["hooksAfterEarlyReturn"] = [];
        let earlyReturn: ts.Statement | null = null;
        for (const statement of node.body.statements) {
          const statementHooks = hooksInStatement(statement);
          if (statementHooks.length > 0) {
            hooks.push(...statementHooks);
            if (earlyReturn) {
              for (const hook of statementHooks) {
                hooksAfterEarlyReturn.push({
                  hook,
                  line: source.getLineAndCharacterOfPosition(statement.getStart(source)).line + 1,
                  returnLine: source.getLineAndCharacterOfPosition(earlyReturn.getStart(source)).line + 1,
                });
              }
            }
          }
          if (ts.isReturnStatement(statement)) earlyReturn = earlyReturn ?? statement;
          if (ts.isIfStatement(statement) && returnsFrom(statement.thenStatement)) {
            earlyReturn = earlyReturn ?? statement;
          }
        }
        scans.push({
          file: path.relative(SRC, file).split(path.sep).join("/"),
          name: componentName(node, source),
          hooks,
          hooksAfterEarlyReturn,
        });
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
  }
  return scans;
}

test("no component calls a hook after an early return in its own body", () => {
  const offenders = scanComponents()
    .filter((scan) => scan.hooksAfterEarlyReturn.length > 0)
    .map((scan) => ({
      file: scan.file,
      name: scan.name,
      hooks: scan.hooksAfterEarlyReturn,
    }));

  assert.deepEqual(
    offenders,
    [],
    "a hook behind a guard renders a different hook list depending on the state that guard reads",
  );
});

test("the identity gate returns before the hooks, and the component it mounts owns them", () => {
  const scans = scanComponents();
  const appShell = scans.filter((scan) => scan.name === "AppShell");
  const authenticated = scans.filter((scan) => scan.name === "AuthenticatedShell");

  // The gate itself is hook-free, so nothing about the identity state can reorder hooks that
  // belong to the terminal.
  assert.equal(appShell.length, 1, "AppShell is one component");
  assert.deepEqual(appShell[0].hooks, [], "AppShell calls no hooks before its gates return");

  assert.equal(authenticated.length, 1, "the gate mounts exactly one authenticated shell");
  assert.ok(authenticated[0].hooks.includes("useInspectorStore"));
  assert.ok(authenticated[0].hooks.includes("useCommandPalette"));

  // The gate still gates: the terminal is mounted only for a confirmed identity, so moving the
  // hooks did not move the boundary.
  const shell = readWebSource("app/shell/AppShell.tsx");
  const gate = /if \(api\.authState !== "authenticated"\) \{[\s\S]*?<SignInScreen[\s\S]*?\n  \}/.exec(shell)?.[0];
  assert.ok(gate, "the identity gate returns before the terminal mounts");
  assert.match(shell, /\n\n  return <AuthenticatedShell controller=\{controller\} \/>;/);
  assert.ok(
    shell.indexOf('if (api.authState !== "authenticated")') <
      shell.indexOf("return <AuthenticatedShell controller={controller} />;"),
  );
});
