import { useCallback, useEffect, useRef, useState } from "react";
import { CommandPalette } from "@/components/CommandPalette";
import { InspectorPanel } from "@/components/InspectorPanel";
import { RestrictedSurface } from "@/components/RestrictedSurface";
import { SignInScreen } from "@/components/SignInScreen";
import { MfaEnrolment } from "@/components/MfaEnrolment";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import { ShellTicker } from "@/components/ShellTicker";
import { DataProblemNotice } from "@/components/DataProblemNotice";
import { ConnectionNotice } from "@/components/ConnectionNotice";
import { aiAvailabilityOf } from "@/app/model/aiAvailability";
import { startConnectionWatch, useScreenFreshness } from "@/app/data/connection";
import { DeskBriefDialog, openDeskBrief } from "@/components/DeskBriefDialog";
import type { AppController } from "@/app/hooks/useAppController";
import { useCommandPalette } from "@/app/hooks/useCommandPalette";
import { useAnswerBar } from "@/app/hooks/useAnswerBar";
import type { AnswerTarget } from "@/app/answer/answerModel";
import {
  describeEndpointFailures,
  describeEndpointRetry,
} from "@/app/model/endpointFailures";
import {
  compositionFromProfile,
  compositionSeesAdministration,
} from "@/app/experience/experienceProfile";
import type { PaletteCommand } from "@/app/experience/commandPalette";
import { commandById, glossaryCommands, paletteLabel, paletteUnavailableReasonKey } from "@/app/experience/commandPalette";
import { PAGE_VIEW_REGISTRY, viewToSearch } from "@/app/navigation/viewRegistry";
import { isCommercialPage, isControlPlanePage } from "@/app/navigation/productNavigation";
import { needsCommercialWorkspaceReads } from "@/stores/workspaceReadScope";
import {
  modeLanding,
  modeLocationFromSearch,
  modeTaskVisible,
  visibleModes,
} from "@/app/navigation/modeNavigation";
import { workspaceFromLocation } from "@/app/hooks/useWorkspaceNavigation";
import { inspectorDetailFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import { WorkspaceRenderer } from "@/app/workspaces/WorkspaceRenderer";
import { usePageEnter } from "@/app/shell/usePageEnter";
import { PanelErrorBoundary } from "@/components/PanelErrorBoundary";
import { isBlockingCompatibility } from "@/app/releaseCompatibility";
import { changeAppLanguage } from "@/i18n";
import { loadRemotePreferences, saveRemotePreference } from "@/app/preferences/remotePreferences";
import type { ThemeMode } from "@/stores/theme";
import { layoutWorkspacePage } from "@/app/context/viewPreference";
import { requestProblemReport } from "@/app/model/supportReport";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { useWideContent } from "@/app/shell/useWideContent";
import { FirstRunSetupGate } from "@/components/FirstRunSetup";
import { useTimePreferenceStore } from "@/stores/timePreference";
import { invalidateReads, setReadCacheScope, useCachedRead } from "@/app/data/readCache";
import { CARGO_BOARD_KEY, readCargoBoard } from "@/app/hooks/useCargoBoard";
import { onApiWrite } from "@/api/client";

import { scrollMemoryKey, useScrollMemory } from "@/app/shell/useScrollMemory";
import { navigationKeyFor, useNavigationKeyStore } from "@/app/shell/navigationKey";

// Any write through the API client marks the kept read answers stale.
onApiWrite(invalidateReads);

interface AppShellProps {
  controller: AppController;
}

export function AppShell({ controller }: AppShellProps) {
  const {
    t,
    i18n,
    api,
    theme,
    navigation,
    traderContext,
    selection,
    controls,
    portfolio,
    sources,
  } = controller;

  const compatibility = api.releaseCompatibility;
  const blockingCompatibility = compatibility && isBlockingCompatibility(compatibility.state);
  if (blockingCompatibility && compatibility) {
    return (
      <div className="release-compatibility-blocker" role="alert">
        <div className="release-compatibility-card">
          <span className="eyebrow">{t("release.compat_blocked_eyebrow")}</span>
          <h1>{t(compatibility.messageKey)}</h1>
          <p>{t("release.compat_blocked_body")}</p>
          <dl className="release-compatibility-facts">
            <div><dt>{t("release.client_version")}</dt><dd>{compatibility.clientVersion}</dd></div>
            <div><dt>{t("release.server_version")}</dt><dd>{compatibility.serverVersion}</dd></div>
            <div>
              <dt>{t("release.min_supported_client")}</dt>
              <dd>{compatibility.minimumSupportedClient ?? t("release.not_reported")}</dd>
            </div>
            <div>
              <dt>{t("release.api_contract")}</dt>
              <dd>{compatibility.apiContractVersion ?? t("release.not_reported")}</dd>
            </div>
          </dl>
          <button type="button" className="button-primary" onClick={() => window.location.reload()}>
            {t("release.compat_retry")}
          </button>
        </div>
      </div>
    );
  }

  // Authentication-first entry: the terminal, its panels and every protected
  // read stay unmounted until the backend confirms the identity. This holds on
  // reload, on deep links and after history navigation, because the store's
  // authState - not the URL - decides what may mount.
  //
  // The authenticated shell is its own component on purpose: the hooks below
  // used to be called in this body after this return, so the same instance
  // rendered with a hook list that depended on the auth state, and React
  // reported that as `Internal React error: Expected static flag was missing`
  // on the sign-in transition.
  if (api.authState !== "authenticated") {
    return (
      <SignInScreen
        t={t}
        authState={api.authState}
        authStatus={api.authStatus}
        authErrorKey={api.authErrorKey}
        authNoticeKey={api.authNoticeKey}
        authBusy={api.authBusy}
        language={i18n.language}
        onLanguageChange={(language) => void changeAppLanguage(language)}
        onOidcSignIn={() => void api.signIn()}
        onDevLogin={(username, password) => void api.login(username, password)}
        onRetryIdentity={() => void api.bootstrapIdentity()}
        passwordChange={api.passwordChange}
        passwordChangeErrorKey={api.passwordChangeErrorKey}
        onCompletePasswordChange={(newPassword) => void api.completePasswordChange(newPassword)}
        onCancelPasswordChange={() => api.cancelPasswordChange()}
        mfaStep={api.mfaStep}
        mfaErrorKey={api.mfaErrorKey}
        onCompleteMfa={(code, recovery) => void api.completeMfa(code, recovery)}
        onCancelMfa={() => api.cancelMfa()}
      />
    );
  }

  // The policy requires a second factor this person has not set up: the server answers
  // nothing else until they enrol (security review H6), so the shell shows only the enrolment.
  if (api.mfaEnrolmentRequired) {
    return <MfaEnrolment t={t} onDone={() => void api.finishMfaEnrolment()} onSignOut={() => void api.signOut()} />;
  }

  return <AuthenticatedShell controller={controller} />;
}

interface AuthenticatedShellProps {
  controller: AppController;
}

/**
 * The authenticated terminal: one shell for every page, composed only once the
 * backend confirmed the identity. Every hook in this component runs on every
 * render of it (it mounts when the gate opens and unmounts when it closes), so
 * the sign-in transition changes which component is mounted rather than the
 * number of hooks one component calls.
 */
function AuthenticatedShell({ controller }: AuthenticatedShellProps) {
  // One answer for the whole screen: is it current (app/data/connection.ts, small-desk 3.7).
  const screenFreshness = useScreenFreshness();
  useEffect(() => startConnectionWatch(), []);
  const {
    t,
    i18n,
    api,
    theme,
    navigation,
    marketView,
    traderContext,
    selection,
    controls,
    portfolio,
    sources,
  } = controller;
  // One entrance per page change, on the page container (UX R10).
  const mainRef = useRef<HTMLElement>(null);
  usePageEnter(mainRef, navigation.activeWorkspace);

  // The one bounded failure model. Loader keys and backend messages stay in the store: only
  // translated endpoint labels, safe failure messages and one "showing N of M" summary are
  // rendered (status panel, notice), so nothing leaks internals or grows past five rows.
  const endpointFailures = describeEndpointFailures(api.endpointErrors, api.endpointErrorCodes, t);
  const endpointRetry = describeEndpointRetry(
    {
      busy: api.endpointRetryBusy,
      attempts: api.endpointRetryAttempts,
      lastAttemptAtUtc: api.endpointRetryLastAttemptAtUtc,
    },
    t,
  );

  // Architecture V2 control-plane boundary: a page that belongs to the
  // administration surface is refused for an identity without an administration
  // capability, instead of mounting a surface whose requests the backend will
  // reject. Navigation is not a security boundary; this is honest presentation.
  // Personal preferences follow the principal across clients and offices: load the server
  // copy once per signed-in identity. A failed read keeps the browser's local copy.
  const principalId = api.currentUser?.principal_id ?? null;
  useEffect(() => {
    if (principalId) void loadRemotePreferences(principalId);
  }, [principalId]);
  // Back on a page or task, the reader is where they left it.
  useScrollMemory(scrollMemoryKey(typeof window === "undefined" ? "" : window.location.search));
  // Floating surfaces (Popover, Dialog, Sheet) close when the place changes (navigationKey.ts).
  const navigationPlace = navigationKeyFor(typeof window === "undefined" ? "" : window.location.search);
  useEffect(() => {
    useNavigationKeyStore.getState().setKey(navigationPlace);
  }, [navigationPlace]);
  useEffect(() => {
    // A sub-view written by replaceState + popstate (administration views) is a move too.
    const follow = () => useNavigationKeyStore.getState().setKey(navigationKeyFor(window.location.search));
    window.addEventListener("popstate", follow);
    return () => window.removeEventListener("popstate", follow);
  }, []);

  // Kept answers belong to one principal: another identity starts from an empty read cache.
  setReadCacheScope(principalId);
  const chooseLanguage = (language: string) => {
    void changeAppLanguage(language);
    saveRemotePreference("language", language);
  };
  const chooseTheme = (mode: ThemeMode) => {
    theme.setMode(mode);
    saveRemotePreference("theme", mode);
  };

  const composition = compositionFromProfile(api.currentUser?.experience);
  const controlPlaneRestricted =
    isControlPlanePage(navigation.activeWorkspace) &&
    !compositionSeesAdministration(composition);
  // An administrator without a commercial role lands on, or deep-links into, a business page:
  // take them to their own surface instead of mounting panels whose every read is refused.
  const commercialRestricted =
    api.currentUser !== null &&
    isCommercialPage(navigation.activeWorkspace) &&
    !needsCommercialWorkspaceReads(api.currentUser);
  const ownSurface = compositionSeesAdministration(composition) ? "sources" : "settings";
  const openWorkspace = navigation.openWorkspace;
  const profileReady = composition.available;
  useEffect(() => {
    // Wait for the identity profile: it decides whether the own surface is administration.
    // Judge by the page the URL asks for, not the page still on screen: right after sign-in
    // the shell shows the default page for a moment before it applies the deep link, and
    // redirecting on that would drop an administrator's link to Access or Settings.
    if (!commercialRestricted || !profileReady) return;
    // Reading the location can itself resolve the persona home into the URL (the identity
    // profile arrives after the first render at sign-in): follow it, or the business page that
    // rendered first stays on screen as a restriction while the URL already names Access.
    const requested = workspaceFromLocation();
    openWorkspace(isCommercialPage(requested) ? ownSurface : requested);
  }, [commercialRestricted, profileReady, ownSurface, openWorkspace]);

  // A mode task the caller's role cannot use is absent, never an error page: a link to one opens
  // the first task of the same mode the role can use (or the first mode it can). Composition only;
  // the backend refuses the hidden task's reads regardless.
  const roleUser = api.currentUser;
  useEffect(() => {
    if (!roleUser || !profileReady || commercialRestricted) return;
    const page = workspaceFromLocation();
    const location = modeLocationFromSearch(page, window.location.search);
    if (!location || modeTaskVisible(location.task, roleUser)) return;
    const landing = modeLanding(location.mode.id, roleUser) ?? visibleModes(roleUser)[0]?.tasks[0] ?? null;
    if (landing) openWorkspace(landing.page, landing.pageTask);
  }, [roleUser, profileReady, commercialRestricted, openWorkspace, navigation.activeWorkspace, navigation.locationRevision]);

  // The layout class names the page whose layout is on screen, not only the page the URL named:
  // the market primary resolves a task inside its own shell, so the map task - chosen by tab, by
  // deep link or by the persisted view - has to bring the `.workspace-network` rules with it.
  // Keying the class on the URL alone left the map column unsized and its stage hidden.
  const layoutPage = layoutWorkspacePage({
    activeWorkspace: navigation.activeWorkspace,
    task: marketView.task,
  });

  // Every instant on screen follows the reader's "Times shown in" choice: re-render on a change.
  useTimePreferenceStore((state) => state.preference);

  // Phone width: a table wider than its box scrolls inside itself (styles/frame.css).
  const compactWidth = useCompactWidth();
  useWideContent(compactWidth);

  // Wave 9 shell surfaces: the canonical Inspector (object detail in one place)
  // and the command palette (one keyboard entry point to the derived command set).
  const inspector = useInspectorStore();
  // The palette finds a destination by its earlier name in either language ("Decision Center",
  // "决策中心", "Exposure"): old names are aliases of the new ones (WF-05).
  const paletteAliases = useCallback(
    (command: PaletteCommand) =>
      (command.aliasKeys ?? []).flatMap((key) => [i18n.t(key, { lng: "en" }), i18n.t(key, { lng: "zh-CN" })]),
    [i18n],
  );
  // A mode or task the caller's role cannot use is absent from the palette, as from the bar.
  const currentUser = api.currentUser;
  const paletteVisible = useCallback(
    (command: PaletteCommand) => {
      if (!command.target.mode) return true;
      const mode = visibleModes(currentUser).find((item) => item.id === command.target.mode);
      if (!mode) return false;
      if (command.target.modeTask) return mode.tasks.some((task) => task.id === command.target.modeTask);
      // A sub-view of a mode's page is offered when that page's task is.
      return command.target.page ? mode.tasks.some((task) => task.page === command.target.page) : true;
    },
    [currentUser],
  );
  // The palette finds the book's cargoes by id, vessel or IMO (QA-L-05). The board is read
  // once the palette has first been opened, by a person who may read the book, and shares the
  // cargo board's cached read.
  const [cargoesWanted, setCargoesWanted] = useState(false);
  const canReadBook = Array.isArray(currentUser?.permissions) && currentUser.permissions.includes("portfolio.read");
  const paletteCargoes = useCachedRead(cargoesWanted && canReadBook ? CARGO_BOARD_KEY : null, readCargoBoard);
  const palette = useCommandPalette({
    // AI off (small-desk 3.6): the palette offers no AI command at all.
    includeAiActions: aiAvailabilityOf(currentUser).available,
    activeWorkspace: navigation.activeWorkspace,
    context: {
      routeId: selection.routeId,
      resourceId: selection.resourceId,
      strategyVersionId: selection.strategyVersionId,
      strategyRunId: selection.strategyRunId,
    },
    capabilities: composition.effectiveCapabilities,
    activeContextComplete: Boolean(composition.available),
    labels: (command: PaletteCommand) => paletteLabel(command, t),
    glossaryTerms: api.glossaryTerms,
    cargoes: paletteCargoes.data ?? undefined,
    aliases: paletteAliases,
    visible: paletteVisible,
    onNavigate: (command: PaletteCommand) => {
      const page = command.target.page;
      if (command.target.primary) navigation.openPrimaryWorkspace(command.target.primary);
      // A mode opens at its first task the caller can use (the Desk at the remembered view).
      else if (command.target.mode && command.id === `navigate.mode.${command.target.mode}`) navigation.openMode(command.target.mode);
      else if (page) {
        const view = command.target.view;
        const entry = PAGE_VIEW_REGISTRY[page];
        navigation.openWorkspace(page, view && entry?.param === "task" ? view : undefined);
        if (view && entry?.param === "view") {
          // An administration or research sub-view: write it and let a mounted page follow.
          const url = new URL(window.location.href);
          url.search = viewToSearch(url.search, page, view);
          window.history.replaceState(window.history.state, "", url);
          window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
        }
        if (command.target.cargo) {
          // The cargo board opens at the cargo it was found by (its `cargo` URL parameter).
          const url = new URL(window.location.href);
          url.searchParams.set("cargo", command.target.cargo);
          window.history.replaceState(window.history.state, "", url);
          window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
        }
        if (command.target.term) {
          // The glossary opens at the term it was found by.
          const url = new URL(window.location.href);
          url.searchParams.set("term", command.target.term);
          window.history.replaceState(window.history.state, "", url);
        }
      }
    },
    onInspect: (kind, ref) =>
      inspector.open({
        kind,
        ref,
        label: ref,
        originPage: navigation.activeWorkspace,
      }),
    onUtility: (utility) => {
      if (utility === "access-identity") navigation.openWorkspace("access");
      else if (utility === "brief-morning") openDeskBrief("morning");
      else if (utility === "brief-eod") openDeskBrief("eod");
      else if (utility === "report-problem") requestProblemReport({});
      else if (utility === "help") navigation.openPrimaryWorkspace("system");
      else void api.signOut();
    },
  });

  useEffect(() => {
    if (palette.open) setCargoesWanted(true);
  }, [palette.open]);

  // The answer bar inside the palette (instant answers, look-ups, Ask).
  const answerBar = useAnswerBar({
    open: palette.open,
    query: palette.query,
    glossary: api.glossaryTerms,
    permissions: currentUser?.permissions ?? [],
    language: i18n.language,
    // A live answer (a spread) moves with the session's market updates while a stream is open.
    liveStamp: api.marketLastUpdatedAtUtc,
    streaming: api.streamingActive,
    liveQuotes: api.marketQuotes,
  });
  const openAnswerTarget = (target: AnswerTarget) => {
    const command = target.kind === "glossary"
      ? glossaryCommands([{ term: target.term }])[0]
      : commandById(`navigate.mode.${target.mode}.${target.task}`);
    if (command) palette.run(command);
    // A target that carries a question for the task (Spreads' description) puts it in the URL,
    // where the task reads it.
    if (command && target.kind === "task" && target.params) {
      const url = new URL(window.location.href);
      // The page's own task (Research → Spreads is `task=spreads` on the Research page).
      url.searchParams.set("task", target.task);
      for (const [key, value] of Object.entries(target.params)) url.searchParams.set(key, value);
      window.history.replaceState(window.history.state, "", url);
      window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    }
  };
  const openAskedReport = (question: string) => {
    const command = commandById("navigate.mode.research.reports");
    if (!command) return;
    palette.run(command);
    // Research → Reports reads the question and proposes its plan (its existing Ask flow).
    const url = new URL(window.location.href);
    url.searchParams.set("ask", question);
    window.history.replaceState(window.history.state, "", url);
    window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
  };

  return (
    <div className={`app cockpit-app workspace-${layoutPage}`} data-screen-stale={screenFreshness.current ? undefined : screenFreshness.reason}>
      <WorkspaceTopBar
        activeWorkspace={navigation.activeWorkspace}
        activePrimaryWorkspace={navigation.activePrimaryWorkspace}
        activeMode={navigation.activeMode}
        dataStatus={api.dataStatus}
        loading={api.loading}
        streamingActive={api.streamingActive}
        language={i18n.language}
        mode={theme.mode}
        marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
        sourceStats={sources.sourceStats}
        sourceEndpointError={api.endpointErrors.sources}
        currentUser={api.currentUser}
        monitoring={api}
        endpointFailures={endpointFailures}
        endpointRetry={endpointRetry}
        onRetryEndpoints={() => void api.retryFailedWorkspaceEndpoints()}
        onOpenDataSources={() => navigation.openWorkspace("sources")}
        t={t}
        onOpenPrimaryWorkspace={navigation.openPrimaryWorkspace}
        onOpenMode={navigation.openMode}
        onSignIn={() => void api.signIn()}
        onSignOut={() => void api.signOut()}
        onOpenAccess={() => navigation.openWorkspace("access")}
        onOpenSettings={() => navigation.openWorkspace("settings")}
        onOpenToday={() => navigation.openWorkspace("market", "overview")}
        onOpenCommandPalette={() => palette.setOpen(true)}
        onLanguageChange={chooseLanguage}
        onModeChange={chooseTheme}
      />
      {/* The situational strip under the menu: what needs this person now, by role (§5). */}
      <ShellTicker language={i18n.language} t={t} openWorkspace={navigation.openWorkspace} />

      {/* Reads that did not load: a quiet count on the bar's status indicator, and this line once
          per set of problems (dismissible); a store that does not answer stays (DataProblemNotice). */}
      {/* The server not answering (or this computer offline) is one calm line, not a list of
          failed reads; the clock line says when this computer's clock is off (small-desk 3.7). */}
      <ConnectionNotice t={t} />
      {screenFreshness.current || screenFreshness.reason === "live_quiet" ? (
        <DataProblemNotice
          t={t}
          failures={endpointFailures}
          retry={endpointRetry}
          onRetry={() => void api.retryFailedWorkspaceEndpoints()}
          storeDown={api.dataStatus === "unavailable"}
        />
      ) : null}

      <main className="app-main" ref={mainRef} id="workspace-primary-content" data-shell-region="primary-workspace">
        {/* One composition path for every page: the shell owns the regions, the workspace
            composition owns its pages. The map-first network route used to be intercepted
            here, which meant its surface was mounted outside the registry that declares it;
            it is now composed by the market primary like every other page of that primary
            (conflicting register C9). */}
        {controlPlaneRestricted || commercialRestricted ? (
          <RestrictedSurface t={t} />
        ) : (
          // A page that fails to draw shows a notice in its place; the top bar stays usable.
          <PanelErrorBoundary t={t} resetKey={navigationPlace}>
            <WorkspaceRenderer controller={controller} />
          </PanelErrorBoundary>
        )}
      </main>

      {inspector.subject && (
        <InspectorPanel
          subject={inspector.subject}
          detail={inspectorDetailFor(api, inspector.subject)}
          canGoBack={inspector.history.length > 0}
          t={t}
          onClose={inspector.close}
          onBack={inspector.back}
        />
      )}

      <DeskBriefDialog language={i18n.language} t={t} />

      {/* The first administrator's welcome flow (first-run setup); admins only, skippable. */}
      <FirstRunSetupGate
        currentUser={currentUser}
        t={t}
        onNavigate={(destination) => {
          navigation.openWorkspace(destination.page);
          if (destination.view) {
            const url = new URL(window.location.href);
            url.search = viewToSearch(url.search, destination.page, destination.view);
            window.history.replaceState(window.history.state, "", url);
            window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
          }
        }}
      />

      <CommandPalette
        open={palette.open}
        query={palette.query}
        results={palette.results}
        activeIndex={palette.activeIndex}
        unavailable={palette.unavailable}
        labelFor={(command) => paletteLabel(command, t)}
        reasonFor={(command) => paletteUnavailableReasonKey(command, palette.availability)}
        t={t}
        onQueryChange={palette.setQuery}
        onMove={palette.move}
        onRunActive={palette.runActive}
        onRun={palette.run}
        onClose={() => palette.setOpen(false)}
        answerBar={answerBar}
        onAnswerOpen={openAnswerTarget}
        onOpenReport={openAskedReport}
      />
    </div>
  );
}
