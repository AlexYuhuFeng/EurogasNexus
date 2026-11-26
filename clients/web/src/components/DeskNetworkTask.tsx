import { api as apiClient, type EdgeDTO, type NodeDTO, type TodayNeedsMeItemDTO } from "@/api/client";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import { readKey, useCachedRead } from "@/app/data/readCache";
import type { AppController } from "@/app/hooks/useAppController";
import { capacityOperatingBoardRead } from "@/app/model/capacityOperatingBoardRead";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";

/** The kept page id of Desk → Network (app/data/keepAlive.tsx). */
export const DESK_NETWORK_KEPT = "desk-network";

/**
 * Desk → Network as a kept page: rendered once at the shell (WorkspaceRenderer) and shown by
 * the Desk page's slot, so the map, its sources, camera and selection outlive a visit to any
 * other page. `active` is whether it is on screen.
 */
export function DeskNetworkTask({ controller, active }: { controller: AppController; active: boolean }) {
  const { t, api, theme, portfolio, controls } = controller;
  // Today's "What needs me" (CP-19): the items with a place are listed beside the map. The read
  // is Today's own (one shared cache entry, app/hooks/useDeskToday.ts).
  const desk = useDeskToday();
  const needsMe = (desk.today?.rows.find((row) => row?.key === "needs_me") as { items?: TodayNeedsMeItemDTO[] } | undefined)?.items;
  // Reference geometry, read by the map itself until the workspace batch has it (the batch
  // commits when its slowest read answers): cached for the session, never re-read.
  const waiting = api.nodes.length === 0;
  const ownNodes = useCachedRead<NodeDTO[]>(
    waiting ? readKey("/reference-network/nodes", { limit: 2000 }) : null,
    (signal) => apiClient.nodes(undefined, { signal }).then((response) => (Array.isArray(response.data) ? response.data : [])),
    { freshMs: Number.POSITIVE_INFINITY },
  );
  const ownEdges = useCachedRead<EdgeDTO[]>(
    api.edges.length === 0 ? readKey("/reference-network/edges", { limit: 2000 }) : null,
    (signal) => apiClient.edges(undefined, { signal }).then((response) => (Array.isArray(response.data) ? response.data : [])),
    { freshMs: Number.POSITIVE_INFINITY },
  );
  return (
    <NetworkWorkspace
      t={t}
      nodes={api.nodes.length ? api.nodes : ownNodes.data ?? api.nodes}
      edges={api.edges.length ? api.edges : ownEdges.data ?? api.edges}
      routes={api.routes}
      mode={theme.mode}
      activeLayers={controls.activeLayers}
      searchTerm={controls.searchTerm}
      networkGeometryState={portfolio.networkGeometryState}
      onToggleLayer={controls.toggleLayer}
      onDefaultLayers={controls.resetLayers}
      // Parked while another page shows: nothing it opened stays above that page, and its
      // timers and map rendering pause.
      active={active}
      language={controller.i18n.language}
      needsMe={needsMe}
      // The Capacity tab beside the map: the operating board joins the `flows` and
      // `capacity` reads, so it states which of them answered from the store's own facts
      // (`app/model/capacityOperatingBoardRead.ts`), as the Source Center does.
      capacity={{
        flows: api.flows,
        capacity: api.capacity,
        tsoAccess: api.tsoAccess,
        tsoTariffs: api.tsoTariffs,
        storage: api.storage,
        lng: api.lng,
        boardRead: capacityOperatingBoardRead(
          {
            flows: {
              rows: api.flows.length,
              error: api.endpointErrors.flows,
              errorCode: api.endpointErrorCodes.flows,
            },
            capacity: {
              rows: api.capacity.length,
              error: api.endpointErrors.capacity,
              errorCode: api.endpointErrorCodes.capacity,
            },
            loading: api.workspaceLoading,
            committedPasses: api.workspaceLoadsCommitted,
            retry: {
              busy: api.endpointRetryBusy,
              attempts: api.endpointRetryAttempts,
              lastAttemptAtUtc: api.endpointRetryLastAttemptAtUtc,
            },
          },
          t,
        ),
        onRetryBoardRead: () => void api.retryFailedWorkspaceEndpoints(),
      }}
    />
  );
}
