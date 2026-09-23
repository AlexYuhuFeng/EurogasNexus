/**
 * The vanilla zustand store creator, under the name the api store imports.
 *
 * `stores/api.ts` imports `create` from `zustand`, whose main entry also binds a React hook. These
 * tests drive the store's own actions (`getState` / `setState`), which the vanilla creator
 * implements, so the harness swaps the entry for this re-export rather than rendering React in Node.
 */

export { createStore as create } from "zustand/vanilla";
