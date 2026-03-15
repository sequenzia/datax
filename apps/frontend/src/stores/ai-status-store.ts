import { create } from "zustand";

export type AiConnectionStatus = "connected" | "disconnected" | "checking";

export type AiUnavailableReason =
  | "no_provider"
  | "provider_unreachable"
  | "network_error"
  | null;

interface AiStatusState {
  /** Current AI connectivity status */
  connectionStatus: AiConnectionStatus;
  /** Why the AI is unavailable, if it is */
  unavailableReason: AiUnavailableReason;
  /** Whether the user has dismissed the banner */
  bannerDismissed: boolean;
  /** Whether at least one provider is configured */
  hasProvider: boolean;
  /** Last successful connectivity check timestamp */
  lastCheckAt: number | null;

  setConnectionStatus: (status: AiConnectionStatus) => void;
  setUnavailableReason: (reason: AiUnavailableReason) => void;
  dismissBanner: () => void;
  resetBanner: () => void;
  setHasProvider: (has: boolean) => void;
  setLastCheckAt: (ts: number) => void;
}

export const useAiStatusStore = create<AiStatusState>((set) => ({
  connectionStatus: "checking",
  unavailableReason: null,
  bannerDismissed: false,
  hasProvider: true,
  lastCheckAt: null,

  setConnectionStatus: (connectionStatus) =>
    set((state) => {
      // Auto-clear banner when connectivity is restored
      if (connectionStatus === "connected" && state.connectionStatus !== "connected") {
        return {
          connectionStatus,
          unavailableReason: null,
          bannerDismissed: false,
        };
      }
      return { connectionStatus };
    }),

  setUnavailableReason: (unavailableReason) =>
    set({ unavailableReason, bannerDismissed: false }),

  dismissBanner: () => set({ bannerDismissed: true }),

  resetBanner: () => set({ bannerDismissed: false }),

  setHasProvider: (hasProvider) =>
    set((state) => {
      if (!hasProvider && state.hasProvider) {
        return {
          hasProvider,
          unavailableReason: "no_provider",
          bannerDismissed: false,
        };
      }
      if (hasProvider && !state.hasProvider) {
        return {
          hasProvider,
          unavailableReason: null,
          bannerDismissed: false,
        };
      }
      return { hasProvider };
    }),

  setLastCheckAt: (lastCheckAt) => set({ lastCheckAt }),
}));
