/** API client for backend communication. */

import type {
  Dataset,
  DatasetDetail,
  DatasetPreview,
  DatasetProfile,
  DatasetUploadResponse,
  Bookmark,
  BookmarkListResponse,
  CreateBookmarkRequest,
  Dashboard,
  DashboardItem,
  DashboardListResponse,
  CreateDashboardRequest,
  UpdateDashboardRequest,
  AddDashboardItemRequest,
  Connection,
  ConnectionDetail,
  ConnectionTestResult,
  ConnectionCreateRequest,
  ConnectionUpdateRequest,
  ConnectionTestParamsRequest,
  Conversation,
  ConversationListResponse,
  ConversationDetail,
  ProviderConfig,
  ProviderCreateRequest,
  ExecuteQueryRequest,
  ExecuteQueryResponse,
  ExplainRequest,
  ExplainResponse,
  SaveQueryRequest,
  SavedQuery,
  SavedQueryListResponse,
  HistoryResponse,
  SchemaResponse,
} from "@/types/api";

const API_BASE = "/api/v1";

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function apiMutate<T>(
  path: string,
  options: { method: string; body?: unknown },
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `API error: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function fetchDatasets(): Promise<Dataset[]> {
  const data = await apiFetch<{ datasets: Dataset[] }>("/datasets");
  return data.datasets;
}

export function fetchDataset(id: string): Promise<DatasetDetail> {
  return apiFetch<DatasetDetail>(`/datasets/${id}`);
}

export function fetchDatasetPreview(
  id: string,
  params: { offset?: number; limit?: number; sort_by?: string; sort_order?: string } = {},
): Promise<DatasetPreview> {
  const search = new URLSearchParams();
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.sort_by) search.set("sort_by", params.sort_by);
  if (params.sort_order) search.set("sort_order", params.sort_order);
  const qs = search.toString();
  return apiFetch<DatasetPreview>(`/datasets/${id}/preview${qs ? `?${qs}` : ""}`);
}

export function fetchDatasetProfile(id: string): Promise<DatasetProfile> {
  return apiFetch<DatasetProfile>(`/datasets/${id}/profile`);
}

export function deleteDataset(id: string): Promise<void> {
  return apiMutate<void>(`/datasets/${id}`, { method: "DELETE" });
}

export async function uploadDataset(
  file: File,
  name?: string,
): Promise<DatasetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);

  const response = await fetch(`${API_BASE}/datasets/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `API error: ${response.status}`);
  }
  return response.json() as Promise<DatasetUploadResponse>;
}

export async function fetchConnections(): Promise<Connection[]> {
  const data = await apiFetch<{ connections: Connection[] }>("/connections");
  return data.connections;
}

export function fetchConnection(id: string): Promise<ConnectionDetail> {
  return apiFetch<ConnectionDetail>(`/connections/${id}`);
}

export function fetchConnectionSchema(
  connectionId: string,
): Promise<ConnectionDetail> {
  return apiFetch<ConnectionDetail>(`/connections/${connectionId}`);
}

export async function fetchConversations(): Promise<Conversation[]> {
  const data = await apiFetch<{ conversations: Conversation[] }>("/conversations");
  return data.conversations;
}

export function fetchConversationsPaginated(params: {
  cursor?: string | null;
  limit?: number;
  search?: string;
}): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams();
  if (params.cursor) searchParams.set("cursor", params.cursor);
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.search) searchParams.set("search", params.search);
  const qs = searchParams.toString();
  return apiFetch<ConversationListResponse>(
    `/conversations${qs ? `?${qs}` : ""}`,
  );
}

export function deleteConversation(id: string): Promise<void> {
  return apiMutate<void>(`/conversations/${id}`, { method: "DELETE" });
}

export function updateConversationTitle(
  id: string,
  title: string,
): Promise<Conversation> {
  return apiMutate<Conversation>(`/conversations/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export function testConnection(connectionId: string): Promise<ConnectionTestResult> {
  return apiMutate<ConnectionTestResult>(`/connections/${connectionId}/test`, {
    method: "POST",
  });
}

export function refreshConnectionSchema(
  connectionId: string,
): Promise<Connection> {
  return apiMutate<Connection>(`/connections/${connectionId}/refresh-schema`, {
    method: "POST",
  });
}

export function createConnection(
  body: ConnectionCreateRequest,
): Promise<Connection> {
  return apiMutate<Connection>("/connections", {
    method: "POST",
    body,
  });
}

export function updateConnection(
  connectionId: string,
  body: ConnectionUpdateRequest,
): Promise<Connection> {
  return apiMutate<Connection>(`/connections/${connectionId}`, {
    method: "PUT",
    body,
  });
}

export function testConnectionParams(
  body: ConnectionTestParamsRequest,
): Promise<ConnectionTestResult> {
  return apiMutate<ConnectionTestResult>("/connections/test-params", {
    method: "POST",
    body,
  });
}

export function deleteConnection(connectionId: string): Promise<void> {
  return apiMutate<void>(`/connections/${connectionId}`, {
    method: "DELETE",
  });
}

export async function fetchProviders(): Promise<ProviderConfig[]> {
  const data = await apiFetch<{ providers: ProviderConfig[] }>(
    "/settings/providers",
  );
  return data.providers;
}

export function createProviderConfig(
  body: ProviderCreateRequest,
): Promise<ProviderConfig> {
  return apiMutate<ProviderConfig>("/settings/providers", {
    method: "POST",
    body,
  });
}

export function deleteProvider(id: string): Promise<void> {
  return apiMutate<void>(`/settings/providers/${id}`, {
    method: "DELETE",
  });
}

export function executeQuery(
  body: ExecuteQueryRequest,
  signal?: AbortSignal,
): Promise<ExecuteQueryResponse> {
  return fetch(`${API_BASE}/queries/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text().catch(() => response.statusText);
      throw new Error(text || `API error: ${response.status}`);
    }
    return response.json() as Promise<ExecuteQueryResponse>;
  });
}

