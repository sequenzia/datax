/** TanStack Query hooks for dashboard data fetching. */

import { useQuery } from "@tanstack/react-query";
import { fetchConversations } from "@/lib/api";

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
