/** TanStack Query hooks for connection management. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchConnections,
  fetchConnection,
  createConnection,
  updateConnection,
  testConnection,
  testConnectionParams,
  refreshConnectionSchema,
  deleteConnection,
} from "@/lib/api";
import type {
  ConnectionCreateRequest,
  ConnectionUpdateRequest,
  ConnectionTestParamsRequest,
} from "@/types/api";

export function useConnectionList() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: fetchConnections,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useConnectionDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["connections", id],
    queryFn: () => fetchConnection(id!),
    enabled: !!id,
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message.includes("404")) return false;
      return failureCount < 3;
    },
  });
}

export function useCreateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ConnectionCreateRequest) => createConnection(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });
}

export function useUpdateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: ConnectionUpdateRequest;
    }) => updateConnection(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });
}

export function useTestConnectionParams() {
  return useMutation({
    mutationFn: (body: ConnectionTestParamsRequest) =>
      testConnectionParams(body),
  });
}

export function useTestConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: testConnection,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });
}

export function useRefreshConnectionSchema() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: refreshConnectionSchema,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });
}

export function useDeleteConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConnection,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });
}
