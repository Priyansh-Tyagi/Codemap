import { createContext, useContext } from "react";

// Pages read this; App provides it. Kept apart from the hook that talks to the
// network so a page that only needs the value never imports the API layer.
// The default is the "nothing to report" state, so a page rendered without a
// provider (every page test, Storybook-style previews) behaves exactly as before.
export const DEFAULT_SERVER_STATUS = {
  phase: "ready",
  storage: { state: "unmanaged" },
  elapsedSeconds: 0,
  retry: () => {},
};

export const ServerStatusContext = createContext(DEFAULT_SERVER_STATUS);

export function useServerStatusContext() {
  return useContext(ServerStatusContext);
}

/** True when projects saved right now will not survive a server restart. */
export function isStorageDegraded(status) {
  return status?.phase === "ready" && status?.storage?.state === "degraded";
}
