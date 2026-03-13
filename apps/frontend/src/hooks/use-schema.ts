/** TanStack Query hook for unified schema data. */

import { useQuery } from "@tanstack/react-query";
import { fetchSchema } from "@/lib/api";

export function useSchema() {
  return useQuery({
    queryKey: ["schema"],
    queryFn: fetchSchema,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
    staleTime: 30_000,
  });
}
