/**
 * Hook to monitor AI service availability.
 *
 * Polls the backend health endpoint and checks provider configuration
 * to determine whether the AI assistant is available. Manages the
 * AI status store accordingly.
 */

import { useEffect, useRef, useCallback } from "react";
import { useProviders } from "@/hooks/use-providers";
import { useAiStatusStore } from "@/stores/ai-status-store";
import type { AiConnectionStatus, AiUnavailableReason } from "@/stores/ai-status-store";

/** How often to poll for connectivity (ms) */
const HEALTH_POLL_INTERVAL = 30_000;

/** Timeout for the health check fetch (ms) */
const HEALTH_CHECK_TIMEOUT = 5_000;

async function checkAgentHealth(): Promise<{
  reachable: boolean;
  errorType: "network_error" | "provider_unreachable" | null;
}> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT);

    const response = await fetch("/api/agent/health", {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      return { reachable: true, errorType: null };
    }

    // Server responded but with an error status
    return { reachable: false, errorType: "provider_unreachable" };
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { reachable: false, errorType: "network_error" };
    }
    // Network-level failure (CORS, DNS, connection refused, etc.)
    return { reachable: false, errorType: "network_error" };
  }
}

export function useAiStatus(): {
  connectionStatus: AiConnectionStatus;
  unavailableReason: AiUnavailableReason;
  hasProvider: boolean;
  bannerDismissed: boolean;
  showBanner: boolean;
  bannerMessage: string;
  dismissBanner: () => void;
  chatDisabled: boolean;
  chatDisabledMessage: string | null;
} {
  const {
    connectionStatus,
    unavailableReason,
    hasProvider,
    bannerDismissed,
    setConnectionStatus,
    setUnavailableReason,
    setHasProvider,
    setLastCheckAt,
    dismissBanner,
  } = useAiStatusStore();

  const { data: providers, isError: providersError } = useProviders();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update provider status when provider data changes
  useEffect(() => {
    if (providersError) {
      // Can't determine provider status; treat as no provider for safety
      return;
    }
    if (providers !== undefined) {
      const hasActiveProvider = providers.length > 0;
      setHasProvider(hasActiveProvider);
    }
  }, [providers, providersError, setHasProvider]);

  // Health check callback
  const runHealthCheck = useCallback(async () => {
    setConnectionStatus("checking");
    const result = await checkAgentHealth();
    setLastCheckAt(Date.now());

    if (result.reachable) {
      setConnectionStatus("connected");
    } else {
      setConnectionStatus("disconnected");
      if (result.errorType) {
        setUnavailableReason(result.errorType);
      }
    }
  }, [setConnectionStatus, setUnavailableReason, setLastCheckAt]);

  // Poll health periodically
  useEffect(() => {
    // Only poll if we have providers configured
    if (!hasProvider) {
      setConnectionStatus("disconnected");
      return;
    }

    void runHealthCheck();

    pollRef.current = setInterval(() => {
      void runHealthCheck();
    }, HEALTH_POLL_INTERVAL);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [hasProvider, runHealthCheck, setConnectionStatus]);

  // Determine banner visibility and message
  const isDisconnected = connectionStatus === "disconnected";
  const noProvider = unavailableReason === "no_provider" || !hasProvider;

  const showBanner = isDisconnected && !bannerDismissed;

  let bannerMessage: string;
  if (noProvider) {
    bannerMessage =
      "Configure an AI provider in Settings to start chatting.";
  } else if (unavailableReason === "network_error") {
    bannerMessage =
      "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.";
  } else if (unavailableReason === "provider_unreachable") {
    bannerMessage =
      "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.";
  } else {
    bannerMessage =
      "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.";
  }

  // Chat should be disabled when AI is not available
  const chatDisabled = isDisconnected || !hasProvider;
  let chatDisabledMessage: string | null = null;
  if (!hasProvider) {
    chatDisabledMessage =
      "Configure an AI provider in Settings to start chatting";
  } else if (isDisconnected) {
    chatDisabledMessage = "AI assistant is currently unavailable";
  }

  return {
    connectionStatus,
    unavailableReason,
    hasProvider,
    bannerDismissed,
    showBanner,
    bannerMessage,
    dismissBanner,
    chatDisabled,
    chatDisabledMessage,
  };
}
