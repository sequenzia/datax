/** TanStack Query hooks for dashboard CRUD operations. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDashboards,
  fetchDashboard,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  addDashboardItem,
  removeDashboardItem,
  executeQuery,
} from "@/lib/api";
import type {
  CreateDashboardRequest,
  UpdateDashboardRequest,
  AddDashboardItemRequest,
  DashboardItem,
  ExecuteQueryResponse,
} from "@/types/api";

export function useDashboardList() {
  return useQuery({
    queryKey: ["dashboards"],
    queryFn: fetchDashboards,
    retry: 2,
  });
}

export function useDashboard(id: string | undefined) {
  return useQuery({
    queryKey: ["dashboards", id],
    queryFn: () => fetchDashboard(id!),
    enabled: !!id,
    retry: 2,
  });
}

export function useCreateDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateDashboardRequest) => createDashboard(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}

export function useUpdateDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateDashboardRequest }) =>
      updateDashboard(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDashboard(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}

export function useAddDashboardItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dashboardId,
      body,
    }: {
      dashboardId: string;
      body: AddDashboardItemRequest;
    }) => addDashboardItem(dashboardId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}

export function useRemoveDashboardItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dashboardId,
      itemId,
    }: {
      dashboardId: string;
      itemId: string;
    }) => removeDashboardItem(dashboardId, itemId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}

/** Auto-refresh: re-execute a bookmark's SQL to get current data. */
export function useAutoRefreshItem(item: DashboardItem) {
  const bookmark = item.bookmark;
  const hasSql = !!bookmark?.sql && !!bookmark?.source_id && !!bookmark?.source_type;

  return useQuery<ExecuteQueryResponse>({
    queryKey: ["dashboard-refresh", item.id, bookmark?.sql],
    queryFn: () =>
      executeQuery({
        sql: bookmark!.sql!,
        source_id: bookmark!.source_id!,
        source_type: bookmark!.source_type as "dataset" | "connection",
      }),
    enabled: hasSql,
    retry: 1,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