export function explainQuery(
  body: ExplainRequest,
): Promise<ExplainResponse> {
  return apiMutate<ExplainResponse>("/queries/explain", {
    method: "POST",
    body,
  });
}

export function saveQuery(
  body: SaveQueryRequest,
): Promise<SavedQuery> {
  return apiMutate<SavedQuery>("/queries/save", {
    method: "POST",
    body,
  });
}

export function updateSavedQuery(
  id: string,
  body: SaveQueryRequest,
): Promise<SavedQuery> {
  return apiMutate<SavedQuery>(`/queries/saved/${id}`, {
    method: "PUT",
    body,
  });
}

export function deleteSavedQuery(id: string): Promise<void> {
  return apiMutate<void>(`/queries/saved/${id}`, {
    method: "DELETE",
  });
}

export function fetchSavedQueries(): Promise<SavedQuery[]> {
  return apiFetch<SavedQueryListResponse>("/queries/saved").then(
    (data) => data.queries,
  );
}

export function fetchSchema(): Promise<SchemaResponse> {
  return apiFetch<SchemaResponse>("/schema");
}

export function fetchQueryHistory(params?: {
  limit?: number;
  offset?: number;
}): Promise<HistoryResponse> {
  const search = new URLSearchParams();
  if (params?.limit !== undefined) search.set("limit", String(params.limit));
  if (params?.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  return apiFetch<HistoryResponse>(`/queries/history${qs ? `?${qs}` : ""}`);
}

export function createConversation(): Promise<Conversation> {
  return apiMutate<Conversation>("/conversations", { method: "POST" });
}

export function fetchConversationDetail(
  id: string,
): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/conversations/${id}`);
}

export function saveMessage(
  conversationId: string,
  body: { role: "user" | "assistant"; content: string },
): Promise<Message> {
  return apiMutate<Message>(`/conversations/${conversationId}/messages`, {
    method: "POST",
    body,
  });
}

/* -------------------------------------------------------------------------- */
/*  Bookmarks                                                                  */
/* -------------------------------------------------------------------------- */

export async function fetchBookmarks(): Promise<Bookmark[]> {
  const data = await apiFetch<BookmarkListResponse>("/bookmarks");
  return data.bookmarks;
}

export function createBookmark(
  body: CreateBookmarkRequest,
): Promise<Bookmark> {
  return apiMutate<Bookmark>("/bookmarks", {
    method: "POST",
    body,
  });
}

export function deleteBookmark(id: string): Promise<void> {
  return apiMutate<void>(`/bookmarks/${id}`, { method: "DELETE" });
}

/* -------------------------------------------------------------------------- */
/*  Dashboards                                                                  */
/* -------------------------------------------------------------------------- */

export async function fetchDashboards(): Promise<Dashboard[]> {
  const data = await apiFetch<DashboardListResponse>("/dashboards");
  return data.dashboards;
}

export function fetchDashboard(id: string): Promise<Dashboard> {
  return apiFetch<Dashboard>(`/dashboards/${id}`);
}

export function createDashboard(
  body: CreateDashboardRequest,
): Promise<Dashboard> {
  return apiMutate<Dashboard>("/dashboards", {
    method: "POST",
    body,
  });
}

export function updateDashboard(
  id: string,
  body: UpdateDashboardRequest,
): Promise<Dashboard> {
  return apiMutate<Dashboard>(`/dashboards/${id}`, {
    method: "PUT",
    body,
  });
}

export function deleteDashboard(id: string): Promise<void> {
  return apiMutate<void>(`/dashboards/${id}`, { method: "DELETE" });
}

export function addDashboardItem(
  dashboardId: string,
  body: AddDashboardItemRequest,
): Promise<DashboardItem> {
  return apiMutate<DashboardItem>(`/dashboards/${dashboardId}/items`, {
    method: "POST",
    body,
  });
}

export function removeDashboardItem(
  dashboardId: string,
  itemId: string,
): Promise<void> {
  return apiMutate<void>(`/dashboards/${dashboardId}/items/${itemId}`, {
    method: "DELETE",
  });
}

