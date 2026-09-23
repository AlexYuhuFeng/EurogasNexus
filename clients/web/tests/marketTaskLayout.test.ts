/**
 * The market shell's layout must follow the task it displays, not only the page the URL named.
 *
 * Browser review found the Market Overview -> Network tab rendering under `workspace-market`, so
 * every `.workspace-network` rule - the ones that give the map column its height and show its
 * stage - never matched. These are resolver and wiring contracts; computed style and geometry are
 * the browser sweep's to measure.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  layoutWorkspacePage,
  marketTaskWorkspacePage,
  resolveMarketViewTask,
} from "../src/app/context/viewPreference.ts";
import {
  DEFAULT_MARKET_TASK,
  MARKET_TASKS,
} from "../src/app/model/marketCockpitModel.ts";
import { primaryWorkspaceForPage } from "../src/app/navigation/productNavigation.ts";
import {
  isWorkspacePageId,
  workspaceTaskSearch,
  workspacePageIds,
  type WorkspacePageId,
} from "../src/workspaceNavigation.ts";

const ROOT = new URL("../", import.meta.url);
const SRC = fileURLToPath(new URL("src", ROOT));

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`src/${relativePath}`, ROOT), "utf8");
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true, recursive: true })
    .filter(
      (entry) =>
        entry.isFile() && (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")),
    )
    .map((entry) => path.join(entry.parentPath ?? directory, entry.name))
    .sort();
}

/** The task a location resolves to, and the layout page that composition takes. */
function layoutFor(input: {
  activeWorkspace: WorkspacePageId;
  search: string;
  persisted?: "curves" | "network" | null;
}): { task: string; page: WorkspacePageId } {
  const task = resolveMarketViewTask({
    search: input.search,
    activeWorkspace: input.activeWorkspace,
    persisted: input.persisted ?? null,
  }).task;
  return { task, page: layoutWorkspacePage({ activeWorkspace: input.activeWorkspace, task }) };
}

test("every market task composes on a market page that resolves the same task back", () => {
  assert.deepEqual(MARKET_TASKS, ["overview", "curves", "network", "capacity"]);
  assert.equal(DEFAULT_MARKET_TASK, "curves");

  for (const task of MARKET_TASKS) {
    const page = marketTaskWorkspacePage(task);
    assert.ok(isWorkspacePageId(page), `${task} composes on a declared page`);
    assert.equal(primaryWorkspaceForPage(page).id, "market", `${task} -> ${page}`);
    // The page's own deep link has to land on the same task, or the layout and the view disagree.
    assert.deepEqual(
      resolveMarketViewTask({
        search: `?workspace=${page}&task=${task}`,
        activeWorkspace: page,
        persisted: null,
      }).task,
      task,
      `${page} renders the ${task} task`,
    );
  }

  // The map's layout lives under `.workspace-network`, never under the market shell.
  assert.equal(marketTaskWorkspacePage("network"), "network");
  assert.equal(marketTaskWorkspacePage("capacity"), "capacity");
  assert.equal(marketTaskWorkspacePage("curves"), "market");
  assert.equal(marketTaskWorkspacePage("overview"), "market");
});

test("the direct deep link, the task URL, the tab switch and the persisted view agree", () => {
  // 1. The direct map-first deep link.
  assert.deepEqual(layoutFor({ activeWorkspace: "network", search: "?workspace=network" }), {
    task: "network",
    page: "network",
  });

  // 2. The second entry path from the browser review: the market shell with an explicit task.
  assert.deepEqual(
    layoutFor({ activeWorkspace: "market", search: "?workspace=market&task=network" }),
    { task: "network", page: "network" },
  );

  // 3. The tab switch: the URL `openTask("network")` writes through the navigation hook, with the
  //    trader/selection context keys carried.
  const context = "?gasDay=2026-09-07&hub=TTF&route=route-1";
  const mapTabUrl = workspaceTaskSearch(context, "market", "network");
  assert.deepEqual(layoutFor({ activeWorkspace: "market", search: `?${mapTabUrl}` }), {
    task: "network",
    page: "network",
  });
  const backUrl = new URLSearchParams(workspaceTaskSearch(`?${mapTabUrl}`, "market", "curves"));
  assert.equal(backUrl.get("gasDay"), "2026-09-07");
  assert.equal(backUrl.get("hub"), "TTF");
  assert.equal(backUrl.get("route"), "route-1");
  assert.deepEqual(layoutFor({ activeWorkspace: "market", search: `?${backUrl.toString()}` }), {
    task: "curves",
    page: "market",
  });

  // 4. The persisted per-user view, with no task in the URL, and the numeric fallback.
  assert.deepEqual(
    layoutFor({ activeWorkspace: "market", search: "?workspace=market", persisted: "network" }),
    { task: "network", page: "network" },
  );
  assert.deepEqual(
    layoutFor({ activeWorkspace: "market", search: "?workspace=market", persisted: "curves" }),
    { task: "curves", page: "market" },
  );
  assert.deepEqual(
    layoutFor({ activeWorkspace: "market", search: "?workspace=market", persisted: null }),
    { task: "curves", page: "market" },
  );
  assert.deepEqual(layoutFor({ activeWorkspace: "market", search: "" }), {
    task: "curves",
    page: "market",
  });
});

test("only the market primary takes its layout from a task", () => {
  for (const page of workspacePageIds) {
    const primary = primaryWorkspaceForPage(page).id;
    for (const task of MARKET_TASKS) {
      const layoutPage = layoutWorkspacePage({ activeWorkspace: page, task });
      if (primary === "market") {
        assert.equal(primaryWorkspaceForPage(layoutPage).id, "market", `${page}/${task}`);
      } else {
        // A task in the URL of another primary cannot move that page's layout class.
        assert.equal(layoutPage, page, `${page}/${task}`);
      }
    }
  }
});

test("one resolution feeds both the layout class and the rendered task", () => {
  const shell = readWebSource("app/shell/AppShell.tsx");
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  const controller = readWebSource("app/hooks/useAppController.ts");

  assert.match(shell, /className=\{`app cockpit-app workspace-\$\{layoutPage\}`\}/);
  assert.match(
    shell,
    /const layoutPage = layoutWorkspacePage\(\{\s*activeWorkspace: navigation\.activeWorkspace,\s*task: marketView\.task,/,
  );
  assert.match(cockpit, /const \{ task, rememberTask \} = marketView;/);
  assert.match(controller, /const marketView = useMarketViewPreference\(\{/);

  // One resolution, not a second copy of the per-principal preference: the hook is called in the
  // controller, and nowhere else in the client.
  const callers = sourceFiles(SRC)
    .filter((file) => readFileSync(file, "utf8").includes("useMarketViewPreference({"))
    .map((file) => path.basename(file));
  assert.deepEqual(callers, ["useAppController.ts"]);
});
