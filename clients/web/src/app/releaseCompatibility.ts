/** Client/server compatibility contract for the unversioned `/api` surface.
 *
 * Compatibility is explicit metadata, never a substring of an installer
 * filename and never a guess from the URL. The backend exposes this metadata
 * at `GET /api/runtime/release`.
 */

import {
  CLIENT_APPLICATION_VERSION,
  CLIENT_BUILD_GIT_SHA,
  CLIENT_MINIMUM_SUPPORTED_SERVER,
  CLIENT_RELEASE_CHANNEL,
} from "./releaseMetadata.ts";

export type ReleaseChannel = "preview" | "rc" | "stable";

export interface ClientReleaseMetadata {
  version: string;
  channel: ReleaseChannel;
  buildGitSha: string | null;
  minimumSupportedServer: string;
}

export interface ServerReleaseMetadata {
  application_version: string;
  release_channel: ReleaseChannel;
  git_sha: string | null;
  api_contract_version: string;
  database_schema_revision: string;
  minimum_supported_client: string;
  minimum_supported_server: string;
  backtest_engine_version: string;
  strategy_schema_version: string;
  strategy_run_schema_version: string;
  solver_version: string;
}

export type ReleaseCompatibilityState =
  | "compatible"
  | "client_update_required"
  | "server_upgrade_required"
  | "contract_mismatch"
  | "unknown";

export interface ReleaseCompatibility {
  state: ReleaseCompatibilityState;
  clientVersion: string;
  serverVersion: string;
  minimumSupportedClient: string | null;
  minimumSupportedServer: string | null;
  apiContractVersion: string | null;
  messageKey: string;
}

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease: string[];
  core: string;
}

export function parseVersion(value: string | null | undefined): ParsedVersion | null {
  if (!value) return null;
  const match = /^\s*(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\s*$/.exec(value);
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease: match[4] ? match[4].split(".") : [],
    core: `${match[1]}.${match[2]}.${match[3]}`,
  };
}

export function compareVersions(left: string | null | undefined, right: string | null | undefined): number {
  const a = parseVersion(left);
  const b = parseVersion(right);
  if (!a || !b) return 0;
  if (a.major !== b.major) return a.major - b.major;
  if (a.minor !== b.minor) return a.minor - b.minor;
  if (a.patch !== b.patch) return a.patch - b.patch;
  if (a.prerelease.length === 0 && b.prerelease.length === 0) return 0;
  if (a.prerelease.length === 0) return 1;
  if (b.prerelease.length === 0) return -1;
  const length = Math.max(a.prerelease.length, b.prerelease.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = a.prerelease[index];
    const rightPart = b.prerelease[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    const leftNumber = /^\d+$/.test(leftPart) ? Number(leftPart) : null;
    const rightNumber = /^\d+$/.test(rightPart) ? Number(rightPart) : null;
    if (leftNumber !== null && rightNumber !== null) {
      if (leftNumber !== rightNumber) return leftNumber - rightNumber;
      continue;
    }
    if (leftPart !== rightPart) return leftPart < rightPart ? -1 : 1;
  }
  return 0;
}

export function compatibilityForServer(
  client: ClientReleaseMetadata,
  server: ServerReleaseMetadata | null,
): ReleaseCompatibility {
  if (!server) {
    return {
      state: "unknown",
      clientVersion: client.version,
      serverVersion: "unknown",
      minimumSupportedClient: null,
      minimumSupportedServer: null,
      apiContractVersion: null,
      messageKey: "release.compat_unknown",
    };
  }

  const serverMinClient = server.minimum_supported_client;
  const contractMismatch = server.api_contract_version !== "api-contract/v1";
  const clientTooOld =
    Boolean(serverMinClient) && compareVersions(client.version, serverMinClient) < 0;
  const serverTooOld =
    Boolean(client.minimumSupportedServer) &&
    compareVersions(server.application_version, client.minimumSupportedServer) < 0;

  if (contractMismatch) {
    return {
      state: "contract_mismatch",
      clientVersion: client.version,
      serverVersion: server.application_version,
      minimumSupportedClient: serverMinClient ?? null,
      minimumSupportedServer: server.minimum_supported_server ?? null,
      apiContractVersion: server.api_contract_version,
      messageKey: "release.compat_contract_mismatch",
    };
  }
  if (serverTooOld) {
    return {
      state: "server_upgrade_required",
      clientVersion: client.version,
      serverVersion: server.application_version,
      minimumSupportedClient: serverMinClient ?? null,
      minimumSupportedServer: client.minimumSupportedServer,
      apiContractVersion: server.api_contract_version,
      messageKey: "release.compat_server_upgrade_required",
    };
  }
  if (clientTooOld) {
    return {
      state: "client_update_required",
      clientVersion: client.version,
      serverVersion: server.application_version,
      minimumSupportedClient: serverMinClient ?? null,
      minimumSupportedServer: server.minimum_supported_server ?? null,
      apiContractVersion: server.api_contract_version,
      messageKey: "release.compat_client_update_required",
    };
  }
  return {
    state: "compatible",
    clientVersion: client.version,
    serverVersion: server.application_version,
    minimumSupportedClient: serverMinClient ?? null,
    minimumSupportedServer: server.minimum_supported_server ?? null,
    apiContractVersion: server.api_contract_version,
    messageKey: "release.compat_ok",
  };
}

export const CLIENT_RELEASE_METADATA: ClientReleaseMetadata = {
  version: CLIENT_APPLICATION_VERSION,
  channel: CLIENT_RELEASE_CHANNEL as ReleaseChannel,
  buildGitSha: CLIENT_BUILD_GIT_SHA,
  minimumSupportedServer: CLIENT_MINIMUM_SUPPORTED_SERVER,
};

export function isBlockingCompatibility(state: ReleaseCompatibilityState): boolean {
  return (
    state === "client_update_required" ||
    state === "server_upgrade_required" ||
    state === "contract_mismatch"
  );
}
