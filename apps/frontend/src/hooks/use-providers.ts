/** TanStack Query hooks for AI provider configuration. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchProviders,
  createProviderConfig,
  deleteProvider,
} from "@/lib/api";
import type { ProviderCreateRequest } from "@/types/api";

const PROVIDERS_KEY = ["providers"] as const;

export function useProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: fetchProviders,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useCreateProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderCreateRequest) => createProviderConfig(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}
