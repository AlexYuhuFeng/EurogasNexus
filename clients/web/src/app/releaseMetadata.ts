/** Client release identity. Kept in sync with pyproject.toml by
 * scripts/release/check_version_consistency.py.
 *
 * Application version, channel and commit are deliberately separate fields;
 * no code may derive the channel from an installer filename.
 */

export const CLIENT_APPLICATION_VERSION = "0.5.0";
const viteEnv = (import.meta as { env?: Record<string, string> }).env ?? {};
export const CLIENT_RELEASE_CHANNEL = viteEnv.VITE_EUROGAS_RELEASE_CHANNEL?.trim() || "preview";
export const CLIENT_MINIMUM_SUPPORTED_SERVER = "0.5.0";
export const CLIENT_BUILD_GIT_SHA = viteEnv.VITE_EUROGAS_BUILD_GIT_SHA?.trim() || null;
export const CLIENT_BUILD_GIT_REF = viteEnv.VITE_EUROGAS_BUILD_GIT_REF?.trim() || null;
export const CLIENT_BUILD_RUN_ID = viteEnv.VITE_EUROGAS_BUILD_RUN_ID?.trim() || null;
