/** TanStack Query hooks for SQL query execution, saved queries, and history. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  executeQuery,
  explainQuery,
  saveQuery,
  updateSavedQuery,
  deleteSavedQuery,
  fetchSavedQueries,
  fetchQueryHistory,
} from "@/lib/api";
import type {
  ExecuteQueryRequest,
  ExplainRequest,
  SaveQueryRequest,
} from "@/types/api";

const SAVED_QUERIES_KEY = ["savedQueries"] as const;
const QUERY_HISTORY_KEY = ["queryHistory"] as const;

export function useExecuteQuery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      body,
      signal,
    }: {
      body: ExecuteQueryRequest;
      signal?: AbortSignal;
    }) => executeQuery(body, signal),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_HISTORY_KEY });
    },
  });
}

export function useExplainQuery() {
  return useMutation({
    mutationFn: (body: ExplainRequest) => explainQuery(body),
  });
}

export function useSavedQueries() {
  return useQuery({
    queryKey: SAVED_QUERIES_KEY,
    queryFn: fetchSavedQueries,
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}

export function useSaveQuery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveQueryRequest) => saveQuery(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SAVED_QUERIES_KEY });
    },
  });
}

export function useUpdateSavedQuery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SaveQueryRequest }) =>
      updateSavedQuery(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SAVED_QUERIES_KEY });
    },
  });
}

export function useDeleteSavedQuery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSavedQuery(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SAVED_QUERIES_KEY });
    },
  });
}

export function useQueryHistory(params?: {
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: [...QUERY_HISTORY_KEY, params],
    queryFn: () => fetchQueryHistory(params),
    retry: 3,
    retryDelay: (attemptIndex: number) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
