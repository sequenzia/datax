import { describe, it, expect, beforeEach } from "vitest";
import { useAiStatusStore } from "../ai-status-store";

describe("useAiStatusStore", () => {
  beforeEach(() => {
    // Reset the store to initial state
    useAiStatusStore.setState({
      connectionStatus: "checking",
      unavailableReason: null,
      bannerDismissed: false,
      hasProvider: true,
      lastCheckAt: null,
    });
  });

  it("starts with checking status", () => {
    const state = useAiStatusStore.getState();
    expect(state.connectionStatus).toBe("checking");
    expect(state.unavailableReason).toBeNull();
    expect(state.bannerDismissed).toBe(false);
  });

  it("sets connection status to disconnected", () => {
    useAiStatusStore.getState().setConnectionStatus("disconnected");
    expect(useAiStatusStore.getState().connectionStatus).toBe("disconnected");
  });

  it("auto-clears banner when connectivity is restored", () => {
    const store = useAiStatusStore.getState();

    // Simulate disconnection
    store.setConnectionStatus("disconnected");
    store.setUnavailableReason("network_error");
    store.dismissBanner();

    expect(useAiStatusStore.getState().bannerDismissed).toBe(true);

    // Restore connectivity
    useAiStatusStore.getState().setConnectionStatus("connected");

    const state = useAiStatusStore.getState();
    expect(state.connectionStatus).toBe("connected");
    expect(state.unavailableReason).toBeNull();
    expect(state.bannerDismissed).toBe(false);
  });

  it("dismisses banner", () => {
    useAiStatusStore.getState().dismissBanner();
    expect(useAiStatusStore.getState().bannerDismissed).toBe(true);
  });

  it("resets banner dismissed state when unavailable reason changes", () => {
    useAiStatusStore.getState().dismissBanner();
    expect(useAiStatusStore.getState().bannerDismissed).toBe(true);

    useAiStatusStore.getState().setUnavailableReason("provider_unreachable");
    expect(useAiStatusStore.getState().bannerDismissed).toBe(false);
  });

  it("sets no_provider reason when hasProvider becomes false", () => {
    useAiStatusStore.getState().setHasProvider(false);

    const state = useAiStatusStore.getState();
    expect(state.hasProvider).toBe(false);
    expect(state.unavailableReason).toBe("no_provider");
  });

  it("clears reason when hasProvider becomes true", () => {
    useAiStatusStore.getState().setHasProvider(false);
    expect(useAiStatusStore.getState().unavailableReason).toBe("no_provider");

    useAiStatusStore.getState().setHasProvider(true);
    expect(useAiStatusStore.getState().unavailableReason).toBeNull();
  });

  it("distinguishes no_provider from network_error", () => {
    // No provider
    useAiStatusStore.getState().setHasProvider(false);
    expect(useAiStatusStore.getState().unavailableReason).toBe("no_provider");

    // Reset
    useAiStatusStore.getState().setHasProvider(true);

    // Network error
    useAiStatusStore.getState().setUnavailableReason("network_error");
    expect(useAiStatusStore.getState().unavailableReason).toBe("network_error");
  });

  it("distinguishes network_error from provider_unreachable", () => {
    useAiStatusStore.getState().setUnavailableReason("network_error");
    expect(useAiStatusStore.getState().unavailableReason).toBe("network_error");

    useAiStatusStore.getState().setUnavailableReason("provider_unreachable");
    expect(useAiStatusStore.getState().unavailableReason).toBe(
      "provider_unreachable",
    );
  });

  it("records last check timestamp", () => {
    const now = Date.now();
    useAiStatusStore.getState().setLastCheckAt(now);
    expect(useAiStatusStore.getState().lastCheckAt).toBe(now);
  });
});
