/** TanStack Query hooks for dataset management. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDatasets,
  fetchDataset,
  fetchDatasetPreview,
  fetchDatasetProfile,
  deleteDataset,
  uploadDataset,
} from "@/lib/api";

export function useDatasetList() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useDatasetDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id],
    queryFn: () => fetchDataset(id!),
    enabled: !!id,
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message.includes("404")) return false;
      return failureCount < 3;
    },
  });
}

export function useDatasetPreview(
  id: string | undefined,
  params: { offset?: number; limit?: number; sort_by?: string; sort_order?: string } = {},
) {
  return useQuery({
    queryKey: ["datasets", id, "preview", params],
    queryFn: () => fetchDatasetPreview(id!, params),
    enabled: !!id,
    retry: 2,
  });
}

export function useDatasetProfile(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id, "profile"],
    queryFn: () => fetchDatasetProfile(id!),
    enabled: !!id,
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message.includes("404")) return false;
      return failureCount < 3;
    },
  });
}

export function useDeleteDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDataset,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}

export function useUploadDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, name }: { file: File; name?: string }) =>
      uploadDataset(file, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}
