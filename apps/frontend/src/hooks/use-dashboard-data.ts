/** TanStack Query hooks for dashboard data fetching. */

import { useQuery } from "@tanstack/react-query";
import { fetchDatasets, fetchConnections, fetchConversations } from "@/lib/api";

const POLL_INTERVAL = 30_000; // 30 seconds

export function useDatasets() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
    refetchInterval: POLL_INTERVAL,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: fetchConnections,
    refetchInterval: POLL_INTERVAL,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
